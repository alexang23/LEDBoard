"""Publish a type-6 AEI LED command message to a live MQTT broker.

Companion to tests/test_aei_led_control.py for manual verification against a
running LEDBoard application (DEVICE_TYPE=1, AEI mode). The application subscribes
to f"{MQTT_TOPIC}" (mqtt_svc2.connect_MQTT_service) and selects the AEI
handler by the payload's type == 6, so by default this script publishes to
the base topic ("IPC").

The message's code_id selects the command (see GLOSSARY: LED command
message):
    0  query  : publish the port's (or, with --all, every port's) led_states
                as a board state message with code_id 6
    1  set one: set the LED named by --led-no on --port-no to --led-state
    2  set many: set whole ports from --ports, e.g.
                --ports 1=1204 --ports 2=0350

Examples:
    uv run python tests/send_aei_test_message.py
    uv run python tests/send_aei_test_message.py --port-no 2 --led-no 4 --led-state 3
    uv run python tests/send_aei_test_message.py --code-id 0
    uv run python tests/send_aei_test_message.py --code-id 0 --port-no 1
    uv run python tests/send_aei_test_message.py --code-id 2 --ports 1=1204 --ports 2=0350
    uv run python tests/send_aei_test_message.py --host 192.168.1.50 --topic IPC

Expected behaviour on the board: code_id=1 sets the LED named by --led-no
(1=Switch, 2=RFID, 3=E84, 4=Port) on the port given by --port-no to the
state given by --led-state (0=None, 1=Green, 2=Blue, 3=Red); flashed states
(4-6) blink the board's LED while solid states light it directly. code_id=0
makes the board answer with a board state message (code_id=6) carrying the
requested port's led_states code.
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
        description='Publish a type-6 AEI LED command message.'
    )
    parser.add_argument('--host', default=settings.MQTT_IP,
                        help='MQTT broker host (default: %(default)s)')
    parser.add_argument('--port', type=int, default=settings.MQTT_PORT,
                        help='MQTT broker port (default: %(default)s)')
    parser.add_argument('--topic', default=settings.MQTT_TOPIC,
                        help='topic to publish to (default: %(default)s)')
    parser.add_argument('--code-id', type=int, default=1, choices=[0, 1, 2],
                        help='command: 0=query led_states, 1=set one LED, '
                             '2=set whole ports (default: %(default)s)')
    parser.add_argument('--all', action='store_true',
                        help='code_id=0 only: query every port (omits port_no)')
    parser.add_argument('--port-no', type=int, default=1, choices=[1, 2, 3, 4],
                        help='load port number (default: %(default)s)')
    parser.add_argument('--led-no', type=int, default=4, choices=[1, 2, 3, 4],
                        help='code_id=1 only: LED 1=Switch, 2=RFID, 3=E84, '
                             '4=Port (default: %(default)s)')
    parser.add_argument('--led-state', type=int, default=1,
                        help='code_id=1 only: state 0=None, 1=Green, 2=Blue, '
                             '3=Red, 4-6=Flashed (default: %(default)s)')
    parser.add_argument('--ports', action='append', default=[], metavar='PORT_NO=LED_STATES',
                        help='code_id=2 only: set one port, e.g. 1=1204 '
                             '(4 digits, one LED-state digit 0-6 per Port LED '
                             'in Switch/RFID/E84/Port order); repeatable')
    args = parser.parse_args()

    payload = {'type': 6, 'code_id': args.code_id}
    if args.code_id == 0:
        if not args.all:
            payload['port_no'] = args.port_no
        meaning = (f"query every port's led_states"
                   if args.all else
                   f"query port {args.port_no}'s led_states")
    elif args.code_id == 1:
        payload['port_no'] = args.port_no
        payload['led_no'] = args.led_no
        payload['led_state'] = args.led_state
        meaning = f'port {args.port_no} {LED_NAMES[args.led_no]} LED -> {LED_STATES[args.led_state]}'
    else:
        try:
            payload['ports'] = [
                {'port_no': int(pair.split('=', 1)[0]),
                 'led_states': pair.split('=', 1)[1]}
                for pair in args.ports
            ]
        except (ValueError, IndexError):
            parser.error('--ports entries must look like PORT_NO=LED_STATES, e.g. 1=1204')
        if not payload['ports']:
            parser.error('--code-id 2 needs at least one --ports PORT_NO=LED_STATES entry')
        meaning = 'set ports: ' + ', '.join(
            f"port {entry['port_no']} -> {entry['led_states']}" for entry in payload['ports'])
    text = json.dumps(payload)

    print(f'publishing to {args.host}:{args.port} topic={args.topic}')
    print(f'payload  : {text}')
    print(f'meaning  : {meaning}')

    publish.single(args.topic, text, hostname=args.host, port=args.port)

    print('done.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
