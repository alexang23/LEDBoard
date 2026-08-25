import asyncio
import collections
import concurrent.futures
import copy
import json
import random
import re
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Thread

import aiomqtt
from aiomqtt import Will
from aiomqtt.client import Properties, ProtocolVersion, mqtt

import gyro_watchdog
from config import settings
from global_log import LoggerFile

DEFAULT_MAX_RECEIVE_QUEUE_SIZE = 1000
MAX_RECONNECT_DELAY = 30
MAX_OUTBOUND_RETRIES = 5
MAX_CMD_WAIT = 30
# Liveness gap for the MQTTSvc watchdog name. Must cover the worst legitimate
# quiet period: backoff (<=MAX_RECONNECT_DELAY) + a connect attempt
# (<= settings.MQTT_TIMEOUT) + margin, so a normal broker outage is not
# reported as a stalled thread.
MQTT_WATCHDOG_MAX_GAP = max(90, MAX_RECONNECT_DELAY + int(getattr(settings, "MQTT_TIMEOUT", 10)) + 60)
# Dedicated, size-bounded executor for the blocking E84/RFID calls wrapped by
# asyncio.wait_for. A stuck thread cannot be killed, but bounding it here keeps
# one wedged call from occupying a slot in the shared default executor.
CMD_EXECUTOR_MAX_WORKERS = 4


@dataclass
class MQTTCorrelation:
    ResponseTopic: str
    CorrelationData: bytes | None = None


class MQTTSvc(Thread):
    def __init__(self, controller, logger, uiform=None) -> None:
        super().__init__(name="MQTTSvc")

        self.svc_name = "mqtt"
        self.uiform = uiform
        self.controller = controller
        self.logger = logger
        self.logger_heartbeat = LoggerFile("heartbeat", "heartbeat.log")
        self.logger_mqtt = LoggerFile("mqtt", "mqtt.log")
        self.logger_mem = LoggerFile("mqtt_mem", "mqtt_mem.log")

        self.svr_enable = settings.MQTT_ENABLE
        self.ip = settings.MQTT_IP
        self.port = settings.MQTT_PORT
        self.device_id = settings.DEVICE_ID
        self.client_id = settings.MQTT_CLIENT_ID
        self.topic = settings.MQTT_TOPIC
        self.topic_server = settings.MQTT_TOPIC_SERVER
        self.heartbeat_enable = settings.MQTT_HEARTBEAT_ENABLE
        self.heartbeat_time = settings.MQTT_HEARTBEAT_TIME

        self.receive_queue = collections.deque()
        self.max_receive_queue_size = max(1, int(getattr(settings, "MQTT_MAX_RECEIVE_QUEUE_SIZE", DEFAULT_MAX_RECEIVE_QUEUE_SIZE)))
        self.dropped_receive_queue_count = 0
        self._queue_lock = threading.RLock()
        self._outbound_failures = 0
        self._queue_high_warned = False
        self.mqttc = None
        self.connect = False
        self.eqp_state = [-1, -1, -1, -1]
        self._reconnect_delay = 1

        self._stop_requested = False
        self._stop_lock = threading.Lock()
        self._loop = None
        self._receive_event = None
        self._stop_event = None

        # Sized executor for blocking device calls (see _run_in_cmd_executor).
        self._thread_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=CMD_EXECUTOR_MAX_WORKERS,
            thread_name_prefix="mqtt-cmd",
        )

        self.daemon = True
        self.start()

    @property
    def stop(self):
        with self._stop_lock:
            return self._stop_requested

    @stop.setter
    def stop(self, value):
        with self._stop_lock:
            self._stop_requested = bool(value)

        if self._stop_requested:
            self.connect = False
            loop = self._loop
            if loop and loop.is_running():
                try:
                    loop.call_soon_threadsafe(self._signal_stop)
                except RuntimeError:
                    pass

    def _signal_stop(self):
        if self._stop_event is not None:
            self._stop_event.set()
        if self._receive_event is not None:
            self._receive_event.set()

    def stop_and_wait(self, timeout=None):
        if threading.current_thread() is not self:
            self.stop = True
            self.join(timeout=timeout)
            if timeout is not None and self.is_alive():
                self.logger.warning(
                    f"mqtt : thread did not exit within {timeout}s during stop_and_wait"
                )
        else:
            self.stop = True
        self._shutdown_cmd_executor()

    def _run_in_cmd_executor(self, fn, *args):
        executor = getattr(self, "_thread_executor", None)
        if executor is None:
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=CMD_EXECUTOR_MAX_WORKERS,
                thread_name_prefix="mqtt-cmd",
            )
            self._thread_executor = executor
        return asyncio.get_running_loop().run_in_executor(executor, fn, *args)

    def _shutdown_cmd_executor(self):
        executor = getattr(self, "_thread_executor", None)
        if executor is None:
            return
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as err:
            self.logger.warning(f"mqtt : cmd executor shutdown error : {str(err)}")
        finally:
            self._thread_executor = None

    def _is_priority_notification(self, data):
        return isinstance(data, dict) and data.get("correlation") is not None

    def _drop_oldest_non_priority_notification(self):
        with self._queue_lock:
            for index, queued_data in enumerate(self.receive_queue):
                if not self._is_priority_notification(queued_data):
                    del self.receive_queue[index]
                    return True
            return False

    def _enqueue_notification(self, data):
        overflow_log = None
        with self._queue_lock:
            if len(self.receive_queue) >= self.max_receive_queue_size:
                dropped_priority = False
                if not self._drop_oldest_non_priority_notification():
                    dropped_priority = self._is_priority_notification(self.receive_queue[0])
                    self.receive_queue.popleft()

                self.dropped_receive_queue_count += 1
                if self.dropped_receive_queue_count == 1 or self.dropped_receive_queue_count % 100 == 0:
                    overflow_log = (
                        f"mqtt : receive_queue overflow, dropped={self.dropped_receive_queue_count}, "
                        f"max={self.max_receive_queue_size}, dropped_priority={dropped_priority}"
                    )

            self.receive_queue.append(data)

        if overflow_log:
            self.logger.warning(overflow_log)

    def _on_connect(self):
        self.logger.info(
            f"mqtt : on_connect : client_id={self.client_id}, topic={self.topic}, topic_server={self.topic_server}"
        )
        self.connect = True

    def _on_disconnect(self, reason=None):
        if self.stop:
            self.logger.info("mqtt : on_disconnect : shutdown requested")
        elif reason is not None:
            self.logger.warning(f"mqtt : on_disconnect : {reason}")
        else:
            self.logger.warning("mqtt : on_disconnect")
        self.connect = False

    def _create_client(self):
        kwargs = {
            "hostname": self.ip,
            "port": self.port,
            "identifier": self.client_id,
            "protocol": ProtocolVersion(settings.MQTT_PROTOCOL),
            "transport": settings.MQTT_TRANSPORT,
            "timeout": settings.MQTT_TIMEOUT,
            "keepalive": settings.MQTT_KEEPALIVE,
            "clean_start": settings.MQTT_CLEAN_START_FIRST_ONLY,
            "will": Will(
                self.topic_server,
                payload=json.dumps({"id": self.client_id, "status": "offline"}),
                qos=settings.MQTT_QOS,
                retain=True,
            ),
        }
        if settings.MQTT_USERNAME:
            kwargs["username"] = settings.MQTT_USERNAME
        if settings.MQTT_PASSWORD:
            kwargs["password"] = settings.MQTT_PASSWORD
        return aiomqtt.Client(**kwargs)

    @asynccontextmanager
    async def connect_MQTT_service(self):
        client = self._create_client()
        self.logger.info("mqtt : connecting to " + self.ip + " port:" + str(self.port))
        entered = False
        try:
            await client.__aenter__()
            entered = True
            self.mqttc = client
            await client.subscribe(self.topic, settings.MQTT_QOS)
            await client.subscribe(f"{self.topic}/Request", settings.MQTT_QOS)
            await client.subscribe(self.topic_server, settings.MQTT_QOS)
            await client.subscribe(f"{self.topic_server}/Process", settings.MQTT_QOS)
            await client.subscribe(f"{self.topic_server}/LRC/response", settings.MQTT_QOS)
            await client.subscribe(f"{self.topic_server}/WIP/response", settings.MQTT_QOS)
            self._on_connect()

            birth_info = {"id": self.client_id, "status": "online"}
            await client.publish(
                self.topic_server,
                json.dumps(birth_info),
                qos=settings.MQTT_QOS,
                retain=True,
                timeout=5,
            )
            yield client
        finally:
            self.mqttc = None
            if entered:
                self._on_disconnect()
                if self.stop:
                    # Graceful shutdown: the will is discarded on a clean DISCONNECT,
                    # so clear the retained "online" birth message explicitly.
                    try:
                        await client.publish(
                            self.topic_server,
                            json.dumps({"id": self.client_id, "status": "offline"}),
                            qos=settings.MQTT_QOS,
                            retain=True,
                            timeout=5,
                        )
                    except Exception as err:
                        self.logger.warning(f"mqtt : offline publish on shutdown failed : {str(err)}")
                await client.__aexit__(None, None, None)

    def on_notify(self, data):
        if self.stop:
            return

        try:
            data = copy.deepcopy(data)
        except Exception as err:
            self.logger.error(f"mqtt : on_notify : deepcopy failed : {str(err)}")
            return

        self._enqueue_notification(data)

        loop = self._loop
        event = self._receive_event
        if loop and event is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass

    def _get_correlation(self, properties):
        if properties is None:
            return None

        response_topic = getattr(properties, "ResponseTopic", None)
        correlation_data = getattr(properties, "CorrelationData", None)
        if response_topic is None or correlation_data is None:
            return None

        return MQTTCorrelation(
            ResponseTopic=str(response_topic),
            CorrelationData=correlation_data,
        )

    def _build_publish_properties(self, correlation):
        if correlation is None or correlation.CorrelationData is None:
            return None

        props = Properties(mqtt.PacketTypes.PUBLISH)
        props.CorrelationData = correlation.CorrelationData
        return props

    def publish(self, data):
        loop = self._loop
        if not self.connect or self.mqttc is None or loop is None or not loop.is_running():
            return False
        try:
            scheduled_data = copy.deepcopy(data)
            loop.call_soon_threadsafe(asyncio.create_task, self._do_publish(scheduled_data))
        except (RuntimeError, TypeError):
            return False
        return True

    async def _do_publish(self, data):
        try:
            payload = json.dumps(data)
            if "Server" in data:
                if settings.MQTT_DEBUG_ENABLE:
                    print(f"[Server]:{payload}")
                self.logger_mqtt.info(f"[Server]:{payload}")
                await self._publish(self.topic_server, payload)
            else:
                if settings.MQTT_DEBUG_ENABLE:
                    print(f"[IPC]:{payload}")
                self.logger_mqtt.info(f"[IPC]:{payload}")
                await self._publish(f"{self.topic}/LEDBoard", payload)
        except Exception as err:
            self.logger.error('Mqtt Proxy : {}'.format(str(err)))

    async def _publish(self, topic, payload, qos=None, properties=None, retain=False, wait_timeout=5):
        if not self.connect or self.mqttc is None:
            return False

        publish_qos = settings.MQTT_QOS if qos is None else qos

        try:
            await self.mqttc.publish(
                topic,
                payload,
                qos=publish_qos,
                retain=retain,
                properties=properties,
                timeout=wait_timeout,
            )
            return True
        except Exception as err:
            self.logger.error(f"mqtt : publish : topic={topic}, error={str(err)}")
            self.connect = False
            return False

    async def _handle_process_message(self, topic, qos, raw_payload, retain):
        self.logger.info(f"mqtt : on_message topic={topic}, qos={qos}, retain={retain}, data={raw_payload}")
        if retain:
            return

        payload = json.loads(raw_payload)
        port_no = payload['port_no']
        copy_payload = payload.copy()
        copy_payload['type'] = 3
        self._route_to_device(copy_payload)
        self.logger.info(f"mqtt : port_no={port_no}, process_state={payload['process_state']}")

    def _route_to_device(self, data):
        if settings.LEDBOARD2_ENABLE:
            target = self.controller.device if data["port_no"] < 3 else self.controller.device2
        else:
            target = self.controller.device
        target.on_notify(data)

    async def _handle_response_message(self, topic, qos, raw_payload):
        self.logger.info(f"mqtt : on_message topic={topic}, qos={qos}, data={raw_payload}")
        payload = json.loads(raw_payload)
        self._route_to_device(payload)

    async def _handle_ipc_message(self, topic, qos, raw_payload, retain):
        self.logger.info(f"mqtt : on_message topic={topic}, qos={qos}, retain={retain}, data={raw_payload}")
        if retain:
            return
        payload = json.loads(raw_payload)

        if 'type' in payload:
            if payload['type'] in [1, 3, 5]:
                self.logger.info(f"######## exclude ########")
                return

        if payload['type'] == 2 or payload['type'] == 4: # Place & Go message
            pass
        elif payload['type'] == 3: # Equipment message
            pass
        else:
            port_no = payload['port_no']

            if self.eqp_state[port_no] != payload['eqp_state']:
                self.eqp_state[port_no] = payload['eqp_state']
                self.logger.info(f">>>>>>>> mqtt : port_no={port_no}, eqp_state changed to {payload['eqp_state']} <<<<<<<<")
                copy_payload = payload.copy()
                copy_payload['type'] = 3
                self._route_to_device(copy_payload)

            if payload['type'] == 0 and payload['stream'] == 6 and payload['function'] == 11 and payload['code_id'] == 0 and payload['sub_id'] == 0:
                self.logger.info(f"######## exclude ########")
                return
            if payload['type'] == 0 and payload['stream'] == -1 and payload['function'] == -1 and payload['code_id'] == 0:
                self.logger.info(f"######## exclude ########")
                return
            if payload['code_id'] == 0x0071:
                if payload['mode'] == 2:
                    self.logger.info(f"######## exclude ########")
                    return
                if payload['sub_id'] not in [0, 1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23, 24, 25]:
                    self.logger.info(f"######## exclude ########")
                    return
            elif payload['code_id'] not in [0, 0x8003, 0x0080, 0x001c]:
                self.logger.info(f"######## exclude ########")
                return

        self._route_to_device(payload)

    async def _handle_request_message(self, raw_payload, properties):
        correlation = self._get_correlation(properties)
        if correlation is None:
            self.logger.warning("No reply requested")
            return

        if self.uiform is None:
            self.logger.info("mqtt : Request ignored : uiform is not available")
            return

        payload = json.loads(raw_payload)
        self.logger.info(
            f"corr_id={correlation.CorrelationData}, reply_to={correlation.ResponseTopic}, payload={payload}"
        )

        if ("cmd" not in payload) or ("port_no" not in payload):
            return

        port_no = payload["port_no"]
        try:
            await asyncio.wait_for(
                self._run_in_cmd_executor(
                    self.uiform.e84[port_no].api_request,
                    payload["cmd"],
                    payload["data"],
                    correlation,
                ),
                timeout=MAX_CMD_WAIT,
            )
        except asyncio.TimeoutError:
            self.logger.error(
                f"mqtt : timeout : api_request : port_no={port_no}, cmd={payload['cmd']}"
            )

    async def on_message(self, msg):
        topic = str(msg.topic)
        qos = getattr(msg, "qos", None)
        raw_payload = msg.payload
        properties = getattr(msg, "properties", None)
        retain = getattr(msg, "retain", False)

        try:
            if topic.endswith("Process"):
                await self._handle_process_message(topic, qos, raw_payload, retain)
            elif topic.endswith(str(self.topic)):
                await self._handle_ipc_message(topic, qos, raw_payload, retain)
            elif topic.endswith("response"):
                await self._handle_response_message(topic, qos, raw_payload)
            elif topic.endswith("Request"):
                await self._handle_request_message(raw_payload, properties)
        except Exception as err:
            self.logger.error(f"mqtt : on_message : {str(err)}")

    async def data_process(self, data):
        try:
            payload_data = copy.copy(data)

            if "cmd" in payload_data:
                correlation = payload_data.get("correlation")
                if correlation is None or not hasattr(correlation, "ResponseTopic"):
                    self.logger.warning("mqtt : data_process : response dropped, missing correlation")
                    return True
                props = self._build_publish_properties(correlation)
                reply_to = correlation.ResponseTopic
                del payload_data["correlation"]
                payload = json.dumps(payload_data)
                self.logger.info(
                    f"Sending response {payload_data['result']} on '{reply_to}': {correlation.CorrelationData}"
                )
                return await self._publish(reply_to, payload, qos=1, properties=props, wait_timeout=5)

            payload = json.dumps(payload_data)
            if "device_id" in payload_data:
                if not await self._publish(self.topic_server, payload):
                    return False

            pattern = r'"device_id":\s*".+?",?\s*'
            no_deviceid_payload = re.sub(pattern, '', payload)
            return await self._publish(self.topic, no_deviceid_payload)
        except Exception as err:
            self.logger.error(f"mqtt : data_process : {str(err)}")
            return False

    async def memory_check(self):
        if not self.svr_enable:
            return

        try:
            with self._queue_lock:
                queue_len = len(self.receive_queue)
            self.logger_mem.info(
                f"mqtt : memory_check : receive_queue = {queue_len}, "
                f"dropped_receive_queue = {self.dropped_receive_queue_count}, "
                f"max_receive_queue = {self.max_receive_queue_size}"
            )
        except Exception as err:
            self.logger_mem.error(f"mqtt : memory_check : {str(err)}")

    async def heartbeat(self):
        with self._queue_lock:
            queue_depth = len(self.receive_queue)
        # Edge-triggered so a prolonged outage yields one warning on the way up
        # and one recovery line, instead of an alert storm every heartbeat cycle.
        high = queue_depth > 0.8 * self.max_receive_queue_size
        was_high = getattr(self, "_queue_high_warned", False)
        if high and not was_high:
            self._queue_high_warned = True
            self.logger.warning(
                f"mqtt : receive_queue depth={queue_depth}/{self.max_receive_queue_size} "
                f"(>80% full, drops imminent if this keeps growing)"
            )
        elif not high and was_high:
            self._queue_high_warned = False
            self.logger.info(
                f"mqtt : receive_queue depth={queue_depth}/{self.max_receive_queue_size} "
                f"(recovered below 80%)"
            )

        if not self.heartbeat_enable or not self.connect:
            return False

        try:
            data = {
                "device_id": self.device_id,
                "type": 0,
                "stream": 1,
                "function": 1,
                "occurred_at": time.time(),
            }
            payload = json.dumps(data)

            if await self._publish(self.topic_server, payload):
                self.logger_heartbeat.info("alive")
                return True
            return False
        except Exception as err:
            self.logger.error(f"mqtt : heartbeat : {str(err)}")
            return False

    async def _wait_for_stop(self):
        while not self.stop:
            await asyncio.sleep(0.1)

    async def _message_loop(self):
        try:
            async for message in self.mqttc.messages:
                await self.on_message(message)
        finally:
            self.connect = False

    async def _watch_connection(self):
        # Completes when the connection is flagged lost (e.g. a publish failed
        # while TCP is still alive) so the supervisor can tear down and reconnect.
        while not self.stop and self.connect:
            # Runs on the same event loop as _message_loop/_outbound_loop, so a
            # wedged synchronous call in either of those stalls this too - a
            # reliable proxy for "is the MQTT event loop still alive at all".
            # (While disconnected, _run_async keeps the same name alive.)
            gyro_watchdog.touch("MQTTSvc", max_gap=MQTT_WATCHDOG_MAX_GAP)
            await asyncio.sleep(0.2)

    async def _outbound_loop(self):
        while not self.stop:
            if not self.connect:
                await asyncio.sleep(0.5)
                continue

            with self._queue_lock:
                if not self.receive_queue:
                    empty = True
                else:
                    empty = False
                    data = self.receive_queue.popleft()

            if empty:
                await self._receive_event.wait()
                self._receive_event.clear()
                continue

            requeued = False
            try:
                if not self.svr_enable:
                    await asyncio.sleep(0.1)
                    continue

                if await self.data_process(data):
                    self._outbound_failures = 0
                    continue

                if not self.connect:
                    with self._queue_lock:
                        self.receive_queue.appendleft(data)
                    requeued = True
                    raise aiomqtt.MqttError("mqtt : connection lost while publishing")

                if self._requeue_failed_notification(data):
                    requeued = True
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                # A cancellation inside the pop+process window (e.g. the supervisor
                # tearing down on a disconnect) must not lose the notification:
                # put it back at the front of the queue before re-raising.
                if not requeued:
                    with self._queue_lock:
                        self.receive_queue.appendleft(data)
                raise

    def _requeue_failed_notification(self, data):
        """Requeue a failed outbound notification or drop it when retries are exhausted.

        Returns True if the notification was requeued, False if it was dropped.
        """
        self._outbound_failures += 1
        if self._outbound_failures >= MAX_OUTBOUND_RETRIES:
            self._outbound_failures = 0
            self.dropped_receive_queue_count += 1
            self.logger.error(
                f"mqtt : outbound notification dropped after {MAX_OUTBOUND_RETRIES} "
                "consecutive publish failures"
            )
            return False
        with self._queue_lock:
            self.receive_queue.append(data)
        return True

    async def _periodic_task(self, interval, callback):
        while not self.stop:
            await asyncio.sleep(interval)
            if self.stop:
                return

            try:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as err:
                self.logger.error(f"mqtt : periodic task : {str(err)}")

    def _backoff_wait_seconds(self, delay):
        # Randomized backoff spreads reconnect attempts after a broker outage
        # so many devices do not reconnect in lockstep (thundering herd).
        return min(delay + random.uniform(0, delay), MAX_RECONNECT_DELAY)

    async def _run_async(self):
        self._stop_event = asyncio.Event()
        if not self.svr_enable:
            self.logger.info("mqtt : service is disabled, not connecting")
            return

        # Periodic tasks (heartbeat, memory_check) are owned by the service
        # supervisor, not the per-connection block, so a broker reconnect does
        # not restart their cadence from zero. Their callbacks skip publishing
        # while self.connect is False (see heartbeat/memory_check), so a flapping
        # broker cannot starve the heartbeat indefinitely.
        periodic_tasks = [
            asyncio.create_task(self._periodic_task(20, self.memory_check))
        ]
        if self.heartbeat_enable:
            periodic_tasks.append(
                asyncio.create_task(self._periodic_task(self.heartbeat_time, self.heartbeat))
            )

        attempt = 0
        down_since = None
        try:
            while not self.stop:
                # Outside the connected phase neither _watch_connection nor any
                # other task runs, so keep the watchdog alive from the reconnect
                # loop itself; otherwise a legitimate broker outage would look
                # like a stalled MQTTSvc thread after MQTT_WATCHDOG_MAX_GAP.
                gyro_watchdog.touch("MQTTSvc", max_gap=MQTT_WATCHDOG_MAX_GAP)
                delay = self._reconnect_delay
                attempt += 1
                try:
                    async with self.connect_MQTT_service():
                        if down_since is not None:
                            downtime = time.monotonic() - down_since
                            self.logger.info(
                                f"mqtt : reconnected to broker after {attempt} attempt(s), "
                                f"downtime={downtime:.1f}s"
                            )
                        attempt = 0
                        down_since = None
                        self._reconnect_delay = 1
                        self._receive_event = asyncio.Event()
                        with self._queue_lock:
                            has_pending = bool(self.receive_queue)
                        if has_pending:
                            self._receive_event.set()

                        tasks = [
                            asyncio.create_task(self._wait_for_stop()),
                            asyncio.create_task(self._message_loop()),
                            asyncio.create_task(self._outbound_loop()),
                            asyncio.create_task(self._watch_connection()),
                        ]

                        done, pending = await asyncio.wait(
                            tasks,
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        for task in pending:
                            task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)

                        for task in done:
                            if task.cancelled():
                                continue
                            err = task.exception()
                            if err is not None and not self.stop:
                                raise err
                except aiomqtt.MqttError as err:
                    if down_since is None:
                        down_since = time.monotonic()
                    downtime = time.monotonic() - down_since
                    if attempt in (5, 20, 60) or downtime > 300:
                        self.logger.error(
                            f"mqtt : broker still unreachable after {attempt} attempt(s) / "
                            f"{downtime:.0f}s downtime (ip={self.ip}, port={self.port}): {err}"
                        )
                    else:
                        self.logger.warning(f"mqtt : connect_MQTT_service : attempt={attempt} : {err}")
                except Exception as err:
                    self.logger.error(f"mqtt : run : {str(err)}", exc_info=True)
                finally:
                    self._receive_event = None

                if not self.stop:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self._backoff_wait_seconds(delay))
                    except asyncio.TimeoutError:
                        pass
                    self._reconnect_delay = min(delay * 2, MAX_RECONNECT_DELAY)
        finally:
            for task in periodic_tasks:
                task.cancel()
            await asyncio.gather(*periodic_tasks, return_exceptions=True)

    def run(self):
        if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
            self._loop = asyncio.WindowsSelectorEventLoopPolicy().new_event_loop()
        else:
            self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_async())
        finally:
            gyro_watchdog.unregister("MQTTSvc")
            self._loop.close()
            self._shutdown_cmd_executor()
