# LEDButton (LEDBoard Display Module)

An MQTT-driven LED display board controller for SEMI E84/E87 load port signaling. Messages arrive over MQTT and are translated into visual LED states on the physical board.

## Language

### Operating modes

**AEI mode**:
Operating mode (DEVICE_TYPE=1) in which the board is driven remotely by explicit LED control messages instead of interpreting equipment state messages.
_Avoid_: device type 1, remote mode

**GYRO-300 mode**:
Operating mode (DEVICE_TYPE=0) in which the board derives its display from SEMI E84/E87 equipment state messages (port state, code IDs, RFID events).
_Avoid_: device type 0, IPC mode

### Messages

**LED command message**:
An inbound MQTT message carrying type 6 whose `code_id` selects the command: 0 = LED query, 1 = set one LED (one named LED on one port to one state), 2 = set whole ports (one LED state code per port, applied atomically per board). A message with a missing or unknown `code_id` is ignored. Type 6 is the LED-traffic code, shared with outbound board state and event messages in AEI mode.
_Avoid_: LED control message, type-6 message used alone, LED command without code_id

**LED query**:
The code_id-0 LED command message. With a `port_no`, the board answers with one board state message for that port; without one, the message is fanned out to every board and each board answers for its own ports. The response reads the board's commanded state record immediately, not the physical board's echo.
_Avoid_: get state, status request

**LED query response**:
A board state message carrying `code_id` 6 (LEDBOARD_QUERY), published in answer to an LED query. This outbound `code_id` is unrelated to the inbound LED command message's `code_id`.
_Avoid_: query reply used alone

**Board state message**:
An outbound MQTT message the board publishes to report its `code_id` status value (initial status, LED update, reset-button press, mode-button press, E84-button press, RFID-button press, or LED query response) together with the port's `led_states` LED state code and the LED-traffic type code (6 in AEI mode, 4 in GYRO-300 mode). Note: this outbound `code_id` is a completely separate namespace from the inbound LED command message's `code_id` (0/1/2) and from the equipment code ID carried by inbound equipment state messages, despite sharing the name. Formerly keyed `ledboard_state`.
_Avoid_: status message, heartbeat

**LED update**:
A board state message published after the physical board's read-back frame shows a port's `led_states` changed; it reports the LED state code the board actually echoes, not the commanded one.

**Event message**:
An outbound MQTT message (type 6 in AEI mode, type 4 in GYRO-300 mode) the board publishes to the server to report a device event.
_Avoid_: log message

### LED display

**Port LED**:
One of the four named LEDs per port: Switch, RFID, E84, or Port.
_Avoid_: led, light

**LED state**:
The visual state of a single LED: None, Green, Blue, Red, Flashed Green, Flashed Blue, or Flashed Red.
_Avoid_: color used alone

**LED state code**:
The 4-character `led_states` string describing one port's whole display: one LED-state digit (0-6) per Port LED, in Switch, RFID, E84, Port order.
_Avoid_: led_states used alone, color code

**LED frame**:
The fixed-length serial payload sent to the physical board that encodes the state of every port LED as ASCII bits.
_Avoid_: serial packet
