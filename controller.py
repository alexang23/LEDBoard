from threading import Thread
from time import sleep

import traceback
from config import settings

from mqtt_svc2 import MQTTSvc
from device import LEDButton
import gyro_watchdog

CONTROLLER_WATCHDOG_MAX_GAP = 60  # covers shutdown (2x stop_and_wait(15)) and retry cleanup+backoff


class Controller(Thread):
    def __init__(self, logger, sio = None) -> None:
        Thread.__init__(self)
        self.stop = False
        self.tsc_logger = logger
        # self.sender = sender
        self.alarms = {}
        self.loadport = {}
        self.device_id = settings.DEVICE_ID
        self.log_preserve = 30
        self.mqtt_svc = None
        self.device = None
        self.device2 = None
        
    def run(self):

        while not self.stop:
            gyro_watchdog.touch("Controller", max_gap=CONTROLLER_WATCHDOG_MAX_GAP)
            try:
                # Construct devices before starting MQTTSvc: incoming messages
                # are routed via controller.device/device2 (_route_to_device),
                # which has no None guard, so the MQTT thread must not run
                # while those attributes are still None.
                self.device = LEDButton(devPath='COM'+str(settings.LEDBOARD_COM), board=1, mqtt_svc=None, log=self.tsc_logger)
                if settings.LEDBOARD2_ENABLE:
                    self.device2 = LEDButton(devPath='COM'+str(settings.LEDBOARD2_COM), board=2, mqtt_svc=None, log=self.tsc_logger)
                self.mqtt_svc = MQTTSvc(self, self.tsc_logger)
                self.device.mqtt_svc = self.mqtt_svc
                if settings.LEDBOARD2_ENABLE:
                    self.device2.mqtt_svc = self.mqtt_svc
                self.mqtt_svc.start()
                self.device.daemon = True
                self.device.start()
                self.tsc_logger.info('Controller Starting')
                if settings.LEDBOARD2_ENABLE:
                    self.device2.daemon = True
                    self.device2.start()
                    self.tsc_logger.info('Controller2 Starting')
                
                while not self.stop:
                    try:
                        gyro_watchdog.touch("Controller", max_gap=CONTROLLER_WATCHDOG_MAX_GAP)
                        sleep(0.2)
                    except KeyboardInterrupt:
                        self.tsc_logger.warning('IPC killed by user')
                        self.stop = True
                    except Exception:
                        self.tsc_logger.error(traceback.format_exc())
                        pass

                self.tsc_logger.warning('IPC Stopping')
                if self.device:
                    self.device.stop_and_wait(timeout=15)
                if self.device2:
                    self.device2.stop_and_wait(timeout=15)
                if self.mqtt_svc:
                    self.mqtt_svc.stop = True
                self.tsc_logger.warning('IPC Stopped')
            except Exception:
                # Startup failure: clean up what was built and retry after a
                # short backoff. This used to set self.stop = True, which made
                # the outer while run at most once - a single transient failure
                # at boot killed the controller until manual restart.
                # NOTE: bare except was widened to Exception so that a
                # retry-forever loop cannot swallow SystemExit/GeneratorExit.
                self.tsc_logger.error(traceback.format_exc())
                if self.device:
                    self.device.stop_and_wait(timeout=15)
                    self.device = None
                if self.device2:
                    self.device2.stop_and_wait(timeout=15)
                    self.device2 = None
                if self.mqtt_svc:
                    self.mqtt_svc.stop = True
                    self.mqtt_svc = None
                # heartbeat before the backoff sleep so the retry path is covered
                gyro_watchdog.touch("Controller", max_gap=CONTROLLER_WATCHDOG_MAX_GAP)
                sleep(5)

        gyro_watchdog.unregister("Controller")
                
                
                