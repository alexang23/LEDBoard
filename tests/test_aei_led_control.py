"""Tests for DEVICE_TYPE=1 (AEI mode) MQTT LED control.

In AEI mode the LED board is driven remotely by type-6 LED control messages:
a JSON payload {"port_no": N, "type": 6, "led_no": L, "led_state": S} arrives
on the "IPC/AEI" topic, is dispatched by MQTTSvc.on_message to
_handle_aei_message, routed to LEDButton.on_notify, and finally translated by
LEDButton.data_process into a serial frame via set_led.

The tests are fully mocked: no broker and no serial device are required.
- MQTTSvc is exercised with its real on_message/_handle_aei_message/
  _route_to_device logic (constructed without starting its network thread).
- LEDButton is the real class; its serial device is replaced by FakeSerial
  so tests can assert the exact LED frames produced.

Coverage (per the agreed design):
- full valid matrix: led_no 1..4 (Switch/RFID/E84/Port) x led_state 0..3
  (None/Green/Blue/Red) x port_no 1..2 on board 1
- documented current behaviour: flashed states (4..6) produce NO frame,
  because LEDButton.color has no "Flashed ..." entries
- invalid input rejection in data_process
- inbound dispatch: retain skip, port_no > LOAD_PORT_NUMBER skip,
  non-type-6 skip, missing-"type" permissiveness, and the fact that a
  type-6 payload sent to the "IPC" topic is NOT routed.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from config import settings
from device_io import LEDButton
from mqtt_svc2 import MQTTSvc


# --- test doubles -----------------------------------------------------------

class FakeSerial:
    """Stands in for the serial device; records everything written."""

    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(list(data))


class FakeMsg:
    """Minimal stand-in for an aiomqtt.Message."""

    def __init__(self, topic, payload, qos=0, retain=False):
        self.topic = topic
        self.payload = payload
        self.qos = qos
        self.retain = retain
        self.properties = None


class FakeController:
    def __init__(self, device):
        self.device = device
        self.device2 = None


# Expected serial frame layout, pinned from device_io.LEDButton for board 1:
# func bit positions per LED name/port, and color triples per solid state.
FUNC_BITS_PORT1 = {'Switch': 10, 'RFID': 26, 'E84': 18, 'Port': 2}
FUNC_BITS_PORT2 = {'Switch': 14, 'RFID': 30, 'E84': 22, 'Port': 6}
STATE_COLOR = {
    0: [48, 48, 48],  # None
    1: [48, 49, 48],  # Green
    2: [48, 48, 49],  # Blue
    3: [49, 48, 48],  # Red
}
LED_NAME = {1: 'Switch', 2: 'RFID', 3: 'E84', 4: 'Port'}


def led_control_payload(port_no=1, led_no=1, led_state=1):
    return {'port_no': port_no, 'type': 6, 'led_no': led_no, 'led_state': led_state}


# --- fixtures ---------------------------------------------------------------

@pytest.fixture()
def board(monkeypatch, tmp_path):
    # Real LEDButton for board 1; log files go to tmp_path so the test run
    # stays hermetic. The serial device starts as None (as in production)
    # and is swapped for FakeSerial by each test.
    monkeypatch.chdir(tmp_path)
    device = LEDButton(devPath='COM7', board=1, mqtt_svc=None, log=MagicMock())
    device.device = FakeSerial()
    return device


@pytest.fixture()
def svc(board, monkeypatch, tmp_path):
    # Real MQTTSvc (never started): __init__ is network-free, so on_message
    # and the AEI handler run their real dispatch/routing logic.
    monkeypatch.chdir(tmp_path)
    service = MQTTSvc(FakeController(board), MagicMock())
    yield service
    # The thread was never started, so joining is not possible; just release
    # the command executor created in __init__.
    service._shutdown_cmd_executor()


# --- data_process: the DEVICE_TYPE=1 LED control mapping --------------------

@pytest.mark.parametrize('led_no', [1, 2, 3, 4])
@pytest.mark.parametrize('led_state', [0, 1, 2, 3])
@pytest.mark.parametrize('port_no', [1, 2])
def test_type6_valid_matrix_writes_one_frame(board, port_no, led_no, led_state):
    func_bits = FUNC_BITS_PORT1 if port_no == 1 else FUNC_BITS_PORT2

    result = board.data_process(led_control_payload(port_no, led_no, led_state))

    assert result is True
    assert board.device.writes == [
        ['C', func_bits[LED_NAME[led_no]], STATE_COLOR[led_state]]
    ]


@pytest.mark.parametrize('led_no', [1, 2, 3, 4])
@pytest.mark.parametrize('led_state', [4, 5, 6])
def test_type6_flashed_states_produce_no_frame_documented_behaviour(board, led_no, led_state):
    # LEDButton.set_led looks the state name up in self.color, which only
    # contains None/Green/Blue/Red. "Flashed ..." states therefore raise a
    # KeyError inside set_led (swallowed by its try/except) and no frame is
    # written. This test pins that current behaviour; if flashing support is
    # ever added to the AEI path, this test should be updated to assert the
    # expected blink behaviour instead.
    result = board.data_process(led_control_payload(1, led_no, led_state))

    assert result is True
    assert board.device.writes == []


@pytest.mark.parametrize('led_no', [0, 5, 6])
def test_type6_rejects_led_no_out_of_range(board, led_no):
    result = board.data_process(led_control_payload(led_no=led_no))

    assert result is None
    assert board.device.writes == []


@pytest.mark.parametrize('led_state', [-1, 7, 100])
def test_type6_rejects_led_state_out_of_range(board, led_state):
    result = board.data_process(led_control_payload(led_state=led_state))

    assert result is None
    assert board.device.writes == []


def test_type6_rejects_port_no_beyond_board_1(board):
    # Board 1 only serves ports 1-2; port 3-4 belong to board 2.
    result = board.data_process(led_control_payload(port_no=3))

    assert result is None
    assert board.device.writes == []


def test_type6_missing_led_no_is_rejected(board):
    payload = {'port_no': 1, 'type': 6, 'led_state': 1}

    result = board.data_process(payload)

    assert result is None
    assert board.device.writes == []


def test_type6_missing_led_state_is_rejected(board):
    payload = {'port_no': 1, 'type': 6, 'led_no': 1}

    result = board.data_process(payload)

    assert result is None
    assert board.device.writes == []


def test_non_type6_payload_does_not_write_a_frame(board):
    # Only type 6 reaches the LED-control branch; other types fall through
    # to the E84/GYRO-300 style handlers below it.
    result = board.data_process({'port_no': 1, 'type': 4, 'ledboard_state': 1})

    assert board.device.writes == []


# --- inbound MQTT dispatch: on_message -> _handle_aei_message ----------------

def test_aei_topic_type6_message_is_routed_to_device(svc, board):
    payload = led_control_payload(port_no=1, led_no=3, led_state=2)
    msg = FakeMsg('IPC/AEI', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == [payload]


def test_aei_topic_retained_message_is_skipped(svc, board):
    payload = led_control_payload()
    msg = FakeMsg('IPC/AEI', json.dumps(payload).encode(), retain=True)

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == []


def test_aei_topic_port_no_beyond_load_port_number_is_skipped(svc, board):
    # LOAD_PORT_NUMBER is 4 by default; payloads above it are excluded
    # before routing.
    payload = led_control_payload(port_no=settings.LOAD_PORT_NUMBER + 1)
    msg = FakeMsg('IPC/AEI', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == []


def test_aei_topic_non_type6_message_is_not_routed(svc, board):
    payload = {'port_no': 1, 'type': 4, 'ledboard_state': 1}
    msg = FakeMsg('IPC/AEI', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == []


def test_aei_topic_message_without_type_is_routed(svc, board):
    # _handle_aei_message only rejects explicit non-6 types; a payload
    # without a "type" key passes the filter and is routed. data_process
    # then fails on the missing key downstream, but routing itself happens.
    # This test pins that permissive current behaviour.
    payload = {'port_no': 1, 'led_no': 1, 'led_state': 1}
    msg = FakeMsg('IPC/AEI', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == [payload]


def test_type6_sent_to_ipc_topic_is_not_routed(svc, board):
    # Type-6 LED control belongs on "IPC/AEI". The same payload sent to the
    # plain "IPC" topic reaches _handle_ipc_message, whose non-type-2/4
    # branch expects eqp_state and drops the message (KeyError swallowed by
    # on_message). This test documents that behaviour for anyone probing
    # the wrong topic.
    payload = led_control_payload()
    msg = FakeMsg('IPC', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == []
