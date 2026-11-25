"""Tests for led_states and type in outbound board state MQTT messages.

Board state messages (initial status, LED update, reset-button press,
mode-button press) are built by LEDButton._publish_board_state, which
adds the port's 4-digit LED state code (see LEDButton.get_port_states)
and the LED-traffic type code (6 in AEI mode, 4 in GYRO-300 mode)
alongside code_id. These tests use a stub mqtt_svc and an
LEDButton with no serial hardware attached. The ledbutton_cls fixture
(conftest.py) runs every test against both device_io.LEDButton and its
Linux deployment copy device_io_linux.LEDButton.
"""

import threading

from config import settings


class PublishSpy:
    """Records every payload passed to publish, mimicking mqtt_svc2.MQTTSvc."""

    def __init__(self):
        self.payloads = []

    def publish(self, data):
        self.payloads.append(data)
        return True


class WriteSpy:
    """Records every serial command queued to the device."""

    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)


def make_device(ledbutton_cls, board, applied=None):
    """An LEDButton with the attributes the board state and LED update
    paths touch, and no serial hardware attached."""
    device = ledbutton_cls.__new__(ledbutton_cls)
    device.board = board
    device.mqtt_svc = PublishSpy()
    device.device = WriteSpy()
    device.led_idx = {1: 'Switch', 2: 'RFID', 3: 'E84', 4: 'Port'}
    device.applied = dict(applied or {})
    device._applied_lock = threading.Lock()
    device._blink = {}
    device._blink_lock = threading.Lock()
    device.func = {'Port1': 2, 'Port2': 6, 'E841': 18, 'E842': 22,
                   'RFID1': 26, 'RFID2': 30, 'Switch1': 10, 'Switch2': 14}
    device.color = {'Red': [49, 48, 48], 'Green': [48, 49, 48],
                    'Blue': [48, 48, 49], 'None': [48, 48, 48]}
    device.solid_state = {'None': 0, 'Green': 1, 'Blue': 2, 'Red': 3}
    device.led_state = {0: 'None', 1: 'Green', 2: 'Blue', 3: 'Red',
                        4: 'Flashed Green', 5: 'Flashed Blue', 6: 'Flashed Red'}
    device.blink_color = {4: 'Green', 5: 'Blue', 6: 'Red'}
    device.blink_state = {v: k for k, v in device.blink_color.items()}
    device._dirty_ports = set()
    return device


def test_publish_board_state_carries_led_states(ledbutton_cls):
    device = make_device(ledbutton_cls, 1, {('Switch', 1): 2, ('E84', 1): 5})
    device._publish_board_state(1, 10)

    (data,) = device.mqtt_svc.payloads
    assert data['port_no'] == 1
    assert data['code_id'] == 10
    assert data['led_states'] == '2050'
    assert list(data.keys()) == ['port_no', 'type', 'code_id', 'led_states', 'occurred_at']


def test_led_states_defaults_to_zeros_when_never_commanded(ledbutton_cls):
    device = make_device(ledbutton_cls, 1)
    device._publish_board_state(2, 11)

    (data,) = device.mqtt_svc.payloads
    assert data['port_no'] == 2
    assert data['led_states'] == '0000'


def test_board2_maps_global_port_no_to_board_local_port(ledbutton_cls):
    # Board 2 serves global ports 3, 4 as board-local ports 1, 2.
    device = make_device(ledbutton_cls, 2, {('RFID', 1): 6, ('Port', 2): 1})
    device._publish_board_state(3, 10)
    device._publish_board_state(4, 11)

    data3, data4 = device.mqtt_svc.payloads
    assert data3['port_no'] == 3
    assert data3['led_states'] == '0600'
    assert data4['port_no'] == 4
    assert data4['led_states'] == '0001'


def test_returns_occurred_at_equal_to_published_value(ledbutton_cls):
    # Button-press handlers timestamp their debounce record with the
    # published occurred_at.
    device = make_device(ledbutton_cls, 1)
    occurred_at = device._publish_board_state(1, 10)

    (data,) = device.mqtt_svc.payloads
    assert data['occurred_at'] == occurred_at


def test_board_state_type_is_6_in_aei_mode(ledbutton_cls, monkeypatch):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 1)
    device = make_device(ledbutton_cls, 1)
    device._publish_board_state(1, 10)

    (data,) = device.mqtt_svc.payloads
    assert data['type'] == 6


def test_board_state_type_is_4_in_gyro_mode(ledbutton_cls, monkeypatch):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 0)
    device = make_device(ledbutton_cls, 1)
    device._publish_board_state(1, 10)

    (data,) = device.mqtt_svc.payloads
    assert data['type'] == 4


def test_send_event_type_is_6_in_aei_mode(ledbutton_cls, monkeypatch):
    monkeypatch.setattr(settings, 'DEVICE_TYPE', 1)
    device = make_device(ledbutton_cls, 1)
    device.send_event(code=1, subcode=2, msg_text='test')

    (data,) = device.mqtt_svc.payloads
    assert data['type'] == 6


def test_led_update_flush_publishes_ledboard_led(ledbutton_cls):
    assert settings.LEDBOARD_LED == 5
    device = make_device(ledbutton_cls, 1, {('Switch', 1): 2})
    device._dirty_ports.add(1)
    device._flush_led_updates()

    (data,) = device.mqtt_svc.payloads
    assert data['port_no'] == 1
    assert data['code_id'] == settings.LEDBOARD_LED
    assert data['led_states'] == '2000'
    assert device._dirty_ports == set()


def test_led_update_flush_maps_board2_ports(ledbutton_cls):
    device = make_device(ledbutton_cls, 2, {('RFID', 1): 6, ('Port', 2): 1})
    device._dirty_ports.update([1, 2])
    device._flush_led_updates()

    data3, data4 = device.mqtt_svc.payloads
    assert data3['port_no'] == 3
    assert data3['led_states'] == '0600'
    assert data4['port_no'] == 4
    assert data4['led_states'] == '0001'


def test_solid_command_marks_port_dirty_then_flushes(ledbutton_cls):
    device = make_device(ledbutton_cls, 1)
    device.set_led('Switch', 1, 'Green')
    assert device._dirty_ports == {1}

    device._flush_led_updates()
    (data,) = device.mqtt_svc.payloads
    assert data['code_id'] == settings.LEDBOARD_LED
    assert data['led_states'] == '1000'


def test_blink_command_publishes_once_toggles_do_not_republish(ledbutton_cls):
    device = make_device(ledbutton_cls, 1)
    device.start_blink('Port', 1, 'Green')
    assert device._dirty_ports == {1}

    device._flush_led_updates()
    (data,) = device.mqtt_svc.payloads
    assert data['code_id'] == settings.LEDBOARD_LED
    assert data['led_states'] == '0004'

    # Blinker toggle writes record no state change: no new LED update.
    device.set_led('Port', 1, 'Green', from_blinker=True)
    device.set_led('Port', 1, 'None', from_blinker=True)
    assert device._dirty_ports == set()
    device._flush_led_updates()
    assert len(device.mqtt_svc.payloads) == 1


def test_clear_led_updates_drops_pending_after_reset(ledbutton_cls):
    device = make_device(ledbutton_cls, 1)
    device.set_led('E84', 1, 'Red')
    assert device._dirty_ports == {1}

    device._clear_led_updates()
    device._flush_led_updates()
    assert device.mqtt_svc.payloads == []
