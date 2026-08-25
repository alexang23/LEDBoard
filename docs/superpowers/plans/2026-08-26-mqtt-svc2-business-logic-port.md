# Port mqtt_svc.py Business Logic to mqtt_svc2.py — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mqtt_svc2.py's loadport/e84 message-handling logic with mqtt_svc.py's proven business logic (device/device2 routing, SECS filtering, legacy publish routing) while keeping v2's async infrastructure.

**Architecture:** Single-file modification of `C:\gyro\LEDButton\mqtt_svc2.py`. Inbound MQTT messages route through four handlers mirroring mqtt_svc.py's `on_message`; outbound gets a new thread-safe sync `publish()` bridge plus a rewritten `data_process()`. All v2 infrastructure (bounded queue, backoff reconnect, watchdog, LWT/birth, bounded executor) is preserved. Spec: `docs/superpowers/specs/2026-08-26-mqtt-svc2-business-logic-port-design.md`.

**Tech Stack:** Python >=3.14 under uv, aiomqtt>=2.5.1, pydantic v1 settings. No new dependencies. No test framework exists in this project — verification uses throwaway assertion scripts run under `uv run python` from `%TEMP%\opencode\mqtt_port_tests\` (outside the repo), plus `py_compile` and a full-app smoke run.

## Global Constraints

- Modify ONLY `C:\gyro\LEDButton\mqtt_svc2.py`. Never touch `controller.py`, `device.py`, `config.py`, or `mqtt_svc.py`.
- Do not install any packages. Run every Python command through uv: `uv run python ...`.
- Temp verification scripts live in `C:\Users\MyUser\AppData\Local\Temp\opencode\mqtt_port_tests\` (pre-create it; never commit them).
- Conventional Commits, scope `mqtt` (e.g., `feat(mqtt): ...`). Stage only `mqtt_svc2.py`.
- No new code comments in `mqtt_svc2.py` (log strings are fine; they are runtime output, not comments).
- Preserve v2 infrastructure unchanged: bounded receive queue/retries, exponential backoff, `gyro_watchdog`, LWT/birth/offline presence, command executor, `stop_and_wait`.
- After the port, `mqtt_svc2.py` must reference ONLY settings that exist in `config.py` (`LEDBOARD2_ENABLE`, `MQTT_DEBUG_ENABLE`, `MQTT_ENABLE`, `MQTT_QOS`, `MEMORY_CHECK`, heartbeat/topic/client credentials). Forbidden afterward: `RFID_DEVICE_ONLY`, `SERVER_UPLOAD_ALL`, `WAFER_TYPE`, `CLAMP_ENABLE`, `LEDBOARD_ENABLE`, `loadport`, `rfid`, `$SYS/broker/log/N`.
- Line numbers below refer to current HEAD (`7d9f63c`..`33ec283`); locate code by symbol names, they shift between tasks.

---

### Task 1: Sync `publish()` bridge (fixes device.py's missing dependency)

**Files:**
- Modify: `mqtt_svc2.py` (add two methods directly after `_build_publish_properties`, ~line 312)
- Test: `%TEMP%\opencode\mqtt_port_tests\t1_publish.py`

**Interfaces:**
- Consumes: existing `_publish(topic, payload, qos=None, properties=None, retain=False, wait_timeout=5)` coroutine; `self.connect`; `self.mqttc`; `self.topic`; `self.topic_server`; `self._loop`; `settings.MQTT_DEBUG_ENABLE`; `self.logger_mqtt`.
- Produces: `publish(self, data) -> bool` (sync, called from device threads; True = scheduled); `_do_publish(self, data)` coroutine (fire-and-forget send; `'Server'` key -> `topic_server`, else -> `{topic}/LEDBoard`).

- [ ] **Step 1: Write the failing verification script**

Create `%TEMP%\opencode\mqtt_port_tests\t1_publish.py`:

```python
import asyncio
import json
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace as NS

REPO = Path(r"C:\gyro\LEDButton")
sys.path.insert(0, str(REPO))
import mqtt_svc2 as m


class Rec:
    def __init__(self):
        self.got = []
    def on_notify(self, d):
        self.got.append(d)


class FakeLogger:
    def info(self, *a, **k):
        pass
    def warning(self, *a, **k):
        pass
    def error(self, *a, **k):
        pass


class FakeClient:
    def __init__(self):
        self.published = []
    async def publish(self, topic, payload=None, qos=None, retain=False, properties=None, timeout=None):
        self.published.append((topic, payload, qos, properties))


def make_svc(**over):
    svc = m.MQTTSvc.__new__(m.MQTTSvc)
    svc.logger = FakeLogger()
    svc.logger_mqtt = FakeLogger()
    svc.logger_heartbeat = FakeLogger()
    svc.controller = NS(device=Rec(), device2=Rec())
    svc.uiform = None
    svc.eqp_state = [-1, -1, -1, -1]
    svc.topic = "IPC"
    svc.topic_server = "Server"
    svc.connect = True
    svc.mqttc = FakeClient()
    svc._loop = None
    for k, v in over.items():
        setattr(svc, k, v)
    return svc


failures = []


def check(name, cond):
    if cond:
        print(f"PASS {name}")
    else:
        failures.append(name)
        print(f"FAIL {name}")


svc = make_svc(connect=False)
check("disconnected publish returns False", svc.publish({"port_no": 1}) is False)

loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()

svc = make_svc(_loop=loop)
data = OrderedDict([("port_no", 1), ("dual_port", 0), ("ledboard_state", 1)])
check("ipc publish returns True", svc.publish(data) is True)
time.sleep(0.3)
got = svc.mqttc.published
check("ipc publish delivered one frame", len(got) == 1)
if got:
    topic, payload, qos, _props = got[0]
    check("ipc publish topic", topic == "IPC/LEDBoard")
    check("ipc publish payload roundtrip", json.loads(payload)["port_no"] == 1)
    check("ordereddict serializable", isinstance(json.loads(payload), dict))

svc2 = make_svc(_loop=loop)
check("server publish returns True", svc2.publish({"Server": 1, "x": 2}) is True)
time.sleep(0.3)
check("server publish topic", svc2.mqttc.published and svc2.mqttc.published[0][0] == "Server")

loop.call_soon_threadsafe(loop.stop)
if failures:
    sys.exit(1)
print("ALL PASS")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t1_publish.py"`
Expected: FAIL / AttributeError — `MQTTSvc` object has no attribute `publish`.

- [ ] **Step 3: Implement**

In `mqtt_svc2.py`, insert immediately after `_build_publish_properties` (after ~line 312):

```python
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
```

- [ ] **Step 4: Run script to verify it passes**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t1_publish.py"`
Expected: every `PASS` line, final `ALL PASS`, exit code 0.

- [ ] **Step 5: Compile check**

Run: `uv run python -m py_compile mqtt_svc2.py`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add mqtt_svc2.py
git commit -m "feat(mqtt): add thread-safe publish bridge for device outbound state"
```

---

### Task 2: Process/response inbound handlers + shared router

**Files:**
- Modify: `mqtt_svc2.py` — `__init__` (add `eqp_state` near line 78); replace `_handle_process_message` (lines 355-376, the CLAMP/loadport version dies here); add `_route_to_device` and `_handle_response_message`; update `on_message` Process/response dispatch (lines 529-545).
- Test: `%TEMP%\opencode\mqtt_port_tests\t2_inbound.py`

**Interfaces:**
- Consumes: `settings.LEDBOARD2_ENABLE`; `self.controller.device` / `.device2` objects exposing `on_notify(data)`.
- Produces: `_route_to_device(self, data)`; `_handle_process_message(self, topic, qos, raw_payload, retain)` (async); `_handle_response_message(self, topic, qos, raw_payload)` (async); instance attr `self.eqp_state` = `[-1, -1, -1, -1]`. Later tasks reuse all three methods and the attr.

- [ ] **Step 1: Write the failing verification script**

Create `%TEMP%\opencode\mqtt_port_tests\t2_inbound.py`:

```python
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

REPO = Path(r"C:\gyro\LEDButton")
sys.path.insert(0, str(REPO))
import mqtt_svc2 as m


class Rec:
    def __init__(self):
        self.got = []
    def on_notify(self, d):
        self.got.append(d)


class FakeLogger:
    def info(self, *a, **k):
        pass
    def warning(self, *a, **k):
        pass
    def error(self, *a, **k):
        pass


def make_svc():
    svc = m.MQTTSvc.__new__(m.MQTTSvc)
    svc.logger = FakeLogger()
    svc.logger_mqtt = FakeLogger()
    svc.logger_heartbeat = FakeLogger()
    svc.device = Rec()
    svc.device2 = Rec()
    svc.controller = NS(device=svc.device, device2=svc.device2)
    svc.uiform = None
    svc.eqp_state = [-1, -1, -1, -1]
    svc.topic = "IPC"
    svc.topic_server = "Server"
    svc.connect = True
    return svc


failures = []


def check(name, cond):
    if cond:
        print(f"PASS {name}")
    else:
        failures.append(name)
        print(f"FAIL {name}")


async def main():
    m.settings.LEDBOARD2_ENABLE = False
    svc = make_svc()

    await svc._handle_process_message("Server/Process", 0,
                                      b'{"port_no":2,"process_state":"run"}', False)
    check("process routed to device", len(svc.controller.device.got) == 1)
    if svc.controller.device.got:
        d = svc.controller.device.got[0]
        check("process type forced to 3", d.get("type") == 3)
        check("process port preserved", d.get("port_no") == 2)

    await svc._handle_process_message("Server/Process", 0,
                                      b'{"port_no":2,"process_state":"run"}', True)
    check("process retained skipped", len(svc.controller.device.got) == 1)

    m.settings.LEDBOARD2_ENABLE = True
    svc2 = make_svc()
    await svc2._handle_process_message("Server/Process", 0,
                                       b'{"port_no":4,"process_state":"stop"}', False)
    check("board2 routing: high port to device2",
          len(svc2.controller.device.got) == 0 and len(svc2.controller.device2.got) == 1)
    await svc2._handle_process_message("Server/Process", 0,
                                       b'{"port_no":1,"process_state":"stop"}', False)
    check("board2 routing: low port to device", len(svc2.controller.device.got) == 1)
    m.settings.LEDBOARD2_ENABLE = False

    svc3 = make_svc()
    await svc3._handle_response_message("Server/LRC/response", 0,
                                        b'{"port_no":1,"result":"OK"}')
    check("response routed", len(svc3.controller.device.got) == 1)

    msg = NS(topic="Server/Process", qos=0,
             payload=b'{"port_no":2,"process_state":"run"}', retain=False,
             properties=None)
    svc4 = make_svc()
    await svc4.on_message(msg)
    check("on_message dispatches Process", len(svc4.controller.device.got) == 1)

    msg = NS(topic="Server/WIP/response", qos=0,
             payload=b'{"port_no":2,"eqp_state":1}', retain=False, properties=None)
    svc5 = make_svc()
    await svc5.on_message(msg)
    check("on_message dispatches response", len(svc5.controller.device.got) == 1)


asyncio.run(main())
if failures:
    sys.exit(1)
print("ALL PASS")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t2_inbound.py"`
Expected: FAIL — `_handle_process_message() missing required positional argument` (current signature lacks `retain`) or AttributeError on missing methods.

- [ ] **Step 3: Implement**

3a. In `__init__`, after the line `self.connect = False` (~line 77), add:

```python
        self.eqp_state = [-1, -1, -1, -1]
```

3b. Replace the entire `_handle_process_message` method (lines 355-376) with:

```python
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
```

3c. Directly after it add two new methods:

```python
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
```

3d. In `on_message`, change the dispatch to extract retain once and route Process/response; leave the other branches untouched for now:

```python
    async def on_message(self, msg):
        topic = str(msg.topic)
        qos = getattr(msg, "qos", None)
        raw_payload = msg.payload
        properties = getattr(msg, "properties", None)
        retain = getattr(msg, "retain", False)

        try:
            if topic.endswith("Process"):
                await self._handle_process_message(topic, qos, raw_payload, retain)
            elif topic.endswith("LEDBoard"):
                await self._handle_ledboard_message(topic, qos, raw_payload)
            elif topic.endswith("response"):
                await self._handle_response_message(topic, qos, raw_payload)
            elif topic.endswith("Request"):
                await self._handle_request_message(raw_payload, properties)
            elif topic.startswith("$SYS/broker/log/N"):
                await self._handle_broker_log(raw_payload)
        except Exception as err:
            self.logger.error(f"mqtt : on_message : {str(err)}")
```

- [ ] **Step 4: Run script to verify it passes**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t2_inbound.py"`
Expected: all PASS, `ALL PASS`, exit 0.

- [ ] **Step 5: Compile check**

Run: `uv run python -m py_compile mqtt_svc2.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add mqtt_svc2.py
git commit -m "feat(mqtt): route Process and response messages to LEDBoard devices"
```

---

### Task 3: IPC handler — eqp_state tracking + SECS filtering

**Files:**
- Modify: `mqtt_svc2.py` — add `_handle_ipc_message` (place directly after `_handle_response_message`); swap the `endswith("LEDBoard")` dispatch branch in `on_message`.
- Test: `%TEMP%\opencode\mqtt_port_tests\t3_ipc.py`

**Interfaces:**
- Consumes: `_route_to_device(data)` and `self.eqp_state` from Task 2.
- Produces: `_handle_ipc_message(self, topic, qos, raw_payload, retain)` (async). The `on_message` branch becomes `elif topic.endswith(str(self.topic)):` -> `_handle_ipc_message`.

- [ ] **Step 1: Write the failing verification script**

Create `%TEMP%\opencode\mqtt_port_tests\t3_ipc.py`:

```python
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

REPO = Path(r"C:\gyro\LEDButton")
sys.path.insert(0, str(REPO))
import mqtt_svc2 as m


class Rec:
    def __init__(self):
        self.got = []
    def on_notify(self, d):
        self.got.append(d)


class FakeLogger:
    def info(self, *a, **k):
        pass
    def warning(self, *a, **k):
        pass
    def error(self, *a, **k):
        pass


def make_svc():
    svc = m.MQTTSvc.__new__(m.MQTTSvc)
    svc.logger = FakeLogger()
    svc.device = Rec()
    svc.controller = NS(device=svc.device)
    svc.eqp_state = [-1, -1, -1, -1]
    svc.topic = "IPC"
    return svc


failures = []


def check(name, cond):
    if cond:
        print(f"PASS {name}")
    else:
        failures.append(name)
        print(f"FAIL {name}")


async def run_payload(payload, retain=False):
    svc = make_svc()
    await svc._handle_ipc_message("IPC", 0,
                                  bytes(json.dumps(payload), "utf-8"), retain)
    return svc


FULL = {"stream": 1, "function": 1, "sub_id": 0, "mode": 1}

# Counting rules (faithful to mqtt_svc.py): a type-0 message on a fresh svc
# always changes eqp_state (-1 -> value), emitting ONE type-3 copy BEFORE the
# SECS exclusions; an excluded message therefore delivers exactly 1, a fully
# routed one exactly 2. type in {1,3,5} is excluded before everything (the
# Equipment elif in mqtt_svc.py is unreachable for type 3), delivering 0.
check("whitelisted code_id routed (copy+final)",
      len(asyncio.run(run_payload(dict(type=0, port_no=0, eqp_state=1, code_id=0x8003, **FULL))).device.got) == 2)
check("type 1 excluded",
      len(asyncio.run(run_payload(dict(type=1, port_no=0, eqp_state=1))).device.got) == 0)
check("place&go type 2 passthrough",
      len(asyncio.run(run_payload(dict(type=2, port_no=0, eqp_state=1))).device.got) == 1)
check("place&go type 4 passthrough",
      len(asyncio.run(run_payload(dict(type=4, port_no=0, eqp_state=1))).device.got) == 1)
check("type 3 excluded like mqtt_svc.py",
      len(asyncio.run(run_payload(dict(type=3, port_no=0, eqp_state=1))).device.got) == 0)
check("s6f11 excluded (eqp copy only)",
      len(asyncio.run(run_payload(dict(type=0, port_no=0, eqp_state=1, stream=6, function=11,
                           code_id=0, sub_id=0))).device.got) == 1)
check("stream/function -1 excluded (eqp copy only)",
      len(asyncio.run(run_payload(dict(type=0, port_no=0, eqp_state=1, stream=-1, function=-1,
                           code_id=0, sub_id=0))).device.got) == 1)
check("code 0x71 mode 2 excluded (eqp copy only)",
      len(asyncio.run(run_payload(dict(type=0, port_no=0, eqp_state=1, code_id=0x0071,
                           mode=2, sub_id=1, stream=1, function=1))).device.got) == 1)
check("code 0x71 bad sub excluded (eqp copy only)",
      len(asyncio.run(run_payload(dict(type=0, port_no=0, eqp_state=1, code_id=0x0071,
                           mode=1, sub_id=9, stream=1, function=1))).device.got) == 1)
check("code 0x71 good sub routed (copy+final)",
      len(asyncio.run(run_payload(dict(type=0, port_no=0, eqp_state=1, code_id=0x0071,
                           mode=1, sub_id=21, stream=1, function=1))).device.got) == 2)
check("unknown code excluded (eqp copy only)",
      len(asyncio.run(run_payload(dict(type=0, port_no=0, eqp_state=1, code_id=0x1234,
                           sub_id=0, mode=1, stream=1, function=1))).device.got) == 1)
check("retained skipped",
      len(asyncio.run(run_payload({"type": 2, "port_no": 1}, retain=True)).device.got) == 0)


async def eqp_repeat_case():
    svc = make_svc()
    pl = bytes(json.dumps(dict(type=0, port_no=1, eqp_state=7, code_id=0x8003,
                               stream=1, function=1, sub_id=0, mode=1)), "utf-8")
    await svc._handle_ipc_message("IPC", 0, pl, False)
    n_first = len(svc.device.got)
    await svc._handle_ipc_message("IPC", 0, pl, False)
    return svc, n_first


svc_r, n_first = asyncio.run(eqp_repeat_case())
check("eqp change emitted one extra type-3 copy", n_first == 2)
check("eqp repeat emits only final routing", len(svc_r.device.got) == 3)
check("eqp state updated", svc_r.eqp_state[1] == 7)

msg = NS(topic="IPC", qos=0, retain=False, properties=None,
         payload=b'{"type":2,"port_no":1,"code_id":1}')
svc_d = make_svc()
asyncio.run(svc_d.on_message(msg))
check("on_message dispatches IPC via endswith(topic)", len(svc_d.device.got) == 1)

if failures:
    sys.exit(1)
print("ALL PASS")
```

Counting rules recap (all derived from mqtt_svc.py's exact ordering): eqp_state-change copy fires before the SECS exclusion checks, so excluded-but-state-changing type-0 messages deliver exactly 1 frame; fully-routed type-0 messages deliver 2; `type ∈ {1,3,5}` short-circuits to 0 (the later `elif payload['type'] == 3` Equipment branch is unreachable in mqtt_svc.py itself and is ported verbatim); type 2/4 bypass filtering entirely (no eqp tracking, 1 frame).

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t3_ipc.py"`
Expected: FAIL / AttributeError — no attribute `_handle_ipc_message`.

- [ ] **Step 3: Implement**

3a. Add directly after `_handle_response_message`:

```python
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
```

(The two trailing comments `# Place & Go message` / `# Equipment message` are ported verbatim from mqtt_svc.py lines 149/151.)

3b. In `on_message`, replace the LEDBoard branch line pair

```python
            elif topic.endswith("LEDBoard"):
                await self._handle_ledboard_message(topic, qos, raw_payload)
```

with

```python
            elif topic.endswith(str(self.topic)):
                await self._handle_ipc_message(topic, qos, raw_payload, retain)
```

- [ ] **Step 4: Run script to verify it passes**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t3_ipc.py"`
Expected: all PASS, `ALL PASS`, exit 0.

- [ ] **Step 5: Compile check**

Run: `uv run python -m py_compile mqtt_svc2.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add mqtt_svc2.py
git commit -m "feat(mqtt): restore IPC filtering with eqp_state tracking and SECS excludes"
```

---

### Task 4: Rewrite `data_process` with legacy outbound routing

**Files:**
- Modify: `mqtt_svc2.py` — replace the body of `data_process` (lines 547-595).
- Test: `%TEMP%\opencode\mqtt_port_tests\t4_data_process.py`

**Interfaces:**
- Consumes: `_publish(topic, payload, qos, properties, retain, wait_timeout)`; `_build_publish_properties(correlation)`; `MQTTCorrelation`; `self.topic`; `self.topic_server`; `settings.MQTT_DEBUG_ENABLE`; `self.logger_mqtt`. External contract with `_outbound_loop` is unchanged (`await self.data_process(data) -> bool`; False triggers requeue/retry).
- Produces: `data_process(self, data) -> bool` — cmd/correlation replies to `correlation.ResponseTopic` at qos 1; payloads with `device_id` also go to `topic_server` full copy; every non-cmd payload goes to `self.topic` with `"device_id"` regex-stripped.

- [ ] **Step 1: Write the failing verification script**

Create `%TEMP%\opencode\mqtt_port_tests\t4_data_process.py`:

```python
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(r"C:\gyro\LEDButton")
sys.path.insert(0, str(REPO))
import mqtt_svc2 as m


class FakeLogger:
    def info(self, *a, **k):
        pass
    def warning(self, *a, **k):
        pass
    def error(self, *a, **k):
        pass


class FakeClient:
    def __init__(self):
        self.published = []
    async def publish(self, topic, payload=None, qos=None, retain=False, properties=None, timeout=None):
        self.published.append((topic, payload, qos, properties))


def make_svc(connect=True):
    svc = m.MQTTSvc.__new__(m.MQTTSvc)
    svc.logger = FakeLogger()
    svc.logger_mqtt = FakeLogger()
    svc.topic = "IPC"
    svc.topic_server = "Server"
    svc.connect = connect
    svc.mqttc = FakeClient()
    return svc


failures = []


def check(name, cond):
    if cond:
        print(f"PASS {name}")
    else:
        failures.append(name)
        print(f"FAIL {name}")


async def main():
    svc = make_svc()
    ok = await svc.data_process({"device_id": "DEV1", "port_no": 2, "ledboard_state": 1})
    check("returns True", ok is True)
    frames = svc.mqttc.published
    check("two frames published", len(frames) == 2)
    if len(frames) == 2:
        t1, p1, q1, _ = frames[0]
        t2, p2, q2, _ = frames[1]
        check("server frame first", t1 == "Server")
        check("server frame keeps device_id", '"device_id"' in p1)
        check("ipc frame second", t2 == "IPC")
        check("ipc frame device_id stripped", '"device_id"' not in p2)
        check("stripped json still valid", isinstance(json.loads(p2), dict))

    svc = make_svc()
    corr = m.MQTTCorrelation(ResponseTopic="resp/topic", CorrelationData=b"\x01\x02")
    ok = await svc.data_process({"cmd": "status", "result": "OK", "correlation": corr})
    frames = svc.mqttc.published
    check("cmd returns True", ok is True)
    check("cmd single reply frame", len(frames) == 1)
    if frames:
        topic, payload, qos, props = frames[0]
        check("cmd reply topic", topic == "resp/topic")
        check("cmd reply qos 1", qos == 1)
        check("cmd correlation preserved", props.CorrelationData == b"\x01\x02")
        check("correlation key removed", '"correlation"' not in payload)

    svc = make_svc()
    ok = await svc.data_process({"cmd": "x", "result": "NG", "correlation": None})
    check("missing correlation warn-and-drop", ok is True and len(svc.mqttc.published) == 0)

    svc = make_svc(connect=False)
    ok = await svc.data_process({"port_no": 1})
    check("disconnected returns False", ok is False)


asyncio.run(main())
if failures:
    sys.exit(1)
print("ALL PASS")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t4_data_process.py"`
Expected: FAILs on routing semantics — current implementation references `settings.WAFER_TYPE` (`AttributeError`) and publishes differently.

- [ ] **Step 3: Implement**

Replace the entire `data_process` method (lines 547-595) with:

```python
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
```

Deliberate deviation from old mqtt_svc.py (documented in spec): a failed server-topic publish now returns False so v2's requeue/retry loop can retry the whole notification, instead of old behavior of continuing regardless. The dead HTTP-POST tail of the old file is not ported.

- [ ] **Step 4: Run script to verify it passes**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t4_data_process.py"`
Expected: all PASS, `ALL PASS`, exit 0.

- [ ] **Step 5: Compile check**

Run: `uv run python -m py_compile mqtt_svc2.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add mqtt_svc2.py
git commit -m "feat(mqtt): restore legacy outbound routing in data_process"
```

---

### Task 5: Guarded Request handler, legacy subscriptions, e84 removal sweep

**Files:**
- Modify: `mqtt_svc2.py` — replace `_handle_request_message` (lines 437-473); replace subscription block in `connect_MQTT_service` (lines 233-241); delete `_run_e84_cmd` (335-344), `_publish_rfid_status` (346-353), `_handle_ledboard_message` (378-435), `_handle_broker_log` (475-527); delete `BROKER_LOG_POLL_DEBOUNCE_SECONDS` constant (~line 39) and `self._last_broker_poll_time = {}` init line (~line 79).
- Test: `%TEMP%\opencode\mqtt_port_tests\t5_final.py`

**Interfaces:**
- Consumes: `_get_correlation(properties)`, `MQTTCorrelation`, `_run_in_cmd_executor(fn, *args)`, `MAX_CMD_WAIT`.
- Produces: final `on_message` dispatch (Process / IPC / response / Request branches only); `_handle_request_message(self, raw_payload, properties)` — guarded no-op when `self.uiform is None`; subscription list `{topic}`, `{topic}/Request`, `{topic_server}`, `{topic_server}/Process`, `{topic_server}/LRC/response`, `{topic_server}/WIP/response`.

- [ ] **Step 1: Write the failing verification script**

Create `%TEMP%\opencode\mqtt_port_tests\t5_final.py`:

```python
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

REPO = Path(r"C:\gyro\LEDButton")
sys.path.insert(0, str(REPO))
import mqtt_svc2 as m

failures = []


def check(name, cond):
    if cond:
        print(f"PASS {name}")
    else:
        failures.append(name)
        print(f"FAIL {name}")


source = (REPO / "mqtt_svc2.py").read_text(encoding="utf-8")

for token in [
    "$SYS/broker/log/N",
    "_handle_broker_log",
    "_handle_ledboard_message",
    "_run_e84_cmd",
    "_publish_rfid_status",
    "BROKER_LOG_POLL_DEBOUNCE_SECONDS",
    "_last_broker_poll_time",
    "RFID_DEVICE_ONLY",
    "SERVER_UPLOAD_ALL",
    "WAFER_TYPE",
    "CLAMP_ENABLE",
    "LEDBOARD_ENABLE",
    "loadport",
    "rfid",
]:
    check(f"removed: {token}", token not in source)

for token in [
    'client.subscribe(self.topic, settings.MQTT_QOS)',
    'client.subscribe(f"{self.topic}/Request", settings.MQTT_QOS)',
    'client.subscribe(self.topic_server, settings.MQTT_QOS)',
    'client.subscribe(f"{self.topic_server}/Process", settings.MQTT_QOS)',
    'client.subscribe(f"{self.topic_server}/LRC/response", settings.MQTT_QOS)',
    'client.subscribe(f"{self.topic_server}/WIP/response", settings.MQTT_QOS)',
]:
    check(f"subscription present: {token.split('(')[1][:30]}", token in source)


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.infos = []
    def info(self, msg, *a, **k):
        self.infos.append(str(msg))
    def warning(self, msg, *a, **k):
        self.warnings.append(str(msg))
    def error(self, *a, **k):
        pass


class FakeApi:
    def __init__(self):
        self.calls = []
    def api_request(self, cmd, data, correlation):
        self.calls.append((cmd, data, correlation))


def make_svc(uiform):
    svc = m.MQTTSvc.__new__(m.MQTTSvc)
    svc.logger = FakeLogger()
    svc.uiform = uiform
    return svc


async def main():
    svc = make_svc(None)
    good_props = NS(ResponseTopic="r/t", CorrelationData=b"\x09")
    await svc._handle_request_message(b'{"cmd":"x","port_no":1}', good_props)
    check("uiform None -> ignored", any("uiform" in w or "ignored" in i for w in svc.logger.warnings + svc.logger.infos))

    svc = make_svc(None)
    await svc._handle_request_message(b'{"cmd":"x","port_no":1}', NS(CorrelationData=b"\x09"))
    check("no ResponseTopic warned", any("No reply requested" in w for w in svc.logger.warnings))

    api = FakeApi()
    ui = NS(e84={1: api})
    svc = make_svc(ui)
    corr_props = NS(ResponseTopic="resp/x", CorrelationData=b"\x07\x08")
    await svc._handle_request_message(b'{"cmd":"status","data":{"a":1},"port_no":1}', corr_props)
    check("api_request invoked once", len(api.calls) == 1)
    if api.calls:
        cmd, data, corr = api.calls[0]
        check("api_request args", cmd == "status" and data == {"a": 1})
        check("api_request correlation object",
              isinstance(corr, m.MQTTCorrelation) and corr.ResponseTopic == "resp/x")


asyncio.run(main())
if failures:
    sys.exit(1)
print("ALL PASS")
```

Note: `"rfid"` as a substring also appears inside... nothing else in the final file; if this check false-positives on an unrelated identifier (e.g., a variable name containing `rfid`), inspect the match before removing anything unrelated.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t5_final.py"`
Expected: FAILs — removed tokens still present, LRC/WIP subscriptions absent.

- [ ] **Step 3: Implement**

3a. Replace `_handle_request_message` (lines 437-473) with:

```python
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
```

3b. In `connect_MQTT_service`, replace lines from `await client.subscribe(self.topic, settings.MQTT_QOS)` through the `try/except` around `$SYS/broker/log/N` with:

```python
            await client.subscribe(self.topic, settings.MQTT_QOS)
            await client.subscribe(f"{self.topic}/Request", settings.MQTT_QOS)
            await client.subscribe(self.topic_server, settings.MQTT_QOS)
            await client.subscribe(f"{self.topic_server}/Process", settings.MQTT_QOS)
            await client.subscribe(f"{self.topic_server}/LRC/response", settings.MQTT_QOS)
            await client.subscribe(f"{self.topic_server}/WIP/response", settings.MQTT_QOS)
```

3c. Delete entire methods `_run_e84_cmd`, `_publish_rfid_status`, `_handle_ledboard_message`, `_handle_broker_log`; delete module constant `BROKER_LOG_POLL_DEBOUNCE_SECONDS` and its comment block; delete init line `self._last_broker_poll_time = {}`.

3d. In `on_message`, delete the `$SYS/broker/log/N` branch so only four branches remain (Process / IPC / response / Request).

- [ ] **Step 4: Run script to verify it passes**

Run: `uv run python "$env:TEMP\opencode\mqtt_port_tests\t5_final.py"`
Expected: all PASS, `ALL PASS`, exit 0.

- [ ] **Step 5: Compile + unused-import sanity**

Run: `uv run python -m py_compile mqtt_svc2.py`
Then confirm no now-unused imports remain (expected survivors: asyncio, collections, concurrent.futures, copy, json, random, re, threading, time, contextlib.asynccontextmanager, dataclasses.dataclass, Thread, aiomqtt family, gyro_watchdog, settings, LoggerFile).
Expected: exit 0; no leftover imports referencing deleted code.

- [ ] **Step 6: Commit**

```bash
git add mqtt_svc2.py
git commit -m "refactor(mqtt): guard Request handling, adopt legacy subscriptions, drop e84 remnants"
```

---

### Task 6: Full-app smoke verification under uv

**Files:**
- No code changes. Verification only.

**Interfaces:**
- Consumes: everything above.
- Produces: verification evidence that the app starts cleanly with the ported service.

- [ ] **Step 1: Confirm uv environment is intact**

Run: `uv run python -c "import mqtt_svc2, aiomqtt, paho.mqtt.client; print('imports OK')"`
Expected: `imports OK` (no installs performed).

- [ ] **Step 2: Run the app for ~25 s and capture output**

```powershell
$p = Start-Process -FilePath "uv" -ArgumentList "run","python","LEDBoard.py" -PassThru -RedirectStandardOutput "$env:TEMP\opencode\mqtt_port_tests\app_out.txt" -RedirectStandardError "$env:TEMP\opencode\mqtt_port_tests\app_err.txt"
Start-Sleep -Seconds 25
Stop-Process -Id $p.Id -Force
Get-Content "$env:TEMP\opencode\mqtt_port_tests\app_out.txt"
Get-Content "$env:TEMP\opencode\mqtt_port_tests\app_err.txt"
```

(A GUI window may appear briefly; Stop-Process closes it.)

Expected evidence:
- No Traceback / AttributeError / ImportError anywhere in either capture.
- Startup lines from Controller (`Controller Starting` when devices present).
- MQTT lifecycle lines: `mqtt : connecting to ... port:...` then either connect logs (broker reachable) or repeated `mqtt : connect_MQTT_service : attempt=N : ...` backoff warnings (no broker) — both prove the ported supervisor runs.
- If a broker IS reachable: birth message published and six subscriptions logged via `mqtt : on_connect`.

If verification fails: report the failure with the captured log lines, do NOT claim success, and propose the next corrective step per AGENTS.md.

- [ ] **Step 3: No commit (verification-only task)**

Working tree should contain only pre-existing unrelated changes (`controller.py`, `src/`). Leave them untouched.

---

## Plan Self-Review (completed by plan author)

1. **Spec coverage:** inbound Process/IPC/response/Request handlers (Tasks 2, 3, 5), eqp_state init (Task 2), SECS filters (Task 3), `_route_to_device` dedup (Task 2), sync publish bridge (Task 1), `data_process` rewrite incl. regex strip and dead-tail exclusion (Task 4), subscription list incl. LRC/WIP + dropping `/LEDBoard`+`$SYS` (Task 5), removals list (Tasks 2/3/5), kept-infrastructure constraints (Global Constraints; never modified), presence retained (untouched), verification under uv (Task 6). All spec sections map to tasks.
2. **Placeholder scan:** none — every code step contains complete code; every run step has exact command and expected outcome.
3. **Type consistency:** `_handle_process_message(topic, qos, raw_payload, retain)` defined Task 2, consumed Task 3 dispatch; `_route_to_device(data)` defined Task 2, consumed Tasks 2/3; `data_process(data)->bool` contract unchanged for `_outbound_loop`; `MQTTCorrelation` reused unchanged in Tasks 4/5.


