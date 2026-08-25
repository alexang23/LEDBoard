# Design: Port mqtt_svc.py Business Logic to mqtt_svc2.py

Date: 2026-08-26
Status: Approved (design phase)

## Objective Description

`mqtt_svc2.py` (aiomqtt/async) is the service actually wired into this project
(`controller.py:10`), but its message-handling logic targets a loadport/e84
controller API that does not exist here (`controller.loadport` is empty; no
`.e84`, `.rfid`; no `uiform` passed), and it references settings that do not
exist in `config.py` (`RFID_DEVICE_ONLY`, `SERVER_UPLOAD_ALL`, `WAFER_TYPE`),
so inbound messages are dropped and outbound notifications fail with
`AttributeError`. It also lacks the `publish()` method that `device.py` calls.

The proven business logic lives in `mqtt_svc.py` (paho/sync, currently
unwired). This port moves that logic into `mqtt_svc2.py` while keeping v2's
async infrastructure (bounded queue, retries, backoff reconnect, LWT/birth,
watchdog, executor timeouts).

Decisions made with the developer:

- **Full replace** of v2's loadport/e84 handlers with old device-routing logic.
- **Request topic**: keep subscription + handler as a **guarded no-op**
  (`uiform is None` -> log and ignore).
- **Approach A**: faithful port onto v2 infrastructure.

## Runtime Context (facts driving the design)

- `controller.py` constructs `MQTTSvc(self, self.tsc_logger)` — `uiform=None`.
- `Controller` exposes `device` / `device2` (`LEDButton`) and empty `loadport`.
- `device.py` calls `self.mqtt_svc.publish(data)` from its own thread and
  expects a boolean return.
- Inbound data flow: broker -> handlers -> `device.on_notify(payload)`
  (appends to device cmd queue). Outbound: `device.publish(...)` -> broker.
- Relevant config flags that DO exist: `LEDBOARD2_ENABLE`, `MQTT_DEBUG_ENABLE`,
  `MQTT_QOS`, `MEMORY_CHECK`, heartbeat settings.

## Change List

- `mqtt_svc2.py` — only file modified.

## Detailed Design

### 1. Inbound handling

`on_message(msg)` dispatches by topic suffix, same order as old code:

| Topic ends with | Handler |
|---|---|
| `"Process"` | `_handle_process_message` |
| `self.topic` ("IPC") | `_handle_ipc_message` |
| `"response"` | `_handle_response_message` |
| `"Request"` | `_handle_request_message` |

All handlers run inline on the event loop (JSON parse + deque append only).
Logs use topic/qos/retain/data — the old logs referenced `msg.state`, which
neither paho CallbackAPIVersion.VERSION2 nor aiomqtt messages expose.

**`_handle_process_message(topic, qos, raw_payload, retain)`**

1. Log. 2. Skip if `retain`. 3. Parse JSON. 4. `copy_payload = payload.copy()`;
   `copy_payload['type'] = 3`. 5. Route via `_route_to_device(copy_payload)`.
6. Log `port_no`, `process_state`.

**`_route_to_device(data)`** (shared helper):

```python
if settings.LEDBOARD2_ENABLE:
    target = self.controller.device if data["port_no"] < 3 else self.controller.device2
else:
    target = self.controller.device
target.on_notify(data)
```

**`_handle_ipc_message(topic, qos, raw_payload, retain)`**

1. Log. 2. Skip if `retain`. 3. Parse JSON.
4. If `'type' in payload` and `payload['type'] in [1, 3, 5]` -> log
   "exclude", return.
5. Branch on type:
   - `type in (2, 4)` (Place & Go) or `type == 3` (Equipment): no filtering,
     fall through to step 7.
   - else (type 0):
     - eqp_state tracking: `port_no = payload['port_no']`; if
       `self.eqp_state[port_no] != payload['eqp_state']`: update array, log
       banner, route a `type=3` copy immediately.
     - Exclude if `type==0 and stream==6 and function==11 and code_id==0 and sub_id==0`.
     - Exclude if `type==0 and stream==-1 and function==-1 and code_id==0`.
     - `code_id == 0x0071`: exclude if `mode == 2`; exclude if
       `sub_id not in [0..7, 20..25]`.
     - elif `code_id not in [0, 0x8003, 0x0080, 0x001c]` -> exclude.
7. Route original payload via `_route_to_device(payload)`.

`self.eqp_state = [-1, -1, -1, -1]` initialized in `__init__`.

**`_handle_response_message(topic, qos, raw_payload)`**

Log, parse, `_route_to_device(payload)`.

**`_handle_request_message(raw_payload, properties)`**

1. `correlation = self._get_correlation(properties)`; None -> warn
   "No reply requested", return.
2. Guarded no-op: if `self.uiform is None` -> info log, return.
3. Parse JSON; require `'cmd'` and `'port_no'`; run
   `self.uiform.e84[port_no].api_request(payload['cmd'], payload['data'], correlation)`
   via `_run_in_cmd_executor` under `asyncio.wait_for(MAX_CMD_WAIT)`.
   (`MQTTCorrelation` exposes `ResponseTopic`/`CorrelationData`, matching what
   the old raw MQTT5 properties provided.)

### 2. Outbound publishing

**New sync `publish(data)`** — called by `device.py` from its own thread:

1. Return `False` if not connected (`self.connect`) or client/loop missing.
2. Schedule fire-and-forget:
   `loop.call_soon_threadsafe(asyncio.create_task, self._do_publish(data))`
   wrapped in try/except (`RuntimeError` -> return False); return `True`.
   Mirrors old non-blocking paho publish semantics (old never waited).
3. `_do_publish(data)` coroutine:
   - `'Server' in data`: JSON dump; `MQTT_DEBUG_ENABLE` print + `logger_mqtt`
     `[Server]:{payload}`; `await self._publish(self.topic_server, payload)`.
   - else: JSON dump; debug print + `logger_mqtt` `[IPC]:{payload}`;
     `await self._publish(f"{self.topic}/LEDBoard", payload)`.
   - Exceptions caught -> `logger.error('Mqtt Proxy : {err}')`.

**Rewritten async `data_process(data)`** (queued path via `on_notify` ->
`_outbound_loop`; retry/requeue semantics unchanged):

1. `'cmd' in data`: correlation missing -> warn + return True. Else
   props = `_build_publish_properties(correlation)`,
   `reply_to = correlation.ResponseTopic`, delete `'correlation'` key, JSON
   dump, info log `Sending response {result} on '{reply_to}'`, return
   `await _publish(reply_to, payload, qos=1, properties=props, wait_timeout=5)`.
2. Else `payload = json.dumps(data)`:
   - if `'device_id' in data` -> `await _publish(self.topic_server, payload)`.
   - always: strip device_id via regex `"device_id":\s*".+?",?\s*`
     -> `return await _publish(self.topic, stripped)`.

The dead HTTP-POST tail after `return True` in old `data_process` is NOT
ported. `MQTTCorrelation`, `_get_correlation`, `_build_publish_properties`
are kept (used by both paths).

### 3. Subscriptions

On connect, all at `settings.MQTT_QOS`:

- `{topic}`
- `{topic}/Request`
- `{topic_server}`
- `{topic_server}/Process`
- `{topic_server}/LRC/response`
- `{topic_server}/WIP/response`

Dropped vs current v2: `{topic}/LEDBoard` (own loopback; old never subscribed),
`$SYS/broker/log/N`.

### 4. Removals

`_handle_ledboard_message`, `_handle_broker_log`, `_run_e84_cmd`,
`_publish_rfid_status`, `BROKER_LOG_POLL_DEBOUNCE_SECONDS`,
`_last_broker_poll_time`; settings references `CLAMP_ENABLE`,
`LEDBOARD_ENABLE`, `RFID_DEVICE_ONLY`, `SERVER_UPLOAD_ALL`, `WAFER_TYPE`.

### 5. Kept v2 infrastructure (intentional deviations from old)

- Bounded receive queue, overflow drop accounting, high-water warning.
- Exponential backoff reconnect with jitter; downtime logging.
- Watchdog integration (`gyro_watchdog`, `MQTT_WATCHDOG_MAX_GAP`).
- Heartbeat / memory_check periodic tasks owned by the supervisor.
- Bounded command executor + `MAX_CMD_WAIT` timeouts.
- Thread-safe `stop` property, `stop_and_wait()`.
- LWT/birth/offline presence on `topic_server` (retained
  `{"id": client_id, "status": "online"/"offline"}`). NOTE: the old service
  never published presence messages; upstream will start seeing these
  retained payloads. Accepted by developer during design review.

### 6. Error handling

Per-handler try/except logging in the existing `mqtt : <context> : {err}`
style; malformed JSON is caught by the outer `on_message` handler; retained
messages skipped for Process/IPC; publish failure sets `connect=False` which
triggers supervisor teardown/reconnect (existing behavior).

## Verification Steps

1. Check uv environment has required packages (no new dependencies needed;
   aiomqtt already used). Do not install unrelated packages.
2. `uv run python LEDBoard.py`:
   - Expected even without a broker: clean startup — controller spawns
     MQTTSvc thread, retry/backoff warnings logged, no import/AttributeError
     from ported code paths.
   - If broker reachable at `MQTT_IP:MQTT_PORT`: connect + birth message +
     subscribe logs confirm wiring; publish a test Process/IPC message to
     observe `device.on_notify` routing in logs.
