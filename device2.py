# 20210714
import time
import serial
import struct
import threading
import collections
from collections import OrderedDict
from config import settings
from global_log import AsyncLoggerFile
import gyro_watchdog
import queue
import re

e84Path = '/dev/ttyUSB0'

READER_JOIN_TIMEOUT = 2.0  # seconds; bounded so a wedged reader can't hang stop()

def led_frame(bit_index: int | None = None, start: str = 'A') -> tuple[int, ...]:
    """
    Build a 34-byte LED board frame: start char + 32 ASCII '0'/'1' payload + 'B'.
    bit_index (1..32) selects which payload character is set to '1'.
    start is 'A' for normal frames, 'C' for the reset frame.
    """
    frame = [ord('0')] * 34
    frame[0], frame[-1] = ord(start), ord('B')
    if bit_index is not None:
        frame[bit_index] = ord('1')
    return tuple(frame)

initialize = led_frame()
reset = led_frame(start='C')
B1Red =   led_frame(2)
B1Green = led_frame(3)
B1Blue =  led_frame(4)
B2Red =   led_frame(6)
B2Green = led_frame(7)
B2Blue =  led_frame(8)
B3Red =   led_frame(10)
B3Green = led_frame(11)
B3Blue =  led_frame(12)
B4Red =   led_frame(14)
B4Green = led_frame(15)
B4Blue =  led_frame(16)
B5Red =   led_frame(18)
B5Green = led_frame(19)
B5Blue =  led_frame(20)
B6Red =   led_frame(22)
B6Green = led_frame(23)
B6Blue =  led_frame(24)
B7Red =   led_frame(26)
B7Green = led_frame(27)
B7Blue =  led_frame(28)
B8Red =   led_frame(30)
B8Green = led_frame(31)
B8Blue =  led_frame(32)

def led2text(data_orig: bytes, encoding: str = 'utf-8', logger=None) -> str:
    """
    Validates a 32-character binary string (decoded from bytes), and if valid,
    translates it into a detailed text description for LED states grouped by ports.

    Args:
        data: A bytes object containing the 32-character binary data.
        encoding: The character encoding to use when decoding the bytes (default: 'utf-8').
        logger: Optional logger used for invalid-content diagnostics.

    Returns:
        A string representing the LED states grouped by ports, or "invalid content"
        if the input data is not valid.
    """
    try:
        data_str = data_orig.decode(encoding)
    except UnicodeDecodeError:
        if logger:
            logger.error(f"Error decoding bytes with {encoding} encoding.")
        return "invalid content"

    # 1. Validate if the received data (32 characters) contains only '0' or '1' and is exactly 32 chars long
    data = data_str[1:33]
    if not re.fullmatch(r'^[01]{32}$', data):
        if logger:
            logger.warning(f"{data} Data is invalid (contains non-0/1 characters or incorrect length).")
        return "invalid content"

    result_status = "correct"

    all_led_descriptions = {}

    # Loop through each LED group (4 characters per LED) to get individual descriptions
    for i in range(8): # 8 LEDs (0 to 7)
        led_number = i + 1
        start_index = i * 4
        # Slice from the decoded string
        led_chars = data[start_index : start_index + 4]

        button = led_chars[0]
        red = led_chars[1]
        green = led_chars[2]
        blue = led_chars[3]

        current_led_description = "" # Start with an empty string for the light/button part

        # Button state
        if button == '1':
            current_led_description += "press"

        # Light state
        light_state = ""
        if red == '0' and green == '0' and blue == '0':
            light_state = "no" # No light
        elif red == '1':
            light_state = "red"
        elif green == '1':
            light_state = "green"
        elif blue == '1':
            light_state = "blue"
        # Note: This logic prioritizes red > green > blue if multiple are '1'.
        # Adjust if simultaneous colors like yellow (red+green) are expected.

        # Combine button and light state
        if current_led_description != "" and light_state != "":
            current_led_description += "_" + light_state
        elif light_state != "":
            current_led_description = light_state

        # Handle the case where there's no press and no light
        if button == '0' and red == '0' and green == '0' and blue == '0':
            current_led_description = "no"

        all_led_descriptions[led_number] = current_led_description # Store by LED number

    port1_led_numbers = [3, 7, 5, 1]
    port2_led_numbers = [4, 8, 6, 2]

    port1_descriptions = []
    for led_num in port1_led_numbers:
        port1_descriptions.append(all_led_descriptions[led_num])
    port1_string = "1: " + ", ".join(port1_descriptions)

    port2_descriptions = []
    for led_num in port2_led_numbers:
        port2_descriptions.append(all_led_descriptions[led_num])
    port2_string = "2: " + ", ".join(port2_descriptions)

    final_description = f"{port1_string}   {port2_string}"

    return final_description

class SerialPortHandler:
    def __init__(self, port='COM14', board=1, controller=None, baudrate=9600, timeout=0.5, max_queue_size=500, logger=None, logger_led=None):
        self.port = port
        self.board = board
        self.controller = controller
        self.baudrate = baudrate
        self.timeout = timeout
        self.logger = logger
        self.logger_led = logger_led

        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        self.ser.reset_input_buffer()
        time.sleep(2)  # Give time for connection

        # Queues
        self.incoming_queue = queue.Queue(maxsize=max_queue_size)
        self.outgoing_queue = queue.Queue()

        self.running = False
        self.reconnect = False
        self.last_update = time.time()

        # Threads
        self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)

    def start(self):
        if not self.ser.is_open:
            self.ser.open()
            self.ser.reset_input_buffer()
            time.sleep(2)  # Give time for connection
        self.reconnect = False
        self.running = True
        self.reader_thread.start()
        self.controller.send_event(True, 0, 0, 'connect', self.board)

    def stop(self):
        self.running = False
        # Best effort: unblock a reader wedged in a native read (e.g. USB-serial
        # surprise removal) so the bounded join below can complete.
        try:
            self.ser.cancel_read()
        except Exception:
            pass
        if self.reader_thread is not None:
            if self.reader_thread.is_alive():
                self.reader_thread.join(timeout=READER_JOIN_TIMEOUT)
            if self.reader_thread.is_alive():
                # Keep the watchdog name registered: the wedged thread has
                # stopped touching and the monitor will flag it with a dump.
                self.logger.error(f"board {self.board}: reader thread did not exit within {READER_JOIN_TIMEOUT}s during stop()")
            else:
                gyro_watchdog.unregister(f"SerialPortHandler-board{self.board}")
        try:
            if self.ser.is_open:
                self.ser.close()
        except Exception as exc:
            self.logger.error(f"board {self.board}: serial port close error : {exc}")
        self.controller.send_event(True, 0, 1, 'close', self.board)

    def _read_loop(self):
        start = b'A'
        end = b'B'
        start2 = b'C'
        end2 = b'D'
        head = None
        correct = [b'0', b'1']
        in_message = False
        buffer = bytearray()
        prev_income = bytearray()
        income_count = 0

        while self.running:
            gyro_watchdog.touch(f"SerialPortHandler-board{self.board}", max_gap=10)
            try:
                dtime = time.time() - self.last_update
                if dtime > 10:
                    self.reconnect = True

                byte = self.ser.read(1)
                if not byte:
                    continue  # timeout or no data

                if not in_message:
                    if byte == start or byte == start2:
                        head = byte
                        in_message = True
                        buffer = bytearray()  # start fresh
                        buffer.extend(byte)

                else: # start to record data
                    if (head == start and byte == end) or (head == start2 and byte == end2):
                        buffer.extend(end)

                        # --- START: New logic to prioritize outgoing queue ---
                        # Check if there's data in the outgoing_queue and attempt to send one item
                        # before queueing the just-received incoming message.
                        #
                        # DELIBERATE optimistic local echo: pending commands are merged into the
                        # just-received frame, the merged frame is written to the board, and that
                        # SAME merged frame (not the raw received one) is queued below as the
                        # reported state. LEDButton.run() consumes incoming_queue for
                        # button-press edge detection (res[idx]==49 and status[idx]==48) and
                        # prev-state tracking, so queueing the raw frame instead would
                        # re-report a press the 'B' ack below already cleared (duplicate press
                        # event) and show stale LED colors until the board's next physical echo.
                        # If outgoing_queue is empty here, buffer is passed through unmutated.
                        if not self.outgoing_queue.empty():
                            data = None 
                            try:
                                while not self.outgoing_queue.empty():
                                    data = self.outgoing_queue.get_nowait() # Get item
                                    if data[0] == 'C': # color command
                                        buffer[data[1]] = data[2][0]
                                        buffer[data[1]+1] = data[2][1]
                                        buffer[data[1]+2] = data[2][2]
                                    elif data[0] == 'B': # button command
                                        buffer[data[1]] = 48
                                
                                if self.ser.is_open:
                                    if settings.LEDBOARD_DEBUG_ENABLE:
                                        print(f"board {self.board}: >>>>>> write {bytes(buffer)}  # {self.led2text(bytes(buffer))}")
                                    self.logger_led.info(f"board {self.board}: >>>>>> write {bytes(buffer)}  # {self.led2text(bytes(buffer))}")
                                    self.ser.write(bytes(buffer))
                                    self.outgoing_queue.task_done() # Item processed
                                else:
                                    # Port not open, requeue the item
                                    self.logger.error(f"board {self.board}: Warning: Serial port not open in _read_loop. Requeuing data: {buffer}")
                            except queue.Empty:
                                # Queue became empty between check and get, do nothing.
                                pass
                            except serial.SerialException as se_write:
                                self.logger.error(f"board {self.board}: Serial port write error in _read_loop: {str(se_write)}. Requeuing data: {buffer}")
                            except Exception as e_prio_write:
                                self.logger.error(f"board {self.board}: Error during prioritized outgoing write in _read_loop: {str(e_prio_write)}")
                        # --- END: New logic to prioritize outgoing queue ---

                        try:
                            send_income = True
                            # If a command above was merged into buffer, this queue entry is the
                            # commanded state (optimistic local echo), not the board's own report.
                            income = bytes(buffer)
                            self.last_update = time.time()
                            if prev_income == income:
                                income_count += 1
                                if income_count >= 10:
                                    income_count = 0
                                else:
                                    send_income = False
                            else:
                                if income == bytes(reset):
                                    print(f"board {self.board}: <<<<<< read  {income} reset  # {self.led2text(income)}")
                                elif income == bytes(initialize):
                                    print(f"board {self.board}: <<<<<< read  {income} initialize  # {self.led2text(income)}")
                                else:
                                    print(f"board {self.board}: <<<<<< read  {income}  # {self.led2text(income)}")
                                prev_income = income
                                income_count = 0
                            if send_income:
                                self.incoming_queue.put_nowait(income)
                        except queue.Full:
                            self.logger.error(f"board {self.board}: Warning: Incoming queue full. Dropping line.")

                        in_message = False
                        head = None

                    elif byte in correct:
                        buffer.extend(byte)
                    else:
                        in_message = False
                        head = None

            except Exception as err:
                self.logger.error(f"board {self.board}: Serial port read error: {str(err)}")
                self.reconnect = True

    def write(self, data):
        """Queue data to be written asynchronously."""
        self.outgoing_queue.put(data)

    def read(self, block=True, timeout=None):
        """Read a line from incoming queue."""
        try:
            return self.incoming_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def led2text(self, data_orig: bytes, encoding: str = 'utf-8') -> str:
        return led2text(data_orig, encoding, self.logger)

class LEDButton(threading.Thread):
    def __init__(self, devPath, board=1, mqtt_svc=None, log=None, name=''):
        threading.Thread.__init__(self)
        self.devPath = devPath
        self.state = {'alarm':False}

        self.errorCode = 0
        self.errorMsg = ''
        self.pspl = False
        self.stop = False
        self.svr_enable = True
        self.cmd_queue = collections.deque()
        self.timeout = 30
        self.lastTime = time.time()
        self.count = 0
        self.device = None
        self.board = board
        self.mqtt_svc = mqtt_svc
        self.logger = log
        self.logger_led = AsyncLoggerFile(f"ledboard_{self.board}", f"ledboard_{self.board}.log")
        self.name = name
        self.status = list(initialize)
        self.idx = {1:1, 2:5, 3:9, 4:13, 5:17, 6:21, 7:25, 8:29}
        self.btntime = {1:time.time(), 2:time.time(), 3:time.time(), 4:time.time(), 5:time.time(), 6:time.time(), 7:time.time(), 8:time.time()}
        self.func = {'Port1':2, 'Port2':6, 'E841':18, 'E842':22, 'RFID1':26, 'RFID2':30, 'Switch1':10, 'Switch2':14}
        self.color = {'Red':[49, 48, 48], 'Green':[48, 49, 48], 'Blue':[48, 48, 49], 'None':[48, 48, 48]}
        self._blink = {}
        self._blink_lock = threading.Lock()

    def led2text(self, data_orig: bytes, encoding: str = 'utf-8') -> str:
        return led2text(data_orig, encoding, self.logger)


    def cmd(self, data):
        try:
            data = list(data)
            self.cmd_queue.append(struct.pack('>BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB', *data))
        except Exception as err:
            self.logger.error(f"board {self.board}: {str(err)}")

    def initial_status(self):
        
        data2 = OrderedDict()
        port_no = 3 if self.board == 2 else 1
        data2['port_no'] = port_no
        data2['dual_port'] = 0
        data2['ledboard_state'] = settings.LEDBOARD_INITIAL
        data2['occurred_at'] = time.time()
        res_mqtt = self.mqtt_svc.publish(data2)
        
        data = OrderedDict()
        data['port_no'] = port_no + 1
        data['dual_port'] = 0
        data['ledboard_state'] = settings.LEDBOARD_INITIAL
        data['occurred_at'] = time.time()
        res_mqtt = self.mqtt_svc.publish(data)

    def on_notify(self, data):
        self.cmd_queue.append(data)

    def set_led(self, fname, port_no, color, data=None, from_blinker=False):
        try:
            if fname == 'Port' and not from_blinker:
                self.stop_blink(port_no)
            data = ['C', self.func[f"{fname}{port_no}"], self.color[color]]
            self.device.write(data)
        except Exception as err:
            self.logger.error(f"board {self.board}: {str(err)}")

    def start_blink(self, port_no_led):
        try:
            with self._blink_lock:
                self._blink[port_no_led] = True
        except Exception as err:
            self.logger.error(f"board {self.board}: {str(err)}")

    def stop_blink(self, port_no_led):
        try:
            with self._blink_lock:
                self._blink.pop(port_no_led, None)
        except Exception as err:
            self.logger.error(f"board {self.board}: {str(err)}")

    def _blink_loop(self):
        while not self.stop:
            time.sleep(0.5)
            try:
                with self._blink_lock:
                    ports = list(self._blink.items())
                for port_no_led, on in ports:
                    if port_no_led not in self._blink:
                        continue
                    self.set_led('Port', port_no_led, 'Green' if on else 'None', from_blinker=True)
                    with self._blink_lock:
                        if port_no_led in self._blink:
                            self._blink[port_no_led] = not on
            except Exception as err:
                self.logger.error(f"board {self.board}: blink error {str(err)}")

    def data_process(self, payload):
        try:

            port_no = payload['port_no']

            if self.board == 1:
                if port_no > 2:
                    return
                port_no_led = port_no
            else: # self.board == 2
                if port_no < 3:
                    return
                port_no_led = port_no - 2
            
            if payload['type'] == 2: # RFID sense/change
                if payload['mode'] == 2:
                    self.set_led('Switch', port_no_led, 'Blue')
                    if 'LRC' in payload:
                        if payload['LRC']:
                            self.set_led('Port', port_no_led, 'Green')
                        else:
                            self.set_led('Port', port_no_led, 'Red')
                        return
                    if 'WIP' in payload:
                        if payload['WIP']:
                            self.set_led('E84', port_no_led, 'Green')
                        else:
                            self.set_led('E84', port_no_led, 'Red')
                        return

                    if payload['code_id'] == 128:
                        self.set_led('RFID', port_no_led, 'Red')
                    #[2025-05-27 01:09:50,461] mqtt : on_message topic=IPC, qos=2, data=b'{"device_id": "BEBLO16", "port_id": "2", "port_no": 2, "dual_port": 0, "mode": 2, "carrier_id": "211C83183", "type": 2, "stream": -1, "function": -1, "code_id": 0, "sub_id": 1, "msg_text": "ps sensor 1, place rfid", "status": "", "occurred_at": 1748275790.367923}'
                    elif payload['code_id'] == 0 and payload['sub_id'] == 1 and "place rfid" in payload['msg_text']:
                        self.set_led('Port', port_no_led, 'None')
                        self.set_led('E84', port_no_led, 'None')
                        self.set_led('RFID', port_no_led, 'Green')
                        print('###### 2-2-1')
                    #[2025-05-27 03:45:21,749] [INFO] [SYSTEM] [SYSTEM]: mqtt : on_message topic=IPC, qos=2, data=b'{"device_id": "BEBLO16", "port_id": "1", "port_no": 1, "dual_port": 0, "mode": 2, "carrier_id": "225C85056", "type": 2, "stream": -1, "function": -1, "code_id": 0, "sub_id": 0, "msg_text": "ps sensor 0, remove rfid", "status": "", "occurred_at": 1748285121.6867406}'
                    elif payload['code_id'] == 0 and payload['sub_id'] == 0 and "remove rfid" in payload['msg_text'] and payload['prev_carrier_id'] != '' and payload['carrier_id'] == '':
                        self.set_led('Port', port_no_led, 'None')
                        self.set_led('E84', port_no_led, 'None')
                        self.set_led('RFID', port_no_led, 'None')
                        print('###### 2-2-2')
                    else:
                        self.set_led('RFID', port_no_led, 'None')
                        print('###### 2-2-3')

                elif payload['mode'] == 1:
                    if payload['carrier_id'] != '':
                        self.set_led('RFID', port_no_led, 'Green')
                    else:
                        self.set_led('RFID', port_no_led, 'None')
                    self.set_led('Switch', port_no_led, 'Green')
                    print('###### 2-1')
                else:
                    self.set_led('RFID', port_no_led, 'None')
                    self.set_led('Switch', port_no_led, 'None')
                    print('###### 2-0')

                if payload['eqp_state'] == 1: # Alarm
                    self.set_led('Port', port_no_led, 'Red')
                return

            elif payload['type'] == 3: # Equipment message
                if payload['process_state'] == 1:
                    self.set_led('Port', port_no_led, 'Blue')
                elif payload['process_state'] == 2:
                    self.start_blink(port_no_led)
                elif payload['port_state'] == 128 or payload['code_id'] == 128 or len(payload['alarm_text']) > 0 or payload['eqp_state'] == 1: # Alarm
                    self.set_led('Port', port_no_led, 'Red')
                    print('###### 0-3-128-0')

                else:
                    if payload['mode'] == 1:
                        self.set_led('Port', port_no_led, 'Green')
                    else:
                        self.set_led('Port', port_no_led, 'None')
                    print('###### 0-3-0-0')
                return

            elif payload['type'] == 4: # LEDBoard message
                if payload['stream'] == 6 and payload['function'] == 11 and payload['code_id'] == 0 and payload['sub_id'] == 0 :
                    if payload['mode'] == 1: # Auto:1
                        self.set_led('Port', port_no_led, 'Green')
                        self.set_led('E84', port_no_led, 'Green')
                        self.set_led('RFID', port_no_led, 'None')
                        self.set_led('Switch', port_no_led, 'Green')
                        print('###### 0-4-611-00-0')
                    elif payload['mode'] == 2: # Manual:2
                        self.set_led('Port', port_no_led, 'None')
                        self.set_led('E84', port_no_led, 'None')
                        self.set_led('RFID', port_no_led, 'None')
                        self.set_led('Switch', port_no_led, 'Blue')
                        print('###### 0-4-611-00-1')
                    else:
                        self.set_led('Port', port_no_led, 'None')
                        self.set_led('E84', port_no_led, 'None')
                        self.set_led('RFID', port_no_led, 'None')
                        self.set_led('Switch', port_no_led, 'None')
                        print('###### 0-4-611-00-2')

            else: # payload['type'] != 2

                # [2025-05-27 02:00:33,001] mqtt : on_message topic=IPC, qos=2, data=b'{"device_id": "BEBLO16", "port_no": 1, "port_id": "LP1", "port_state": 1, "carrier_id": "", "dual_port": 0, "mode": 1, "load": 1, "alarm_id": 0, "alarm_text": "", "type": 0, "stream": -1, "function": -1, "code_id": 32771, "sub_id": 1, "msg_text": "Change to Auto", "status": "{\\"P\\": 0, \\"I\\": 0, \\"O\\": 128, \\"G\\": 0, \\"E\\": 193}", "occurred_at": 1748278832.938678}'
                if payload['code_id'] == 32771 and payload['sub_id'] == 1: # Change to Auto 0x8003 0001
                    self.set_led('Port', port_no_led, 'None')
                    self.set_led('E84', port_no_led, 'None')
                    self.set_led('RFID', port_no_led, 'None')
                    self.set_led('Switch', port_no_led, 'Green')
                    print('###### 0-1')
                # [2025-05-27 02:00:40,623] mqtt : on_message topic=IPC, qos=2, data=b'{"device_id": "BEBLO16", "port_no": 1, "port_id": "LP1", "port_state": 1, "carrier_id": "", "dual_port": 0, "mode": 2, "load": 1, "alarm_id": 0, "alarm_text": "", "type": 0, "stream": -1, "function": -1, "code_id": 32771, "sub_id": 0, "msg_text": "Change to Manual", "status": "{\\"P\\": 0, \\"I\\": 0, \\"O\\": 192, \\"G\\": 0, \\"E\\": 193}", "occurred_at": 1748278840.514376}'
                elif payload['code_id'] == 32771 and payload['sub_id'] == 0: # Change to Manual 0x8003 0000
                    self.set_led('Port', port_no_led, 'None')
                    self.set_led('E84', port_no_led, 'None')
                    self.set_led('RFID', port_no_led, 'None')
                    self.set_led('Switch', port_no_led, 'Blue')
                    print('###### 0-0')
                    return
                elif payload['code_id'] == 25 or payload['code_id'] == 260: # 0x0019 0x0104
                    return
                
                if payload['mode'] == 1 and (payload['port_state'] == 1 or payload['port_state'] == 2 or payload['port_state'] == 5 or payload['port_state'] == 6 or payload['port_state'] == 20 or payload['port_state'] == 21 or payload['port_state'] == 24 or payload['port_state'] == 25): # 0:Idle, 1:Ready to Load, 2:Ready to Unload, 3:Load Start, 4:Unload Start, 5:Load Complete, 6:Unload Complete, 7:Auto Recover, Loading, Unloading, Complete, Idle can use for Port Ready, E84 state
                    self.set_led('Port', port_no_led, 'Green')
                    self.set_led('E84', port_no_led, 'Green')
                    print('###### 0-1256')
                elif payload['mode'] == 1 and (payload['port_state'] == 3 or payload['port_state'] == 4 or payload['port_state'] == 22 or payload['port_state'] == 23): # 3:Loading, 4:Unloading
                    self.set_led('Port', port_no_led, 'Green')
                    self.set_led('E84', port_no_led, 'Blue')
                    print('###### 0-34')
                else:
                    self.set_led('Port', port_no_led, 'None')
                    self.set_led('E84', port_no_led, 'None')
                    print('###### 0-not 123456')

                if payload['port_state'] == 128 or payload['code_id'] == 128 or len(payload['alarm_text']) > 0 or payload['eqp_state'] == 1: # Alarm
                    self.set_led('Port', port_no_led, 'Red')
                    print('###### 0-128-0')

                if payload['type'] == 0 and payload['stream'] == 6 and payload['function'] == 11:
                    if payload['mode'] == 1: # Auto:1, Manual:2
                        self.set_led('Switch', port_no_led, 'Green')
                        print('###### 0-611-0')
                    elif payload['mode'] == 2:
                        self.set_led('Switch', port_no_led, 'Blue')
                        print('###### 0-611-1')
                    else:
                        self.set_led('Switch', port_no_led, 'None')
                        print('###### 0-611-2')
                else:
                    if payload['mode'] == 1: # Auto:1, Manual:2
                        self.set_led('Switch', port_no_led, 'Green')
                        print('###### 0-611-3')
                    elif payload['mode'] == 2:
                        self.set_led('Switch', port_no_led, 'Blue')
                        print('###### 0-611-4')
                    else:
                        self.set_led('Switch', port_no_led, 'None')
                        print('###### 0-611-5')

        except Exception as err:
            self.logger.error(f"device : data_process : {str(err)}")
            return False
    
        return True
    
    def send_event(self, server=False, code=0, subcode=0, msg_text=None, board=1):
        try:
            data = OrderedDict()

            if server:
                data['Server'] = True
            data['device_id'] = settings.DEVICE_ID
            data['board_id'] = board
            data['type'] = 4
            data['code_id'] = code
            data['sub_id'] = subcode
            data['msg_text'] = msg_text
            data['occurred_at'] = time.time()
            data['version'] = f"{settings.SW_VERSION}"
            self.mqtt_svc.publish(data)

        except Exception as err:
            self.logger.error(str(err))

    def stop_and_wait(self, timeout=None):
        # Mirrors MQTTSvc.stop_and_wait: flag the loop, wait for it to exit,
        # then close the underlying serial handler (reader thread + port).
        if threading.current_thread() is not self:
            self.stop = True
            if self.is_alive():
                self.join(timeout=timeout)
                if timeout is not None and self.is_alive():
                    self.logger.warning(f"board {self.board}: thread did not exit within {timeout}s during stop_and_wait")
        else:
            self.stop = True
        if self.device is not None:
            try:
                self.device.stop()
            except Exception as err:
                self.logger.error(f"board {self.board}: serial stop error : {err}")

    def run(self):

        try:
            self.device = SerialPortHandler(port=self.devPath, board=self.board, controller=self, logger=self.logger, logger_led=self.logger_led)
            self.device.start()

        except Exception as err:
            self.logger.error(str(err))

        self.initial_status()

        blink_thread = threading.Thread(target=self._blink_loop, daemon=True)
        blink_thread.start()

        while not self.stop:
            # max_gap covers the None-device recovery path (sleep 5 + sleep 10)
            # and the reconnect branch (stop + sleep 5 + construct + sleep 2 + sleep 3).
            gyro_watchdog.touch(f"LEDButton-board{self.board}", max_gap=30)
            try:
                if not self.device:
                    if self.stop:
                        break
                    self.send_event(True, 128, 2, 'reconnect device', self.board)
                    self.logger.warning(f"board {self.board}, device is None. reconnect device")
                    time.sleep(5)
                    self.device = SerialPortHandler(port=self.devPath, board=self.board, controller=self, logger=self.logger, logger_led=self.logger_led)
                    self.device.start()
                    time.sleep(3)
                    self.initial_status()
                    continue

                # device write
                while self.cmd_queue :
                    if not self.device.ser.is_open:
                        break
                    data = self.cmd_queue.popleft()
                    if self.svr_enable :
                        self.data_process(data)

                if self.device.reconnect:
                    if self.stop:
                        break
                    self.send_event(True, 128, 2, 'reconnect device', self.board)
                    self.logger.warning(f"board {self.board} reconnect device")
                    self.device.stop()
                    time.sleep(5)
                    self.device = SerialPortHandler(port=self.devPath, board=self.board, controller=self, logger=self.logger, logger_led=self.logger_led)
                    self.device.start()
                    time.sleep(3)
                    self.initial_status()
                    continue

                buf = self.device.read(timeout=1)

                if buf is None:
                    continue

                if len(buf) != 34:
                    self.logger.info(f"board {self.board}, Warning : read length != 34, buf : {buf}")
                    continue

                # check data
                self.count = 0
                self.lastTime = time.time()
                if self.errorCode == 7777:
                    self.state['alarm'] = False
                    self.errorCode = 0
                    self.errorMsg = ''

                res = list(buf)
                if settings.LEDBOARD_DEBUG_ENABLE:
                    self.logger_led.info(f"board {self.board}: read {buf}  # {self.led2text(buf)}")

                if res != self.status:
                    self.logger_led.info(f"board {self.board}: #### prev {bytes(self.status)}  # {self.led2text(bytes(self.status))}")
                    self.logger_led.info(f"board {self.board}: #### new  {buf}  # {self.led2text(buf)}")
                    self.logger.info(f"board {self.board}: #### prev {bytes(self.status)}  # {self.led2text(bytes(self.status))}")
                    self.logger.info(f"board {self.board}: #### new  {buf}  # {self.led2text(buf)}")

                data = OrderedDict()

                if (res[0] == 67 and res[33] == 66) or \
                   (res[0] == 65 and \
                    res[33] == 66 and \
                    res[2] == 48 and res[3] == 48 and res[4] == 48 and \
                    res[6] == 48 and res[7] == 48 and res[8] == 48 and \
                    res[10] == 48 and res[11] == 48 and res[12] == 48 and \
                    res[14] == 48 and res[15] == 48 and res[16] == 48 and \
                    res[18] == 48 and res[19] == 48 and res[20] == 48 and \
                    res[22] == 48 and res[23] == 48 and res[24] == 48 and \
                    res[26] == 48 and res[27] == 48 and res[28] == 48 and \
                    res[30] == 48 and res[31] == 48 and res[32] == 48):

                    data2 = OrderedDict()
                    port_no = 3 if self.board == 2 else 1
                    data2['port_no'] = port_no
                    data2['dual_port'] = 0
                    data2['ledboard_state'] = settings.LEDBOARD_INITIAL
                    data2['occurred_at'] = time.time()
                    res_mqtt = self.mqtt_svc.publish(data2)
                    
                    data1 = OrderedDict()
                    data1['port_no'] = port_no + 1
                    data1['dual_port'] = 0
                    data1['ledboard_state'] = settings.LEDBOARD_INITIAL
                    data1['occurred_at'] = time.time()
                    res_mqtt = self.mqtt_svc.publish(data1)

                    if res[1] == 48 and res[5] == 48 and res[9] == 48 and res[13] == 48 and \
                        res[17] == 48 and res[21] == 48 and res[25] == 48 and res[29] == 48 :
                        self.status = res[:]
                        time.sleep(1)
                        continue

                if res[self.idx[1]] == 49 and self.status[self.idx[1]] == 48:
                    if time.time() - self.btntime[1] > settings.LEDBOARD_BUTTON_TIME:
                        port_no = 3 if self.board == 2 else 1
                        data['port_no'] = port_no
                        data['dual_port'] = 0
                        data['ledboard_state'] = settings.LEDBOARD_RESET
                        data['occurred_at'] = time.time()
                        res_mqtt = self.mqtt_svc.publish(data)
                        self.btntime[1] = data['occurred_at']
                    
                    res[self.idx[1]] = 48
                    button = ['B', self.idx[1]]
                    self.device.write(button)

                if res[self.idx[2]] == 49 and self.status[self.idx[2]] == 48:
                    if time.time() - self.btntime[2] > settings.LEDBOARD_BUTTON_TIME:
                        port_no = 3 if self.board == 2 else 1
                        data['port_no'] = port_no + 1
                        data['dual_port'] = 0
                        data['ledboard_state'] = settings.LEDBOARD_RESET
                        data['occurred_at'] = time.time()
                        res_mqtt = self.mqtt_svc.publish(data)
                        self.btntime[2] = data['occurred_at']
                    
                    res[self.idx[2]] = 48
                    button = ['B', self.idx[2]]
                    self.device.write(button)

                if res[self.idx[3]] == 49 and self.status[self.idx[3]] == 48:
                    if time.time() - self.btntime[3] > settings.LEDBOARD_BUTTON_TIME:
                        port_no = 3 if self.board == 2 else 1
                        data['port_no'] = port_no
                        data['dual_port'] = 0
                        data['ledboard_state'] = settings.LEDBOARD_MODE
                        data['occurred_at'] = time.time()
                        res_mqtt = self.mqtt_svc.publish(data)
                        self.btntime[3] = data['occurred_at']
                    
                    res[self.idx[3]] = 48
                    button = ['B', self.idx[3]]
                    self.device.write(button)

                if res[self.idx[4]] == 49 and self.status[self.idx[4]] == 48:
                    if time.time() - self.btntime[4] > settings.LEDBOARD_BUTTON_TIME:
                        port_no = 3 if self.board == 2 else 1
                        data['port_no'] = port_no + 1
                        data['dual_port'] = 0
                        data['ledboard_state'] = settings.LEDBOARD_MODE
                        data['occurred_at'] = time.time()
                        res_mqtt = self.mqtt_svc.publish(data)
                        self.btntime[4] = data['occurred_at']
                        
                    res[self.idx[4]] = 48
                    button = ['B', self.idx[4]]
                    self.device.write(button)

                if res[self.idx[5]] == 49 and self.status[self.idx[5]] == 48:
                    res[self.idx[5]] = 48
                    button = ['B', self.idx[5]]
                    self.device.write(button)

                if res[self.idx[6]] == 49 and self.status[self.idx[6]] == 48:
                    res[self.idx[6]] = 48
                    button = ['B', self.idx[6]]
                    self.device.write(button)

                if res[self.idx[7]] == 49 and self.status[self.idx[7]] == 48:
                    res[self.idx[7]] = 48
                    button = ['B', self.idx[7]]
                    self.device.write(button)

                if res[self.idx[8]] == 49 and self.status[self.idx[8]] == 48:
                    res[self.idx[8]] = 48
                    button = ['B', self.idx[8]]
                    self.device.write(button)

                self.status = res[:]

            except Exception as err:
                self.logger.error(f"board {self.board}: error={str(err)}")
                self.send_event(True, 128, 1, 'could not open port', self.board)
                time.sleep(10)

        gyro_watchdog.unregister(f"LEDButton-board{self.board}")


if __name__ == "__main__":
    device = LEDButton('COM14')
    device.daemon = True
    device.start()

    stop = False
    time.sleep(1)

    while not stop:
        tmp = input('input:')
        tmp = str(tmp)
        if tmp == '11':
            device.cmd(B1Red)
        elif tmp == '12':
            device.cmd(B1Green)
        elif tmp == '13':
            device.cmd(B1Blue)
        elif tmp == '21':
            device.cmd(B2Red)
        elif tmp == '22':
            device.cmd(B2Green)
        elif tmp == '23':
            device.cmd(B2Blue)
        elif tmp == '31':
            device.cmd(B3Red)
        elif tmp == '32':
            device.cmd(B3Green)
        elif tmp == '33':
            device.cmd(B3Blue)
        elif tmp == '41':
            device.cmd(B4Red)
        elif tmp == '42':
            device.cmd(B4Green)
        elif tmp == '43':
            device.cmd(B4Blue)
        elif tmp == '51':
            device.cmd(B5Red)
        elif tmp == '52':
            device.cmd(B5Green)
        elif tmp == '53':
            device.cmd(B5Blue)
        elif tmp == '61':
            device.cmd(B6Red)
        elif tmp == '62':
            device.cmd(B6Green)
        elif tmp == '63':
            device.cmd(B6Blue)
        elif tmp == '71':
            device.cmd(B7Red)
        elif tmp == '72':
            device.cmd(B7Green)
        elif tmp == '73':
            device.cmd(B7Blue)
        elif tmp == '81':
            device.cmd(B8Red)
        elif tmp == '82':
            device.cmd(B8Green)
        elif tmp == '83':
            device.cmd(B8Blue)
        elif tmp == 'q':
            break
        time.sleep(1)
	
