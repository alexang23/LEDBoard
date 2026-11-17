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

**LED control message**:
An inbound MQTT message carrying type 6 that sets one named LED on one port to one state.
_Avoid_: type-6 message used alone, LED command

**Board state message**:
An outbound MQTT message the board publishes to report its `ledboard_state` (initial status, reset-button press, or mode-button press).
_Avoid_: status message, heartbeat

**Event message**:
An outbound MQTT message (type 4) the board publishes to the server to report a device event.
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
