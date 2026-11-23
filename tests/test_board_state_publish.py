"""Tests for led_states in outbound board state MQTT messages.

Board state messages (initial status, reset-button press, mode-button
press) are built by LEDButton._publish_board_state, which adds the port's
4-digit LED state code (see device_io.LEDButton.get_port_states) alongside
ledboard_state. These tests use a stub mqtt_svc and an LEDButton with no
serial hardware attached.
"""

import threading

from device_io import LEDButton


class PublishSpy:
    """Records every payload passed to publish, mimicking mqtt_svc2.MQTTSvc."""

    def __init__(self):
        self.payloads = []

    def publish(self, data):
        self.payloads.append(data)
        return True


def make_device(board, applied=None):
    """An LEDButton with only the attributes _publish_board_state touches."""
    device = LEDButton.__new__(LEDButton)
    device.board = board
    device.mqtt_svc = PublishSpy()
    device.led_idx = {1: 'Switch', 2: 'RFID', 3: 'E84', 4: 'Port'}
    device.applied = dict(applied or {})
    device._applied_lock = threading.Lock()
    return device


def test_publish_board_state_carries_led_states():
    device = make_device(1, {('Switch', 1): 2, ('E84', 1): 5})
    device._publish_board_state(1, 10)

    (data,) = device.mqtt_svc.payloads
    assert data['port_no'] == 1
    assert data['dual_port'] == 0
    assert data['ledboard_state'] == 10
    assert data['led_states'] == '2050'
    assert list(data.keys()) == ['port_no', 'dual_port', 'ledboard_state', 'led_states', 'occurred_at']


def test_led_states_defaults_to_zeros_when_never_commanded():
    device = make_device(1)
    device._publish_board_state(2, 11)

    (data,) = device.mqtt_svc.payloads
    assert data['port_no'] == 2
    assert data['led_states'] == '0000'


def test_board2_maps_global_port_no_to_board_local_port():
    # Board 2 serves global ports 3, 4 as board-local ports 1, 2.
    device = make_device(2, {('RFID', 1): 6, ('Port', 2): 1})
    device._publish_board_state(3, 10)
    device._publish_board_state(4, 11)

    data3, data4 = device.mqtt_svc.payloads
    assert data3['port_no'] == 3
    assert data3['led_states'] == '0600'
    assert data4['port_no'] == 4
    assert data4['led_states'] == '0001'


def test_returns_occurred_at_equal_to_published_value():
    # Button-press handlers timestamp their debounce record with the
    # published occurred_at.
    device = make_device(1)
    occurred_at = device._publish_board_state(1, 10)

    (data,) = device.mqtt_svc.payloads
    assert data['occurred_at'] == occurred_at
