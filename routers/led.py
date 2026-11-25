"""WebAPI for the LED display in AEI mode.

POST /api/led/set        set a single LED (led_no) of a port to led_state
POST /api/led/set/port   apply a 4-digit LED state code to a single port
POST /api/led/set/ports  apply a 4-digit LED state code to multiple ports
POST /api/led/state      report the LED state code of a single port
GET  /api/led/state/all  report the LED state code of every live port

Every route answers HTTP 200 with one envelope:
    {'Success': bool, 'State': 'OK'|'NG', 'ErrorCode': int, 'Message': str, ...}
The envelope is the single source of truth for success/failure. All routes
are restricted to AEI mode (DEVICE_TYPE=1).

POST enqueues the same type-6 LED control payloads the MQTT "IPC/AEI" topic
carries (via LEDButton.on_notify), so HTTP and MQTT share one LED-control
path; a success response means the commands were accepted, not that the
board has physically echoed them yet.

GET /api/led/state/all reports the last commanded state per LED, recorded
by LEDButton.set_led / start_blink for every command path (AEI type-6 and
the RFID/E84 business logic) - not the board's physical serial echo.
POST /api/led/state reads the same recorded state for a single port.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix='/api/led')

AEI_DEVICE_TYPE = 1

# Board layout pinned from device_io.LEDButton: board 1 serves ports 1-2,
# board 2 (when enabled) serves ports 3-4.
BOARD1_PORTS = (1, 2)
BOARD2_PORTS = (3, 4)

# led_states digit i (1-based) is LED i's state: 0=None, 1=Green, 2=Blue,
# 3=Red, 4=Flashed Green, 5=Flashed Blue, 6=Flashed Red.
LED_STATES_LENGTH = 4
VALID_LED_STATES = '0123456'


class LedStateRequest(BaseModel):
    port_no: int
    led_states: str


class LedSetRequest(BaseModel):
    port_no: int
    led_no: int
    led_state: int


class LedPortStateRequest(BaseModel):
    port_no: int


class LedPortStates(BaseModel):
    port_no: int
    led_states: str


class LedPortsRequest(BaseModel):
    ports: list[LedPortStates]


def _envelope(success, error_code=0, message=''):
    return {
        'Success': success,
        'State': 'OK' if success else 'NG',
        'ErrorCode': error_code,
        'Message': message,
    }


def _ng(error_code, message):
    return _envelope(False, error_code, message)


def _port_exists(port_no):
    """True when port_no exists on this machine: within an enabled board."""
    if port_no in BOARD1_PORTS:
        return True
    return port_no in BOARD2_PORTS and settings.LEDBOARD2_ENABLE


def _device_for_port(tsc, port_no):
    """The LEDButton owning port_no, or None when it is not connected."""
    if port_no in BOARD1_PORTS:
        return tsc.device
    return tsc.device2


def _port_no_led(port_no):
    """Board-local port number: board 2 ports (3, 4) map to (1, 2)."""
    return port_no - 2 if port_no in BOARD2_PORTS else port_no


@router.post('/set/port')
async def set_port_led_states(request: Request, body: LedStateRequest):
    if settings.DEVICE_TYPE != AEI_DEVICE_TYPE:
        return _ng(403, 'AEI mode is not enabled')

    if not _port_exists(body.port_no):
        return _ng(403, 'port_no is not exist')

    device = _device_for_port(request.app.state.tsc, body.port_no)
    if device is None:
        return _ng(503, 'device is not connected')

    if len(body.led_states) != LED_STATES_LENGTH or any(ch not in VALID_LED_STATES for ch in body.led_states):
        return _ng(422, 'invalid led_no/led_state')

    for led_no, digit in enumerate(body.led_states, start=1):
        device.on_notify({'port_no': body.port_no, 'type': 6, 'code_id': 1, 'led_no': led_no, 'led_state': int(digit)})

    return {**_envelope(True), 'Port': {'port_no': body.port_no, 'led_states': body.led_states}}


@router.post('/set/ports')
async def set_ports_led_states(request: Request, body: LedPortsRequest):
    if settings.DEVICE_TYPE != AEI_DEVICE_TYPE:
        return _ng(403, 'AEI mode is not enabled')

    if not body.ports:
        return _ng(422, 'ports is required')

    # All-or-nothing: every entry is validated before anything is enqueued,
    # so a bad port or state code anywhere rejects the whole request.
    for entry in body.ports:
        if not _port_exists(entry.port_no):
            return _ng(403, 'port_no is not exist')

        device = _device_for_port(request.app.state.tsc, entry.port_no)
        if device is None:
            return _ng(503, 'device is not connected')

        if len(entry.led_states) != LED_STATES_LENGTH or any(ch not in VALID_LED_STATES for ch in entry.led_states):
            return _ng(422, 'invalid led_no/led_state')

    for entry in body.ports:
        device = _device_for_port(request.app.state.tsc, entry.port_no)
        for led_no, digit in enumerate(entry.led_states, start=1):
            device.on_notify({'port_no': entry.port_no, 'type': 6, 'code_id': 1, 'led_no': led_no, 'led_state': int(digit)})

    return {
        **_envelope(True),
        'Length': len(body.ports),
        'Ports': [{'port_no': entry.port_no, 'led_states': entry.led_states} for entry in body.ports],
    }


@router.post('/set')
async def set_led(request: Request, body: LedSetRequest):
    if settings.DEVICE_TYPE != AEI_DEVICE_TYPE:
        return _ng(403, 'AEI mode is not enabled')

    if not _port_exists(body.port_no):
        return _ng(403, 'port_no is not exist')

    device = _device_for_port(request.app.state.tsc, body.port_no)
    if device is None:
        return _ng(503, 'device is not connected')

    if body.led_no not in range(1, LED_STATES_LENGTH + 1) or body.led_state not in range(len(VALID_LED_STATES)):
        return _ng(422, 'invalid led_no/led_state')

    device.on_notify({'port_no': body.port_no, 'type': 6, 'code_id': 1, 'led_no': body.led_no, 'led_state': body.led_state})

    return {**_envelope(True), 'Port': {'port_no': body.port_no, 'led_no': body.led_no, 'led_state': body.led_state}}


@router.post('/state')
async def get_led_state(request: Request, body: LedPortStateRequest):
    if settings.DEVICE_TYPE != AEI_DEVICE_TYPE:
        return _ng(403, 'AEI mode is not enabled')

    if not _port_exists(body.port_no):
        return _ng(403, 'port_no is not exist')

    device = _device_for_port(request.app.state.tsc, body.port_no)
    if device is None:
        return _ng(503, 'device is not connected')

    return {**_envelope(True), 'Port': {'port_no': body.port_no, 'led_states': device.get_port_states(_port_no_led(body.port_no))}}


@router.get('/state/all')
async def get_all_led_states(request: Request):
    if settings.DEVICE_TYPE != AEI_DEVICE_TYPE:
        return _ng(403, 'AEI mode is not enabled')

    # Live ports: within LOAD_PORT_NUMBER on an enabled board, with a
    # connected device. Any missing device fails the whole request.
    live = []
    for port_no in range(1, settings.LOAD_PORT_NUMBER + 1):
        if _port_exists(port_no):
            live.append((port_no, _device_for_port(request.app.state.tsc, port_no)))

    if any(device is None for _, device in live):
        return _ng(503, 'device is not connected')

    ports = [
        {'port_no': port_no, 'led_states': device.get_port_states(_port_no_led(port_no))}
        for port_no, device in live
    ]
    return {**_envelope(True), 'Length': len(ports), 'Ports': ports}
