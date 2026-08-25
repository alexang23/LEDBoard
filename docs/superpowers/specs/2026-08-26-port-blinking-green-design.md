# Design: Port LED blinking green on `process_state == 2`

Date: 2026-08-26
Scope: SEMI E84/E87 LEDBoard display module (`device.py` only)

## Objective

When an Equipment message (`payload['type'] == 3`) with `payload['process_state'] == 2`
arrives, the affected port's `Port` LED must blink green. Blinking must never block the
`LEDButton` thread.

## Requirements

1. Blink interval: 1 second full period (green on 0.5 s, off 0.5 s).
2. Stop condition: any subsequent `set_led('Port', ...)` command for that port
   (e.g., Blue / Red / None from another MQTT payload) cancels the blink and shows the
   new color.
3. Non-blocking: LED state changes are enqueued via the existing
   `SerialPortHandler.outgoing_queue` path; no `time.sleep()` in the LEDButton thread
   for blinking purposes.
4. Both ports on a board may blink simultaneously and independently.
5. "Blinking green" = alternating Green ↔ None (off).

## Architecture

All changes in `device.py`, class `LEDButton`:

- **Blink registry**: `self._blink = {port_no_led: bool(on_state)}` guarded by
  `self._blink_lock = threading.Lock()`.
- **Blinker thread**: daemon thread running `_blink_loop()`, started at the top of
  `run()`. Ticks every 0.5 s; for each registered port it calls
  `set_led('Port', n, 'Green' | 'None')` (internal, non-cancelling) then flips the
  stored on/off bit → full period of 1 s. Exits when `self.stop` is set.
- **`start_blink(port_no_led)`** / **`stop_blink(port_no_led)`**: register/unregister a
  port in the blink registry. `start_blink` does not write LEDs directly; first tick
  shows green immediately.
- **`set_led(...)` change**: new keyword param `from_blinker=False`. When
  `fname == 'Port'` and not `from_blinker`, cancel any active blink for that port before
  applying the color. This yields override semantics for all existing callers without
  touching them.
- **`data_process` change** (line ~800): `process_state == 2` branch calls
  `start_blink(port_no_led)` instead of solid `set_led('Port', ..., 'Green')`.

## Error handling

- `_blink_loop()` body wrapped in try/except; errors logged via `self.logger.error`
  following existing conventions.
- Thread lifecycle: exits when `self.stop` is True. Reconnect logic in `run()` untouched;
  writes during reconnect fail gracefully in `SerialPortHandler` as they do today.

## Testing

Manual verification per repo convention: `uv run python LEDBoard.py`. Blink behavior is
hardware/MQTT driven; verify via `ledboard_*.log` output showing alternating Green/None
writes for the port after a `process_state == 2` payload, and that any later
`set_led('Port', ...)` payload ends the blink.
