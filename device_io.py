import threading


class LEDButton(threading.Thread):
    """Placeholder for the next-generation LED device I/O implementation.

    The detailed driver behavior is intentionally deferred; this stub keeps the
    controller contract stable for the runtime switch while the implementation is
    developed.
    """

    def __init__(self, devPath=None, board=1, mqtt_svc=None, log=None, name=''):
        super().__init__(daemon=True)
        self.devPath = devPath
        self.board = board
        self.mqtt_svc = mqtt_svc
        self.logger = log
        self.name = name
        self.stop = False
        self.state = {'alarm': False}

    def start(self):
        self.stop = False
        super().start()

    def run(self):
        if self.logger:
            self.logger.info(f"board {self.board}: device_io placeholder started")

    def stop_and_wait(self, timeout=None):
        self.stop = True
        if self.is_alive():
            self.join(timeout=timeout)

    def send_event(self, server=False, code=0, subcode=0, msg_text=None, board=1):
        if self.logger:
            self.logger.info(
                f"board {board}: device_io placeholder send_event "
                f"server={server} code={code} subcode={subcode} msg={msg_text}"
            )

    def set_led(self, *args, **kwargs):
        return None

    def data_process(self, *args, **kwargs):
        return None
