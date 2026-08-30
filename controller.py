from threading import Thread
from time import sleep
from datetime import datetime

import collections
import re
import traceback
from config import Settings, settings

from mqtt_svc2 import MQTTSvc
from device import LEDButton
import logging
from logging.handlers import TimedRotatingFileHandler
import os


class Controller(Thread):
    def __init__(self, logger, sio = None) -> None:
        Thread.__init__(self)
        self.stop = False
        self.tsc_logger = logger
        # self.sender = sender
        self.receive_queue = collections.deque()
        self.alarms = {}
        self.loadport = {}
        self.device_id = settings.DEVICE_ID
        self.log_preserve = 30
        self.mqtt_svc = None
        self.device = None
        self.device2 = None
        
    def data_process(self, data):
        print(data)
        
    def run(self):

        while not self.stop:
            try:
                self.mqtt_svc = MQTTSvc(self, self.tsc_logger)
                self.mqtt_svc.start()
                self.device = LEDButton(devPath='COM'+str(settings.LEDBOARD_COM), board=1, mqtt_svc=self.mqtt_svc, log=self.tsc_logger)
                if settings.LEDBOARD2_ENABLE:
                    self.device2 = LEDButton(devPath='COM'+str(settings.LEDBOARD2_COM), board=2, mqtt_svc=self.mqtt_svc, log=self.tsc_logger)
                self.device.daemon = True
                self.device.start()
                self.tsc_logger.info('Controller Starting')
                if settings.LEDBOARD2_ENABLE:
                    self.device2.daemon = True
                    self.device2.start()
                    self.tsc_logger.info('Controller2 Starting')
                
                while not self.stop:
                    try:
                        while self.receive_queue:
                            data = self.receive_queue.popleft()
                            self.data_process(data)

                        sleep(0.2)
                    except KeyboardInterrupt:
                        self.tsc_logger.warning('IPC killed by user')
                        self.stop = True
                    except:
                        self.tsc_logger.error(traceback.format_exc())
                        pass
                else:
                    self.tsc_logger.warning('IPC Stopping')
                    if self.device:
                        self.device.stop_and_wait(timeout=15)
                    if settings.LEDBOARD2_ENABLE:
                        if self.device2:
                            self.device2.stop_and_wait(timeout=15)
                    if self.mqtt_svc:
                        self.mqtt_svc.stop = True
                    self.tsc_logger.warning('IPC Stopped')
            except:
                self.tsc_logger.error(traceback.format_exc())
                if self.device:
                    self.device.stop_and_wait(timeout=15)
                if settings.LEDBOARD2_ENABLE:
                    if self.device2:
                        self.device2.stop_and_wait(timeout=15)
                if self.mqtt_svc:
                    self.mqtt_svc.stop = True
                self.stop = True
                
                
                