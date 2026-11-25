"""Tests for DEVICE_TYPE=1 (AEI mode) MQTT LED control.

In AEI mode the LED board is driven remotely by type-6 LED command messages:
a JSON payload {"port_no": N, "type": 6, "code_id": C, ...} arrives on the
"IPC" topic, is dispatched by MQTTSvc.on_message to _handle_ipc_message
which delegates type-6 payloads to _handle_aei_message, routed to
LEDButton.on_notify, and finally translated by LEDButton.data_process /
_handle_led_command into LED actions (set_led / start_blink) or query
responses (board state messages via _publish_board_state). code_id selects
the command: 0 = query (led_states response with code_id LEDBOARD_QUERY=6),
1 = set one LED (led_no + led_state), 2 = set whole ports (ports list of
{port_no, led_states}).

The tests are fully mocked: no broker and no serial device are required.
- MQTTSvc is exercised with its real on_message/_handle_aei_message/
  _route_to_device logic (constructed without starting its network thread).
- LEDButton is the real class; its serial device is replaced by FakeSerial
  so tests can assert the exact LED frames produced.

Coverage (per the agreed design):
- LED command message format: type 6 + code_id selects the command
  (0=query, 1=set one LED, 2=set whole ports); the former no-code_id
  format is no longer accepted
- code_id=1 full valid matrix: led_no 1..4 (Switch/RFID/E84/Port) x
  led_state 0..3 (None/Green/Blue/Red) x port_no 1..2 on board 1
- code_id=1 flashed states (4..6) register a blink on the requested LED in
  the requested color (Green/Blue/Red); blink ticks alternate the color
  frame with a None frame, and a solid command cancels the active blink
- code_id=0 query: one board state message (code_id LEDBOARD_QUERY=6) for
  a named port; one message per board-owned port for a query-all (no
  port_no, fanned out to every board by _route_to_device)
- code_id=2 multi-port set: ports list of {port_no, led_states} with
  led_states the 4-digit LED state code, applied atomically per board
  (any invalid entry rejects this board's whole subset); entries for the
  other board's ports are skipped
- invalid input rejection in _handle_led_command; missing/unknown code_id
  is logged and ignored
- inbound dispatch: retain skip, port_no > LOAD_PORT_NUMBER skip,
  non-type-6 skip; a type-6 payload on the "IPC" topic IS routed
  (type == 6 is what selects the AEI handler, not a subtopic); a type-6
  payload without port_no is fanned out to every enabled board
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from config import settings
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
# Blink colors for flashed states reuse the solid color triples.
BLINK_COLOR = {4: STATE_COLOR[1], 5: STATE_COLOR[2], 6: STATE_COLOR[3]}  # Green/Blue/Red
NONE_COLOR = STATE_COLOR[0]


def led_control_payload(port_no=1, led_no=1, led_state=1, code_id=1):
    return {'port_no': port_no, 'type': 6, 'code_id': code_id,
            'led_no': led_no, 'led_state': led_state}


# --- fixtures ---------------------------------------------------------------

@pytest.fixture()
def board(monkeypatch, tmp_path, ledbutton_cls):
    # Real LEDButton for board 1 (ledbutton_cls fixture: both device_io and
    # its Linux copy device_io_linux); log files go to tmp_path so the test
    # run stays hermetic. The serial device starts as None (as in production)
    # and is swapped for FakeSerial by each test.
    monkeypatch.chdir(tmp_path)
    device = ledbutton_cls(devPath='COM7', board=1, mqtt_svc=None, log=MagicMock())
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
def test_type6_flashed_state_starts_blink(board, led_no, led_state):
    # Flashed states register a blink on the requested LED in the requested
    # color (4=Green, 5=Blue, 6=Red). No frame is written until the blinker
    # ticks; the first tick writes the color, the second the off phase.
    result = board.data_process(led_control_payload(1, led_no, led_state))

    assert result is True
    key = (LED_NAME[led_no], 1)
    assert list(board._blink) == [key]
    assert board._blink[key] == {'color': {4: 'Green', 5: 'Blue', 6: 'Red'}[led_state], 'on': True}

    board._blink_tick()
    board._blink_tick()

    func_bit = FUNC_BITS_PORT1[LED_NAME[led_no]]
    assert board.device.writes == [
        ['C', func_bit, BLINK_COLOR[led_state]],
        ['C', func_bit, NONE_COLOR],
    ]


def test_type6_flashed_state_on_second_port_blinks_independently(board):
    result = board.data_process(led_control_payload(port_no=2, led_no=4, led_state=5))

    assert result is True
    assert list(board._blink) == [('Port', 2)]
    assert board._blink[('Port', 2)] == {'color': 'Blue', 'on': True}

    board._blink_tick()

    assert board.device.writes == [['C', FUNC_BITS_PORT2['Port'], BLINK_COLOR[5]]]


def test_type6_solid_state_cancels_active_blink(board):
    board.data_process(led_control_payload(1, 4, 4))  # Port blink Green
    board._blink_tick()

    result = board.data_process(led_control_payload(1, 4, 3))  # Port solid Red

    assert result is True
    assert board._blink == {}
    assert board.device.writes[-1] == ['C', FUNC_BITS_PORT1['Port'], STATE_COLOR[3]]


def test_type6_flashed_state_replaces_active_blink_color(board):
    board.data_process(led_control_payload(1, 3, 4))  # E84 blink Green
    board._blink_tick()

    result = board.data_process(led_control_payload(1, 3, 6))  # E84 blink Red

    assert result is True
    assert board._blink == {('E84', 1): {'color': 'Red', 'on': True}}


def test_type6_solid_command_on_other_led_keeps_blink(board):
    board.data_process(led_control_payload(1, 4, 4))  # Port blink Green
    board._blink_tick()

    result = board.data_process(led_control_payload(1, 3, 2))  # E84 solid Blue

    assert result is True
    assert ('Port', 1) in board._blink


@pytest.mark.parametrize('led_no', [0, 5, 6])
def test_type6_rejects_led_no_out_of_range(board, led_no):
    result = board.data_process(led_control_payload(led_no=led_no))

    # Invalid input is ignored inside _handle_led_command; data_process
    # still reports the message as handled.
    assert result is True
    assert board.device.writes == []


@pytest.mark.parametrize('led_state', [-1, 7, 100])
def test_type6_rejects_led_state_out_of_range(board, led_state):
    result = board.data_process(led_control_payload(led_state=led_state))

    assert result is True
    assert board.device.writes == []


def test_type6_rejects_port_no_beyond_board_1(board):
    # Board 1 only serves ports 1-2; port 3-4 belong to board 2.
    result = board.data_process(led_control_payload(port_no=3))

    assert result is None
    assert board.device.writes == []


def test_type6_missing_led_no_is_rejected(board):
    payload = {'port_no': 1, 'type': 6, 'code_id': 1, 'led_state': 1}

    result = board.data_process(payload)

    assert result is True
    assert board.device.writes == []


def test_type6_missing_led_state_is_rejected(board):
    payload = {'port_no': 1, 'type': 6, 'code_id': 1, 'led_no': 1}

    result = board.data_process(payload)

    assert result is True
    assert board.device.writes == []


def test_non_type6_payload_does_not_write_a_frame(board):
    # Only type 6 reaches the LED command branch; other types fall through
    # to the E84/GYRO-300 style handlers below it.
    result = board.data_process({'port_no': 1, 'type': 4, 'ledboard_state': 1})

    assert board.device.writes == []


# --- code_id=0: LED query ----------------------------------------------------

@pytest.fixture()
def publishing_board(board, monkeypatch):
    # AEI mode so the outbound board state message carries the type-6
    # traffic code, and a mock broker client to capture publications.
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 1)
    board.mqtt_svc = MagicMock()
    return board


def test_query_single_port_publishes_one_board_state_message(publishing_board):
    result = publishing_board.data_process(
        {'port_no': 2, 'type': 6, 'code_id': 0})

    assert result is True
    published = [c.args[0] for c in publishing_board.mqtt_svc.publish.call_args_list]
    assert len(published) == 1
    assert published[0]['port_no'] == 2
    assert published[0]['type'] == 6
    assert published[0]['code_id'] == settings.LEDBOARD_QUERY
    assert published[0]['led_states'] == '0000'  # nothing commanded yet
    assert 'occurred_at' in published[0]


def test_query_single_port_reports_commanded_led_states(publishing_board):
    publishing_board.data_process(led_control_payload(port_no=1, led_no=3, led_state=5))

    publishing_board.data_process({'port_no': 1, 'type': 6, 'code_id': 0})

    published = [c.args[0] for c in publishing_board.mqtt_svc.publish.call_args_list]
    assert published[-1]['port_no'] == 1
    assert published[-1]['code_id'] == settings.LEDBOARD_QUERY
    assert published[-1]['led_states'] == '0050'


def test_query_all_ports_publishes_one_message_per_board_port(publishing_board):
    # Query-all (no port_no) is fanned out to every board; board 1 answers
    # for its own ports 1-2 only, one message per port.
    result = publishing_board.data_process({'type': 6, 'code_id': 0})

    assert result is True
    published = [c.args[0] for c in publishing_board.mqtt_svc.publish.call_args_list]
    assert [m['port_no'] for m in published] == [1, 2]
    for message in published:
        assert message['type'] == 6
        assert message['code_id'] == settings.LEDBOARD_QUERY
        assert message['led_states'] == '0000'


def test_query_all_skips_ports_beyond_load_port_number(publishing_board, monkeypatch):
    monkeypatch.setattr(settings, 'LOAD_PORT_NUMBER', 1)

    publishing_board.data_process({'type': 6, 'code_id': 0})

    published = [c.args[0] for c in publishing_board.mqtt_svc.publish.call_args_list]
    assert [m['port_no'] for m in published] == [1]


# --- code_id=2: set whole ports -----------------------------------------------

def test_code_id2_sets_multiple_ports_from_led_states_codes(board):
    result = board.data_process({'type': 6, 'code_id': 2, 'ports': [
        {'port_no': 1, 'led_states': '1204'},
        {'port_no': 2, 'led_states': '0350'},
    ]})

    assert result is True
    # Solid digits write immediately in Switch/RFID/E84/Port order; flashed
    # digits (4-6) register a blink and write on the blinker tick.
    assert board.device.writes == [
        ['C', FUNC_BITS_PORT1['Switch'], STATE_COLOR[1]],   # port 1 Switch Green
        ['C', FUNC_BITS_PORT1['RFID'], STATE_COLOR[2]],     # port 1 RFID Blue
        ['C', FUNC_BITS_PORT1['E84'], STATE_COLOR[0]],      # port 1 E84 None
        # port 1 Port flashed Green: blink, written on the blinker tick
        ['C', FUNC_BITS_PORT2['Switch'], STATE_COLOR[0]],   # port 2 Switch None
        ['C', FUNC_BITS_PORT2['RFID'], STATE_COLOR[3]],     # port 2 RFID Red
        # port 2 E84 flashed Blue: blink, written on the blinker tick
        ['C', FUNC_BITS_PORT2['Port'], STATE_COLOR[0]],     # port 2 Port None
    ]
    assert board._blink == {
        ('Port', 1): {'color': 'Green', 'on': True},        # port 1 Port flashed Green
        ('E84', 2): {'color': 'Blue', 'on': True},          # port 2 E84 flashed Blue
    }
    assert board.get_port_states(1) == '1204'
    assert board.get_port_states(2) == '0350'


def test_code_id2_skips_ports_belonging_to_the_other_board(board):
    # Board 1 only serves ports 1-2; a port 3-4 entry is not this board's.
    result = board.data_process({'type': 6, 'code_id': 2, 'ports': [
        {'port_no': 3, 'led_states': '1111'},
    ]})

    assert result is True
    assert board.device.writes == []
    assert board._blink == {}


def test_code_id2_invalid_led_states_rejects_the_whole_message(board):
    # Atomic application: one invalid entry means nothing is applied.
    result = board.data_process({'type': 6, 'code_id': 2, 'ports': [
        {'port_no': 1, 'led_states': '1111'},
        {'port_no': 2, 'led_states': '9999'},  # digit 9 is not a LED state
    ]})

    assert result is True
    assert board.device.writes == []
    assert board._blink == {}


def test_code_id2_malformed_entries_are_rejected(board):
    for bad_ports in (
        [{'port_no': 1}],                        # missing led_states
        [{'led_states': '1111'}],                # missing port_no
        [{'port_no': '1', 'led_states': '1111'}],  # non-int port_no
        [{'port_no': 1, 'led_states': 1111}],    # non-string led_states
        [{'port_no': 1, 'led_states': '111'}],   # too short
    ):
        result = board.data_process({'type': 6, 'code_id': 2, 'ports': bad_ports})

        assert result is True
        assert board.device.writes == []


def test_code_id2_without_ports_list_is_rejected(board):
    for payload in ({'type': 6, 'code_id': 2},
                    {'type': 6, 'code_id': 2, 'ports': '1111'},
                    {'type': 6, 'code_id': 2, 'ports': []}):
        result = board.data_process(payload)

        assert result is True
        assert board.device.writes == []


# --- code_id: missing or unknown ----------------------------------------------

@pytest.mark.parametrize('code_id', [None, 3, 99])
def test_type6_missing_or_unknown_code_id_is_ignored(board, code_id):
    payload = {'port_no': 1, 'type': 6, 'led_no': 1, 'led_state': 1}
    if code_id is not None:
        payload['code_id'] = code_id

    result = board.data_process(payload)

    # The former no-code_id format is no longer accepted; unknown code_id
    # values are logged and ignored.
    assert result is True
    assert board.device.writes == []
    assert board._blink == {}


# --- inbound MQTT dispatch: on_message -> _handle_ipc_message -> _handle_aei_message ---

def test_aei_topic_type6_message_is_routed_to_device(svc, board):
    payload = led_control_payload(port_no=1, led_no=3, led_state=2)
    msg = FakeMsg('IPC', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == [payload]


def test_aei_topic_type6_without_port_no_is_fanned_out(svc, board):
    # A query-all (code_id=0) or multi-port set (code_id=2) carries no
    # top-level port_no; _route_to_device fans it out to every enabled
    # board. Board 2 is disabled here, so only board 1 receives it.
    payload = {'type': 6, 'code_id': 0}
    msg = FakeMsg('IPC', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == [payload]


def test_aei_topic_retained_message_is_skipped(svc, board):
    payload = led_control_payload()
    msg = FakeMsg('IPC', json.dumps(payload).encode(), retain=True)

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == []


def test_aei_topic_port_no_beyond_load_port_number_is_skipped(svc, board):
    # LOAD_PORT_NUMBER is 4 by default; payloads above it are excluded
    # before routing.
    payload = led_control_payload(port_no=settings.LOAD_PORT_NUMBER + 1)
    msg = FakeMsg('IPC', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == []


def test_aei_topic_non_type6_message_is_not_aei_routed(svc, board):
    # Only type == 6 selects the AEI handler. A type-4 payload on the base
    # topic follows the normal IPC path (Place & Go) and is routed from
    # there, not via _handle_aei_message.
    payload = {'port_no': 1, 'type': 4, 'ledboard_state': 1}
    msg = FakeMsg('IPC', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == [payload]


def test_aei_topic_message_without_type_is_not_aei_routed(svc, board):
    # type == 6 is what selects the AEI handler. A payload without a "type"
    # key falls through to the GYRO-300 style handling, which fails on the
    # missing keys; on_message swallows the error and nothing is routed.
    payload = {'port_no': 1, 'led_no': 1, 'led_state': 1}
    msg = FakeMsg('IPC', json.dumps(payload).encode())

    asyncio.run(svc.on_message(msg))

    assert list(board.cmd_queue) == []
