"""Publish a type-6 AEI LED control message to a live MQTT broker.

Companion to tests/test_aei_led_control.py for manual verification against a
running LEDBoard application (DEVICE_TYPE=1, AEI mode). The application
subscribes to f"{MQTT_TOPIC}" (mqtt_svc2.connect_MQTT_service) and selects
the AEI handler by the payload's type == 6, so by default this script
publishes to the base topic ("IPC").

Examples:
    uv run python tests/send_aei_test_message.py
    uv run python tests/send_aei_test_message.py --port-no 2 --led-no 4 --led-state 3
    uv run python tests/send_aei_test_message.py --host 192.168.1.50 --topic IPC

Expected behaviour on the board: the LED named by --led-no (1=Switch, 2=RFID,
3=E84, 4=Port) on the port given by --port-no shows the state given by
--led-state (0=None, 1=Green, 2=Blue, 3=Red). Note that flashed states
(4-6) currently produce no change on the board; see
tests/test_aei_led_control.py.
"""

import argparse
import json
import os
import sys

# Make the repo root importable so the broker/topic defaults come from the
# project's own config (config.ini), whether run via uv or plain python.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paho.mqtt import publish  # noqa: E402

from config import settings  # noqa: E402

LED_NAMES = {1: 'Switch', 2: 'RFID', 3: 'E84', 4: 'Port'}
LED_STATES = {
    0: 'None', 1: 'Green', 2: 'Blue', 3: 'Red',
    4: 'Flashed Green', 5: 'Flashed Blue', 6: 'Flashed Red',
}


def main():
    parser = argparse.ArgumentParser(
        description='Publish a type-6 AEI LED control message.'
    )
    parser.add_argument('--host', default=settings.MQTT_IP,
                        help='MQTT broker host (default: %(default)s)')
    parser.add_argument('--port', type=int, default=settings.MQTT_PORT,
                        help='MQTT broker port (default: %(default)s)')
    parser.add_argument('--topic', default=settings.MQTT_TOPIC,
                        help='topic to publish to (default: %(default)s)')
    parser.add_argument('--port-no', type=int, default=1, choices=[1, 2, 3, 4],
                        help='load port number (default: %(default)s)')
    parser.add_argument('--led-no', type=int, default=4, choices=[1, 2, 3, 4],
                        help='LED: 1=Switch, 2=RFID, 3=E84, 4=Port (default: %(default)s)')
    parser.add_argument('--led-state', type=int, default=1,
                        help='state: 0=None, 1=Green, 2=Blue, 3=Red, 4-6=Flashed '
                             '(default: %(default)s)')
    args = parser.parse_args()

    payload = {
        'port_no': args.port_no,
        'type': 6,
        'led_no': args.led_no,
        'led_state': args.led_state,
    }
    text = json.dumps(payload)

    print(f'publishing to {args.host}:{args.port} topic={args.topic}')
    print(f'payload  : {text}')
    print(f'meaning  : port {args.port_no} '
          f'{LED_NAMES[args.led_no]} LED -> {LED_STATES[args.led_state]}')

    publish.single(args.topic, text, hostname=args.host, port=args.port)

    print('done.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
