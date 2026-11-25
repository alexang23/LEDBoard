"""Tests for the /api/led WebAPI (AEI mode only).

POST /api/led/set        sets one LED of one port by enqueuing a single
                         type-6 payload (LEDButton.on_notify).
POST /api/led/set/port   applies a 4-digit LED state code to one port by
                         enqueuing the same type-6 payloads MQTT carries
                         (LEDButton.on_notify).
POST /api/led/set/ports  applies a 4-digit LED state code to several ports
                         in one request (all-or-nothing validation).
POST /api/led/state      reports the LED state code of one port (within
                         LOAD_PORT_NUMBER on an enabled board).
GET  /api/led/state/all  reports the LED state code of every live port
                         (within LOAD_PORT_NUMBER on an enabled board).

Every response is HTTP 200 with one envelope
{Success, State, ErrorCode, Message, ...}. The tests call the route
handlers directly (no httpx dependency) with stubbed Request objects, in
the same fully-mocked style as test_aei_led_control.py: LEDButton is real,
its serial device is FakeSerial, and the Controller is a stub exposing
device/device2.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config import settings
from routers.led import (
    LedPortStateRequest,
    LedPortStates,
    LedPortsRequest,
    LedSetRequest,
    LedStateRequest,
    get_all_led_states,
    get_led_state,
    set_led,
    set_port_led_states,
    set_ports_led_states,
)


# --- test doubles -----------------------------------------------------------

class FakeSerial:
    """Stands in for the serial device; records everything written."""

    def __init__(self):
        self.writes = []


class StubRequest:
    """Minimal stand-in for starlette Request: only .app.state is used."""

    def __init__(self, tsc):
        self.app = SimpleNamespace(state=SimpleNamespace(tsc=tsc))


class StubController:
    def __init__(self, device, device2):
        self.device = device
        self.device2 = device2


# --- fixtures ---------------------------------------------------------------

@pytest.fixture()
def board(monkeypatch, tmp_path, ledbutton_cls):
    monkeypatch.chdir(tmp_path)
    device = ledbutton_cls(devPath='COM7', board=1, mqtt_svc=None, log=MagicMock())
    device.device = FakeSerial()
    return device


@pytest.fixture()
def board2(monkeypatch, tmp_path, ledbutton_cls):
    monkeypatch.chdir(tmp_path)
    device = ledbutton_cls(devPath='COM7', board=2, mqtt_svc=None, log=MagicMock())
    device.device = FakeSerial()
    return device


@pytest.fixture()
def request_aei(monkeypatch, board, board2):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 1)
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', True)
    return StubRequest(StubController(board, board2))


def post(request_aei, port_no=1, led_states='2356'):
    body = LedStateRequest(port_no=port_no, led_states=led_states)
    return asyncio.run(set_port_led_states(request_aei, body))


def get_all(request_aei):
    return asyncio.run(get_all_led_states(request_aei))


def set_led_state(request_aei, port_no=1, led_no=1, led_state=2):
    body = LedSetRequest(port_no=port_no, led_no=led_no, led_state=led_state)
    return asyncio.run(set_led(request_aei, body))


def get_state(request_aei, port_no=1):
    body = LedPortStateRequest(port_no=port_no)
    return asyncio.run(get_led_state(request_aei, body))


def set_ports(request_aei, ports):
    body = LedPortsRequest(ports=[LedPortStates(**port) for port in ports])
    return asyncio.run(set_ports_led_states(request_aei, body))


# --- POST /api/led/state ------------------------------------------------------

@pytest.mark.parametrize('port_no', [1, 2, 3, 4])
def test_post_valid_enqueues_four_type6_payloads(request_aei, port_no):
    response = post(request_aei, port_no=port_no)

    tsc = request_aei.app.state.tsc
    device = tsc.device if port_no in (1, 2) else tsc.device2
    assert list(device.cmd_queue) == [
        {'port_no': port_no, 'type': 6, 'code_id': 1, 'led_no': 1, 'led_state': 2},
        {'port_no': port_no, 'type': 6, 'code_id': 1, 'led_no': 2, 'led_state': 3},
        {'port_no': port_no, 'type': 6, 'code_id': 1, 'led_no': 3, 'led_state': 5},
        {'port_no': port_no, 'type': 6, 'code_id': 1, 'led_no': 4, 'led_state': 6},
    ]
    assert response == {
        'Success': True, 'State': 'OK', 'ErrorCode': 0, 'Message': '',
        'Port': {'port_no': port_no, 'led_states': '2356'},
    }


def test_post_clears_to_none(request_aei):
    response = post(request_aei, led_states='0000')

    assert response['Success'] is True
    assert [payload['led_state'] for payload in request_aei.app.state.tsc.device.cmd_queue] == [0, 0, 0, 0]


def test_post_flashed_digits_reach_the_device(request_aei):
    post(request_aei, port_no=2, led_states='1246')

    device = request_aei.app.state.tsc.device
    assert [payload['led_state'] for payload in device.cmd_queue] == [1, 2, 4, 6]


def test_post_rejects_non_aei_mode(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 0)

    response = post(request_aei)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'AEI mode is not enabled'}
    assert list(request_aei.app.state.tsc.device.cmd_queue) == []


@pytest.mark.parametrize('port_no', [0, 5, -1])
def test_post_rejects_port_no_beyond_load_port_number(monkeypatch, request_aei, port_no):
    monkeypatch.setattr(settings, 'LOAD_PORT_NUMBER', 4)

    response = post(request_aei, port_no=port_no)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'port_no is not exist'}


def test_post_rejects_board2_port_when_board2_disabled(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)

    response = post(request_aei, port_no=3)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'port_no is not exist'}


def test_post_rejects_disconnected_device(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)
    request_aei.app.state.tsc.device = None

    response = post(request_aei)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 503, 'Message': 'device is not connected'}


@pytest.mark.parametrize('led_states', ['235', '23567', '2358', 'abcd', '2 56', ''])
def test_post_rejects_invalid_led_states(request_aei, led_states):
    response = post(request_aei, led_states=led_states)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 422, 'Message': 'invalid led_no/led_state'}
    assert list(request_aei.app.state.tsc.device.cmd_queue) == []


# --- POST /api/led/set/ports --------------------------------------------------

def test_set_ports_enqueues_four_payloads_per_port(request_aei):
    response = set_ports(request_aei, [
        {'port_no': 1, 'led_states': '2356'},
        {'port_no': 3, 'led_states': '1111'},
    ])

    tsc = request_aei.app.state.tsc
    assert list(tsc.device.cmd_queue) == [
        {'port_no': 1, 'type': 6, 'code_id': 1, 'led_no': 1, 'led_state': 2},
        {'port_no': 1, 'type': 6, 'code_id': 1, 'led_no': 2, 'led_state': 3},
        {'port_no': 1, 'type': 6, 'code_id': 1, 'led_no': 3, 'led_state': 5},
        {'port_no': 1, 'type': 6, 'code_id': 1, 'led_no': 4, 'led_state': 6},
    ]
    assert list(tsc.device2.cmd_queue) == [
        {'port_no': 3, 'type': 6, 'code_id': 1, 'led_no': 1, 'led_state': 1},
        {'port_no': 3, 'type': 6, 'code_id': 1, 'led_no': 2, 'led_state': 1},
        {'port_no': 3, 'type': 6, 'code_id': 1, 'led_no': 3, 'led_state': 1},
        {'port_no': 3, 'type': 6, 'code_id': 1, 'led_no': 4, 'led_state': 1},
    ]
    assert response == {
        'Success': True, 'State': 'OK', 'ErrorCode': 0, 'Message': '',
        'Length': 2,
        'Ports': [{'port_no': 1, 'led_states': '2356'}, {'port_no': 3, 'led_states': '1111'}],
    }


def test_set_ports_rejects_non_aei_mode(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 0)

    response = set_ports(request_aei, [{'port_no': 1, 'led_states': '2356'}])

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'AEI mode is not enabled'}
    assert list(request_aei.app.state.tsc.device.cmd_queue) == []


def test_set_ports_rejects_empty_ports_list(request_aei):
    response = set_ports(request_aei, [])

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 422, 'Message': 'ports is required'}


def test_set_ports_rejects_all_when_one_led_states_is_invalid(request_aei):
    response = set_ports(request_aei, [
        {'port_no': 1, 'led_states': '2356'},
        {'port_no': 2, 'led_states': '235'},  # too short
    ])

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 422, 'Message': 'invalid led_no/led_state'}
    # All-or-nothing: nothing is enqueued, not even the valid first entry.
    assert list(request_aei.app.state.tsc.device.cmd_queue) == []


@pytest.mark.parametrize('port_no', [0, 5, -1])
def test_set_ports_rejects_all_when_one_port_no_is_unknown(monkeypatch, request_aei, port_no):
    monkeypatch.setattr(settings, 'LOAD_PORT_NUMBER', 4)

    response = set_ports(request_aei, [
        {'port_no': 1, 'led_states': '2356'},
        {'port_no': port_no, 'led_states': '2356'},
    ])

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'port_no is not exist'}
    assert list(request_aei.app.state.tsc.device.cmd_queue) == []


def test_set_ports_rejects_board2_port_when_board2_disabled(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)

    response = set_ports(request_aei, [{'port_no': 4, 'led_states': '2356'}])

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'port_no is not exist'}


def test_set_ports_rejects_all_when_one_device_is_disconnected(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)
    request_aei.app.state.tsc.device = None

    response = set_ports(request_aei, [{'port_no': 1, 'led_states': '2356'}])

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 503, 'Message': 'device is not connected'}


def test_get_all_reflects_http_set_ports(request_aei):
    set_ports(request_aei, [
        {'port_no': 1, 'led_states': '2356'},
        {'port_no': 3, 'led_states': '1111'},
    ])

    # Simulate the device thread draining its command queue.
    for device in (request_aei.app.state.tsc.device, request_aei.app.state.tsc.device2):
        while device.cmd_queue:
            device.data_process(device.cmd_queue.popleft())

    response = get_all(request_aei)

    assert response['Ports'][0] == {'port_no': 1, 'led_states': '2356'}
    assert response['Ports'][2] == {'port_no': 3, 'led_states': '1111'}


# --- POST /api/led/set --------------------------------------------------------

def test_set_valid_enqueues_one_type6_payload(request_aei):
    response = set_led_state(request_aei, port_no=3, led_no=4, led_state=6)

    device = request_aei.app.state.tsc.device2
    assert list(device.cmd_queue) == [{'port_no': 3, 'type': 6, 'code_id': 1, 'led_no': 4, 'led_state': 6}]
    assert response == {
        'Success': True, 'State': 'OK', 'ErrorCode': 0, 'Message': '',
        'Port': {'port_no': 3, 'led_no': 4, 'led_state': 6},
    }


def test_set_clears_to_none(request_aei):
    response = set_led_state(request_aei, led_no=2, led_state=0)

    assert response['Success'] is True
    assert list(request_aei.app.state.tsc.device.cmd_queue) == [
        {'port_no': 1, 'type': 6, 'code_id': 1, 'led_no': 2, 'led_state': 0},
    ]


def test_set_rejects_non_aei_mode(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 0)

    response = set_led_state(request_aei)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'AEI mode is not enabled'}
    assert list(request_aei.app.state.tsc.device.cmd_queue) == []


@pytest.mark.parametrize('port_no', [0, 5, -1])
def test_set_rejects_unknown_port_no(monkeypatch, request_aei, port_no):
    monkeypatch.setattr(settings, 'LOAD_PORT_NUMBER', 4)

    response = set_led_state(request_aei, port_no=port_no)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'port_no is not exist'}


def test_set_rejects_board2_port_when_board2_disabled(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)

    response = set_led_state(request_aei, port_no=4)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'port_no is not exist'}


def test_set_rejects_disconnected_device(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)
    request_aei.app.state.tsc.device = None

    response = set_led_state(request_aei)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 503, 'Message': 'device is not connected'}


@pytest.mark.parametrize('led_no', [0, 5, -1])
def test_set_rejects_invalid_led_no(request_aei, led_no):
    response = set_led_state(request_aei, led_no=led_no, led_state=2)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 422, 'Message': 'invalid led_no/led_state'}
    assert list(request_aei.app.state.tsc.device.cmd_queue) == []


@pytest.mark.parametrize('led_state', [-1, 7, 8])
def test_set_rejects_invalid_led_state(request_aei, led_state):
    response = set_led_state(request_aei, led_no=1, led_state=led_state)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 422, 'Message': 'invalid led_no/led_state'}
    assert list(request_aei.app.state.tsc.device.cmd_queue) == []


# --- GET /api/led/state/all ---------------------------------------------------

def test_get_all_returns_only_live_ports(request_aei):
    # Default LOAD_PORT_NUMBER=4 with both boards enabled: all four ports.
    response = get_all(request_aei)

    assert response['Success'] is True
    assert response['State'] == 'OK'
    assert response['ErrorCode'] == 0
    assert response['Length'] == 4
    assert response['Ports'] == [
        {'port_no': 1, 'led_states': '0000'},
        {'port_no': 2, 'led_states': '0000'},
        {'port_no': 3, 'led_states': '0000'},
        {'port_no': 4, 'led_states': '0000'},
    ]


def test_get_all_excludes_board2_ports_when_disabled(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)

    response = get_all(request_aei)

    assert response['Success'] is True
    assert response['Length'] == 2
    assert [port['port_no'] for port in response['Ports']] == [1, 2]


def test_get_all_respects_load_port_number(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LOAD_PORT_NUMBER', 2)

    response = get_all(request_aei)

    assert response['Success'] is True
    assert response['Length'] == 2
    assert [port['port_no'] for port in response['Ports']] == [1, 2]


def test_get_all_ng_when_a_live_device_is_disconnected(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)
    request_aei.app.state.tsc.device = None

    response = get_all(request_aei)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 503, 'Message': 'device is not connected'}


def test_get_all_ng_in_non_aei_mode(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 0)

    response = get_all(request_aei)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'AEI mode is not enabled'}


# --- POST /api/led/state (single-port report) ----------------------------------

def test_post_state_reports_all_zero_states_for_uncommanded_port(request_aei):
    response = get_state(request_aei, port_no=1)

    assert response == {
        'Success': True, 'State': 'OK', 'ErrorCode': 0, 'Message': '',
        'Port': {'port_no': 1, 'led_states': '0000'},
    }


def test_post_state_reports_recorded_state(request_aei):
    tsc = request_aei.app.state.tsc
    tsc.device.data_process({'port_no': 2, 'type': 6, 'code_id': 1, 'led_no': 1, 'led_state': 3})

    response = get_state(request_aei, port_no=2)

    assert response['Success'] is True
    assert response['Port'] == {'port_no': 2, 'led_states': '3000'}


def test_post_state_maps_board2_ports_to_local_ports(request_aei):
    tsc = request_aei.app.state.tsc
    # Board 2 serves port_no 3-4 as board-local ports 1-2.
    tsc.device2.data_process({'port_no': 4, 'type': 6, 'code_id': 1, 'led_no': 4, 'led_state': 2})

    response = get_state(request_aei, port_no=4)

    assert response['Port'] == {'port_no': 4, 'led_states': '0002'}


def test_post_state_reflects_http_set(request_aei):
    set_led_state(request_aei, port_no=1, led_no=2, led_state=5)

    # Simulate the device thread draining its command queue.
    device = request_aei.app.state.tsc.device
    while device.cmd_queue:
        device.data_process(device.cmd_queue.popleft())

    response = get_state(request_aei, port_no=1)

    assert response['Port'] == {'port_no': 1, 'led_states': '0500'}


def test_post_state_ng_in_non_aei_mode(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 0)

    response = get_state(request_aei)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'AEI mode is not enabled'}


@pytest.mark.parametrize('port_no', [0, 5, -1])
def test_post_state_rejects_unknown_port_no(monkeypatch, request_aei, port_no):
    monkeypatch.setattr(settings, 'LOAD_PORT_NUMBER', 4)

    response = get_state(request_aei, port_no=port_no)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'port_no is not exist'}


def test_post_state_rejects_board2_port_when_board2_disabled(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)

    response = get_state(request_aei, port_no=3)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 403, 'Message': 'port_no is not exist'}


def test_post_state_ng_when_owning_device_is_disconnected(monkeypatch, request_aei):
    monkeypatch.setattr(settings, 'LEDBOARD2_ENABLE', False)
    request_aei.app.state.tsc.device = None

    response = get_state(request_aei, port_no=1)

    assert response == {'Success': False, 'State': 'NG', 'ErrorCode': 503, 'Message': 'device is not connected'}


# --- state reporting through the real device funnel ---------------------------

def test_get_all_reports_last_applied_state(request_aei):
    tsc = request_aei.app.state.tsc
    tsc.device.data_process({'port_no': 2, 'type': 6, 'code_id': 1, 'led_no': 3, 'led_state': 2})

    response = get_all(request_aei)

    assert response['Ports'][0] == {'port_no': 1, 'led_states': '0000'}
    assert response['Ports'][1] == {'port_no': 2, 'led_states': '0020'}


def test_get_all_reports_flashed_state_as_its_digit(request_aei):
    tsc = request_aei.app.state.tsc
    tsc.device.data_process({'port_no': 1, 'type': 6, 'code_id': 1, 'led_no': 1, 'led_state': 4})

    response = get_all(request_aei)

    assert response['Ports'][0] == {'port_no': 1, 'led_states': '4000'}


def test_get_all_maps_board2_ports_to_local_ports(request_aei):
    tsc = request_aei.app.state.tsc
    # Board 2 serves port_no 3-4 as board-local ports 1-2.
    tsc.device2.data_process({'port_no': 4, 'type': 6, 'code_id': 1, 'led_no': 2, 'led_state': 1})

    response = get_all(request_aei)

    assert response['Ports'][2] == {'port_no': 3, 'led_states': '0000'}
    assert response['Ports'][3] == {'port_no': 4, 'led_states': '0100'}


def test_get_all_reflects_http_post(request_aei):
    post(request_aei)

    # Simulate the device thread draining its command queue: the applied
    # state is recorded by set_led/start_blink, so GET only reflects a
    # POST after the device has consumed it.
    device = request_aei.app.state.tsc.device
    while device.cmd_queue:
        device.data_process(device.cmd_queue.popleft())

    response = get_all(request_aei)

    assert response['Ports'][0] == {'port_no': 1, 'led_states': '2356'}


def test_get_all_reflects_http_set(request_aei):
    set_led_state(request_aei, port_no=3, led_no=3, led_state=5)

    # Simulate the device thread draining its command queue.
    device = request_aei.app.state.tsc.device2
    while device.cmd_queue:
        device.data_process(device.cmd_queue.popleft())

    response = get_all(request_aei)

    assert response['Ports'][2] == {'port_no': 3, 'led_states': '0050'}


# --- state reporting for business-logic (non-type-6) commands -----------------

def test_get_all_reflects_business_logic_set_led(request_aei):
    # The RFID/E84 handlers call set_led directly (device_io data_process
    # type 0 / type 2); those writes must show up too.
    tsc = request_aei.app.state.tsc
    tsc.device.set_led('Switch', 1, 'Green')
    tsc.device.set_led('RFID', 1, 'Green')
    tsc.device.set_led('E84', 1, 'Blue')
    tsc.device.set_led('Port', 1, 'Blue')

    response = get_all(request_aei)

    assert response['Ports'][0] == {'port_no': 1, 'led_states': '1122'}


def test_get_all_blink_records_flashed_digit(request_aei):
    # Business-logic start_blink (default Green, as in the Port Ready path)
    # reports as its flashed digit, not as the alternating solid color.
    tsc = request_aei.app.state.tsc
    tsc.device.start_blink('Port', 2, 'Blue')

    response = get_all(request_aei)

    assert response['Ports'][1] == {'port_no': 2, 'led_states': '0005'}


def test_get_all_blinker_writes_keep_flashed_digit(request_aei):
    # The blink loop alternates color/None with from_blinker=True; those
    # writes must not overwrite the recorded flash digit.
    tsc = request_aei.app.state.tsc
    tsc.device.data_process({'port_no': 1, 'type': 6, 'code_id': 1, 'led_no': 4, 'led_state': 6})
    tsc.device.set_led('Port', 1, 'Red', from_blinker=True)
    tsc.device.set_led('Port', 1, 'None', from_blinker=True)

    response = get_all(request_aei)

    assert response['Ports'][0] == {'port_no': 1, 'led_states': '0006'}


def test_get_all_solid_command_overrides_blink_digit(request_aei):
    tsc = request_aei.app.state.tsc
    tsc.device.start_blink('Port', 1, 'Green')
    tsc.device.set_led('Port', 1, 'None')  # solid stop: no light

    response = get_all(request_aei)

    assert response['Ports'][0] == {'port_no': 1, 'led_states': '0000'}
