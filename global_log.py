from colorlog import StreamHandler, ColoredFormatter
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import logging
import os
# import time

# from app.host_api import g_app
#from fastapi.logger import logger as fastapi_logger
from datetime import datetime # , date, timedelta
# from datetime import timezone
#from fastapi.logging import default_handler
#from main import logger
from config import settings

# console_logger = logging.getLogger()
# console_logger.setLevel(logging.ERROR) # NOTSET, DEBUG, INFO, WARNING, ERROR, CRITICAL
# console_logger.setLevel(settings.LOG_LEVEL)
# formatter = logging.Formatter(
# 	# '[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d] %(message)s [%(pathname)s %(funcName)s]') #,datefmt='%Y%m%d %H:%M:%S')
#     '[%(asctime)s] %(message)s') #,datefmt='%Y%m%d %H:%M:%S')

# ch = logging.StreamHandler()
# ch.setLevel(logging.ERROR)
# ch.setLevel(settings.LOG_LEVEL)
# ch.setFormatter(formatter)
# console_logger.addHandler(ch)

# log_filename = datetime.datetime.now().strftime("%Y-%m-%d_%H_%M_%S.log")
# fh = logging.FileHandler(log_filename)
# fh.setLevel(logging.DEBUG)
# fh.setFormatter(formatter)
# console_logger.addHandler(fh)

#fastapi_logger.setLevel(logging.DEBUG)

class UTCFormatter(logging.Formatter):
    # converter = time.gmtime
    # converter = time.localtime
    
    def formatTime(self, record, datefmt=None):
        # dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        # dt = datetime.fromtimestamp(record.created).astimezone()
        dt = datetime.fromtimestamp(record.created)
        
        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.isoformat(sep=' ', timespec='milliseconds')  # Change 'seconds' to 'milliseconds' or 'microseconds' if needed 
    
        # dt = self.converter(record.created)
        # if datefmt:
        #     s = time.strftime(datefmt, dt)
        # else:
        #     t = time.strftime("%Y-%m-%d %H:%M:%S", dt)
        #     s = "%s,%03d" % (t, record.msecs)
        # return s
    
class LoggerSECS:
    def __init__(self, name):
        self.logger = logging.getLogger(f'{name}_communication')
        self.name = name
        self.configure_logger()
        
    def configure_logger(self):
        try:
            # delete old handler if exist
            for h in self.logger.handlers[:]:
                self.logger.removeHandler(h)
                h.close()
            self.logger.setLevel(logging.DEBUG)
            # self.logger.setLevel(settings.LOG_LEVEL)

            filename = os.path.join(os.getcwd(), 'log/SECS_{}.log'.format(self.name))
            
            if not Path(filename).is_file():
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                log_file_handler = logging.FileHandler(filename, mode='w', encoding=None, delay=False)
            
            commLogFileHandler = TimedRotatingFileHandler(filename, when='midnight', interval=1, backupCount=settings.log_secs_preserve)
            # commLogFileHandler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
            commLogFileHandler.setFormatter(UTCFormatter('%(asctime)s %(message)s'))
            # commLogFileHandler.setLevel(logging.DEBUG)
            # commLogFileHandler.setLevel(settings.LOG_LEVEL)
            self.logger.addHandler(commLogFileHandler)
            
            # stream_handler = StreamHandler()
            # stream_handler.setFormatter(UTCFormatter('%(asctime)s %(message)s'))
            # stream_handler.setLevel(logging.INFO)
            # self.logger.addHandler(stream_handler)
            
        except Exception as err:
            print(str(err))
            
    def get_logger(self):
        return self.logger

class SystemLogFormatter(logging.Formatter):
    def format(self, record):
        record.event = 'SYSTEM'
        record.user = 'SYSTEM'
        # record.url = None
        # record.remote_addr = None

        if 'event' in record.args:
            record.event = record.args.get('event', 'SYSTEM')

        if 'user' in record.args:
            record.user = record.args.get('user', 'SYSTEM')
            
        if 'type' in record.args:
            record.type = record.args.get('user', record.levelname)

        # if has_request_context():
        #     record.url = request.url
        #     record.remote_addr = request.remote_addr
        
        return super().format(record)

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find('/api/mcs_queue') == -1

class Logger:
    def __init__(self, name, file = None) -> None:
        colored_formatter = ColoredFormatter(
            # '%(log_color)s[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s] [%(module)s]:[%(lineno)d]: %(message)s',
            '%(log_color)s[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s]: %(message)s',
            log_colors={
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
                'SERIOUS': 'red,bg_white',
            }
        )
        formatter = SystemLogFormatter('[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s]: %(message)s')
        
        self.log = logging.getLogger(name)
        for handler in self.log.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                self.log.removeHandler(handler)
                handler.close()
        self.log.setLevel(settings.LOG_LEVEL)
        # self.log.setLevel(logging.ERROR)  ## add ?
        # self.log.setLevel(settings.LOG_LEVEL)

        if file:
            # log_file = '{}/log/{}'.format(os.getcwd(), file)
            log_file = os.path.join(os.getcwd(), 'log', file)

            # Create log files if not exist
            if not Path(log_file).is_file():
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                log_file_handler = logging.FileHandler(log_file, mode='w', encoding=None, delay=False)
            
            timed_file_handler = TimedRotatingFileHandler(log_file, when='midnight', backupCount=settings.log_ipc_preserve)
            timed_file_handler.setFormatter(formatter)
            timed_file_handler.setLevel(settings.LOG_LEVEL)
            self.log.addHandler(timed_file_handler)
        
        if settings.LOG_STDOUT:
            stream_handler = StreamHandler()
            stream_handler.setFormatter(colored_formatter)
            stream_handler.setLevel(settings.LOG_LEVEL)
            self.log.addHandler(stream_handler)
        
        # if settings.LOG_SQLITE:
        #     sqlalchemy_handler = SQLAlchemyHandler()
        #     sqlalchemy_handler.setLevel(settings.LOG_LEVEL)
        #     self.log.addHandler(sqlalchemy_handler)

        # if not g_app.debug:
        #     #fastapi_logger.removeHandler(fastapi_logger.default_handler) #default_handler)
        #     fastapi_logger.addHandler(stream_handler)
        
        self.log.info(f'{name} Logger Started')
        # self.log.flush()

    def debug(self, message, args = None):
        if args is not None:
            self.log.debug(message, args)
            #fastapi_logger.debug(message, args)
            # self.errorlog.debug(message, args)
        else:
            self.log.debug(message)
            # #fastapi_logger.debug(message)
            # self.errorlog.debug(message)
            pass
        
    def info(self, message, args = None):
        if args is not None:
            self.log.info(message, args)
            #fastapi_logger.info(message, args)
        else:
            self.log.info(message)
            #fastapi_logger.info(message)
        
    def warning(self, message, args = None):
        if args is not None:
            self.log.warning(message, args)
            #fastapi_logger.warning(message, args)
        else:
            self.log.warning(message)
            #fastapi_logger.warning(message)
        
    def error(self, message, args = None):
        if args is not None:
            self.log.error(message, args)
            #fastapi_logger.error(message, args)
            # self.errorlog.error(message, args)
        else:
            self.log.error(message)
            #fastapi_logger.error(message)
            # self.errorlog.error(message)
            
    # def serious(self, message, args = None):
    #     if args is not None:
    #         self.log.serious(message, args)
    #         #fastapi_logger.serious(message, args)
    #         # self.errorlog.serious(message, args)
    #     else:
    #         self.log.serious(message)
    #         #fastapi_logger.serious(message)
    #         # self.errorlog.serious(message)

class LoggerFastAPI:
    def __init__(self, file = None) -> None:
        # self.logger = logging.getLogger(f'{name}_webapi')
        # self.logger = logging.getLogger(name)
        # self.name = name
        self.name = None
        
        colored_formatter = ColoredFormatter(
            # '%(log_color)s[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s] [%(module)s]:[%(lineno)d]: %(message)s',
            '%(log_color)s[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s]: %(message)s',
            log_colors={
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
                'SERIOUS': 'red,bg_white',
            }
        )
        formatter = SystemLogFormatter('[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s]: %(message)s')
        
        loggers = (
            logging.getLogger(name)
            for name in logging.root.manager.loggerDict
            if name.startswith("uvicorn")
        )
        
        for uvicorn_logger in loggers:
            print(uvicorn_logger.name)
            # uvicorn_logger.handlers = []
        
        self.log = {}
        
        name = 'uvicorn'
        self.log[name] = logging.getLogger(name)
        for handler in self.log[name].handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                self.log[name].removeHandler(handler)
                handler.close()
        self.log[name].setLevel(settings.LOG_LEVEL)
        # self.log.setLevel(logging.ERROR)  ## add ?
        # self.log.setLevel(settings.LOG_LEVEL)
        
        name2 = 'uvicorn.access'
        self.log[name2] = logging.getLogger(name2)
        for handler in self.log[name2].handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                self.log[name2].removeHandler(handler)
                handler.close()
        self.log[name2].setLevel(settings.LOG_LEVEL)
        
        # name3 = 'uvicorn.error'
        # self.log[name3] = logging.getLogger(name3)
        # for handler in self.log[name3].handlers[:]:
        #     if isinstance(handler, logging.StreamHandler):
        #         self.log[name3].removeHandler(handler)
        #         handler.close()
        # self.log[name3].setLevel(logging.INFO)

        if file:
            # log_file = '{}/log/{}'.format(os.getcwd(), file)
            log_file = os.path.join(os.getcwd(), 'log', file)

            # Create log files if not exist
            if not Path(log_file).is_file():
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                log_file_handler = logging.FileHandler(log_file, mode='w', encoding=None, delay=False)
            
            timed_file_handler = TimedRotatingFileHandler(log_file, when='midnight', backupCount=settings.log_api_preserve)
            timed_file_handler.setFormatter(formatter)
            timed_file_handler.setLevel(settings.LOG_LEVEL)
            self.log[name].addHandler(timed_file_handler)
            self.log[name2].addHandler(timed_file_handler)
            # self.log[name3].addHandler(timed_file_handler)
        
        if settings.LOG_STDOUT:
            stream_handler = StreamHandler()
            stream_handler.setFormatter(colored_formatter)
            stream_handler.setLevel(settings.LOG_LEVEL)
            self.log[name].addHandler(stream_handler)
            self.log[name2].addHandler(stream_handler)
            # self.log[name3].addHandler(stream_handler)
        
        # if settings.LOG_SQLITE:
        #     sqlalchemy_handler = SQLAlchemyHandler()
        #     sqlalchemy_handler.setFormatter(formatter)
        #     sqlalchemy_handler.setLevel(settings.LOG_LEVEL)
        #     self.log[name].addHandler(sqlalchemy_handler)
        #     self.log[name2].addHandler(sqlalchemy_handler)
        #     # self.log[name3].addHandler(sqlalchemy_handler)

        # if not g_app.debug:
        #     #fastapi_logger.removeHandler(fastapi_logger.default_handler) #default_handler)
        #     fastapi_logger.addHandler(stream_handler)
        self.name = name
        self.log[name].info(f'HostAPI Logger Started')
        # self.log.flush()
        
    def get_logger(self):
        if self.name:
            return self.log[self.name]
        else:
            return None

    def debug(self, message, args = None):
        if args is not None:
            for log in self.log:
                log.debug(message, args)
        else:
            for log in self.log:
                log.debug(message)
        
    def info(self, message, args = None):
        if args is not None:
            for log in self.log:
                log.info(message, args)
        else:
            for log in self.log:
                log.info(message)
        
    def warning(self, message, args = None):
        if args is not None:
            for log in self.log:
                log.warning(message, args)
        else:
            for log in self.log:
                log.warning(message)
        
    def error(self, message, args = None):
        if args is not None:
            for log in self.log:
                log.error(message, args)
        else:
            for log in self.log:
                log.error(message)

class LoggerFile:
    def __init__(self, name, file = None) -> None:
        colored_formatter = ColoredFormatter(
            # '%(log_color)s[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s] [%(module)s]:[%(lineno)d]: %(message)s',
            '%(log_color)s[%(asctime)s] : %(message)s',
            log_colors={
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
                'SERIOUS': 'red,bg_white',
            }
        )
        formatter = SystemLogFormatter('[%(asctime)s] : %(message)s')
        
        self.log = logging.getLogger(name)
        for handler in self.log.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                self.log.removeHandler(handler)
                handler.close()
        self.log.setLevel(logging.INFO)
        # self.log.setLevel(logging.ERROR)  ## add ?
        # self.log.setLevel(settings.LOG_LEVEL)

        if file:
            # log_file = '{}/log/{}'.format(os.getcwd(), file)
            log_file = os.path.join(os.getcwd(), 'log', file)

            # Create log files if not exist
            if not Path(log_file).is_file():
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                log_file_handler = logging.FileHandler(log_file, mode='w', encoding=None, delay=False)
            
            timed_file_handler = TimedRotatingFileHandler(log_file, when='midnight', backupCount=settings.log_ipc_preserve)
            timed_file_handler.setFormatter(formatter)
            timed_file_handler.setLevel(logging.INFO)
            self.log.addHandler(timed_file_handler)
        
        # stream_handler = StreamHandler()
        # stream_handler.setFormatter(colored_formatter)
        # stream_handler.setLevel(logging.INFO)
        # self.log.addHandler(stream_handler)
        
        self.log.info(f'{name} Logger Started\n')
        # self.log.flush()

    def debug(self, message, args = None):
        if args is not None:
            self.log.debug(message, args)
        else:
            self.log.debug(message)
        
    def info(self, message, args = None):
        if args is not None:
            self.log.info(message, args)
        else:
            self.log.info(message)
        
    def warning(self, message, args = None):
        if args is not None:
            self.log.warning(message, args)
        else:
            self.log.warning(message)
        
    def error(self, message, args = None):
        if args is not None:
            self.log.error(message, args)
        else:
            self.log.error(message)

# glogger = Logger('api', 'api.log')
# glogger = LoggerFastAPI('api.log')
glogger = None



