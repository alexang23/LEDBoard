from colorlog import StreamHandler, ColoredFormatter
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
from pathlib import Path

import atexit
import logging
import os
import queue
import re
import time

# from app.host_api import g_app
#from fastapi.logger import logger as fastapi_logger
from datetime import datetime, timezone # , date, timedelta
# from datetime import timezone
#from fastapi.logging import default_handler
#from main import logger
from config import settings

LOG_DATE_FORMAT = '%Y-%m-%d'


def get_dated_log_path(filename, for_datetime=None):
    target_datetime = for_datetime or datetime.now()
    source_path = Path(filename)
    return source_path.with_name(
        f'{source_path.stem}_{target_datetime.strftime(LOG_DATE_FORMAT)}{source_path.suffix}'
    )


class DailyPatternTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(
        self,
        filename,
        when='midnight',
        interval=1,
        backupCount=0,
        encoding=None,
        delay=False,
        utc=False,
        atTime=None,
        errors=None,
    ):
        self.source_path = Path(filename)
        if str(self.source_path.parent) not in ('', '.'):
            os.makedirs(self.source_path.parent, exist_ok=True)
        dated_path = get_dated_log_path(self.source_path)
        super().__init__(
            str(dated_path),
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            utc=utc,
            atTime=atTime,
            errors=errors,
        )
        # Enforce retention at startup as well: a process restarted several
        # times within one day may never reach a midnight rollover, so without
        # this, old dated files could accumulate past backupCount between
        # restarts. No-op when backupCount <= 0.
        self._delete_old_files()

    def _dated_path_for(self, current_time):
        # Match the parent class convention: respect self.utc so the date
        # suffix always corresponds to the actual rollover boundary.
        if self.utc:
            event_dt = datetime.fromtimestamp(current_time, tz=timezone.utc)
        else:
            event_dt = datetime.fromtimestamp(current_time)
        return get_dated_log_path(self.source_path, event_dt)

    def _delete_old_files(self):
        if self.backupCount <= 0:
            return

        keep_count = self.backupCount + 1
        current_file = Path(self.baseFilename).resolve()
        # Match only files with a strict _YYYY-MM-DD date suffix so unrelated
        # files sharing the stem prefix are never deleted.
        dated_name_pattern = re.compile(
            r'^' + re.escape(self.source_path.stem)
            + r'_\d{4}-\d{2}-\d{2}'
            + re.escape(self.source_path.suffix) + r'$'
        )
        dated_logs = sorted(
            path
            for path in self.source_path.parent.glob(f'{self.source_path.stem}_*{self.source_path.suffix}')
            if path.is_file() and dated_name_pattern.match(path.name)
        )

        if len(dated_logs) <= keep_count:
            return

        for path in dated_logs[: len(dated_logs) - keep_count]:
            if path.resolve() == current_file:
                continue
            try:
                path.unlink()
            except OSError:
                continue

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None

        current_time = int(time.time())
        new_path = self._dated_path_for(current_time)
        if self.namer is not None:
            new_path = Path(self.namer(str(new_path)))
        self.baseFilename = os.path.abspath(str(new_path))

        if not self.delay:
            self.stream = self._open()

        new_rollover_at = self.computeRollover(current_time)
        while new_rollover_at <= current_time:
            new_rollover_at = new_rollover_at + self.interval
        self.rolloverAt = new_rollover_at
        self._delete_old_files()

class UTCFormatter(logging.Formatter):
    # 'event_time' is a non-standard LogRecord attribute attached via
    # logging's extra= mechanism (e.g. e84_event._log_command passes
    # extra={"event_time": ...} through AsyncLoggerFile, and the attribute
    # survives the QueueHandler pickle round-trip). It carries the original
    # event timestamp so the log shows when the event actually happened
    # instead of when the record was emitted. Records without it fall back
    # to record.created (the emit time).
    def formatTime(self, record, datefmt=None):
        event_time = getattr(record, 'event_time', None)
        if isinstance(event_time, datetime):
            dt = event_time
        elif event_time is not None:
            dt = datetime.fromtimestamp(event_time)
        else:
            dt = datetime.fromtimestamp(record.created)

        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.isoformat(sep=' ', timespec='milliseconds')  # Change 'seconds' to 'milliseconds' or 'microseconds' if needed

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

            commLogFileHandler = DailyPatternTimedRotatingFileHandler(filename, when='midnight', interval=1, backupCount=settings.log_secs_preserve)
            # commLogFileHandler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
            commLogFileHandler.setFormatter(UTCFormatter('%(asctime)s %(message)s'))
            self.logger.addHandler(commLogFileHandler)

        except Exception:
            logging.getLogger(__name__).exception(
                'Failed to configure SECS logger %s', self.name
            )

    def get_logger(self):
        return self.logger

class SystemLogFormatter(logging.Formatter):
    def format(self, record):
        record.event = 'SYSTEM'
        record.user = 'SYSTEM'
        # record.url = None
        # record.remote_addr = None

        if isinstance(record.args, dict) and 'event' in record.args:
            record.event = record.args.get('event', 'SYSTEM')

        if isinstance(record.args, dict) and 'user' in record.args:
            record.user = record.args.get('user', 'SYSTEM')

        if isinstance(record.args, dict) and 'type' in record.args:
            record.type = record.args.get('type', record.levelname)

        # if has_request_context():
        #     record.url = request.url
        #     record.remote_addr = request.remote_addr

        original_format = self._style._fmt
        if record.event == 'SYSTEM' and record.user == 'SYSTEM':
            self._style._fmt = original_format.replace(' [%(event)s] [%(user)s]', '')

        try:
            return super().format(record)
        finally:
            self._style._fmt = original_format


class EventOnlyLogFormatter(SystemLogFormatter):
    def format(self, record):
        if isinstance(record.args, dict):
            args = dict(record.args)
        else:
            args = {}

        args.setdefault('event', datetime.fromtimestamp(record.created).strftime('%M:%S,%f')[:-3])
        record.args = args
        return super().format(record)

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find('/api/mcs_queue') == -1

class Logger:
    def __init__(self, name, file = None, event_only = False) -> None:
        stream_format = (
            '%(log_color)s[%(asctime)s] [%(levelname)s] [%(threadName)s]: %(message)s'
            if event_only
            else '%(log_color)s[%(asctime)s] [%(levelname)s] [%(threadName)s] [%(event)s] [%(user)s]: %(message)s'
        )
        file_format = (
            '[%(asctime)s] [%(levelname)s] [%(threadName)s]: %(message)s'
            if event_only
            else '[%(asctime)s] [%(levelname)s] [%(threadName)s] [%(event)s] [%(user)s]: %(message)s'
        )
        colored_formatter = ColoredFormatter(
            # '%(log_color)s[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s] [%(module)s]:[%(lineno)d]: %(message)s',
            stream_format,
            log_colors={
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
                'SERIOUS': 'red,bg_white',
            }
        )
        formatter_class = EventOnlyLogFormatter if event_only else SystemLogFormatter
        formatter = formatter_class(file_format)

        self.log = logging.getLogger(name)
        for handler in self.log.handlers[:]:
            self.log.removeHandler(handler)
            handler.close()
        self.log.setLevel(settings.LOG_LEVEL)

        if file:
            # log_file = '{}/log/{}'.format(os.getcwd(), file)
            log_file = os.path.join(os.getcwd(), 'log', file)

            timed_file_handler = DailyPatternTimedRotatingFileHandler(log_file, when='midnight', backupCount=settings.log_ipc_preserve)
            timed_file_handler.setFormatter(formatter)
            timed_file_handler.setLevel(settings.LOG_LEVEL)
            self.log.addHandler(timed_file_handler)

        if settings.LOG_STDOUT:
            stream_handler = StreamHandler()
            stream_handler.setFormatter(colored_formatter)
            stream_handler.setLevel(settings.LOG_LEVEL)
            self.log.addHandler(stream_handler)

        self.log.info(f'###### {name} logger started ######')
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

    def error(self, message, args = None, exc_info = False):
        if args is not None:
            self.log.error(message, args, exc_info=exc_info)
            #fastapi_logger.error(message, args)
            # self.errorlog.error(message, args)
        else:
            self.log.error(message, exc_info=exc_info)
            #fastapi_logger.error(message)
            # self.errorlog.error(message)

    def critical(self, message, args = None, exc_info = False):
        if args is not None:
            self.log.critical(message, args, exc_info=exc_info)
        else:
            self.log.critical(message, exc_info=exc_info)

class LoggerFastAPI:
    def __init__(self, file = None) -> None:
        # self.logger = logging.getLogger(f'{name}_webapi')
        # self.logger = logging.getLogger(name)
        # self.name = name
        self.name = None

        colored_formatter = ColoredFormatter(
            # '%(log_color)s[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s] [%(module)s]:[%(lineno)d]: %(message)s',
            '%(log_color)s[%(asctime)s] [%(levelname)s] [%(threadName)s] [%(event)s] [%(user)s]: %(message)s',
            log_colors={
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
                'SERIOUS': 'red,bg_white',
            }
        )
        formatter = SystemLogFormatter('[%(asctime)s] [%(levelname)s] [%(threadName)s] [%(event)s] [%(user)s]: %(message)s')

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

        if file:
            # log_file = '{}/log/{}'.format(os.getcwd(), file)
            log_file = os.path.join(os.getcwd(), 'log', file)

            timed_file_handler = DailyPatternTimedRotatingFileHandler(log_file, when='midnight', backupCount=settings.log_api_preserve)
            timed_file_handler.setFormatter(formatter)
            timed_file_handler.setLevel(settings.LOG_LEVEL)
            self.log[name].addHandler(timed_file_handler)
            self.log[name2].addHandler(timed_file_handler)

        if settings.LOG_STDOUT:
            stream_handler = StreamHandler()
            stream_handler.setFormatter(colored_formatter)
            stream_handler.setLevel(settings.LOG_LEVEL)
            self.log[name].addHandler(stream_handler)
            self.log[name2].addHandler(stream_handler)

        self.name = name
        self.log[name].info(f'###### {name} logger started ######')
        # self.log.flush()

    def get_logger(self):
        if self.name:
            return self.log[self.name]
        else:
            return None

    def debug(self, message, args = None):
        if args is not None:
            for log in self.log.values():
                log.debug(message, args)
        else:
            for log in self.log.values():
                log.debug(message)

    def info(self, message, args = None):
        if args is not None:
            for log in self.log.values():
                log.info(message, args)
        else:
            for log in self.log.values():
                log.info(message)

    def warning(self, message, args = None):
        if args is not None:
            for log in self.log.values():
                log.warning(message, args)
        else:
            for log in self.log.values():
                log.warning(message)

    def error(self, message, args = None, exc_info = False):
        if args is not None:
            for log in self.log.values():
                log.error(message, args, exc_info=exc_info)
        else:
            for log in self.log.values():
                log.error(message, exc_info=exc_info)

    def critical(self, message, args = None, exc_info = False):
        if args is not None:
            for log in self.log.values():
                log.critical(message, args, exc_info=exc_info)
        else:
            for log in self.log.values():
                log.critical(message, exc_info=exc_info)

class LoggerFile:
    def __init__(self, name, file = None) -> None:
        colored_formatter = ColoredFormatter(
            # '%(log_color)s[%(asctime)s] [%(levelname)s] [%(event)s] [%(user)s] [%(module)s]:[%(lineno)d]: %(message)s',
            '%(log_color)s[%(asctime)s] [%(threadName)s] : %(message)s',
            log_colors={
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
                'SERIOUS': 'red,bg_white',
            }
        )
        formatter = SystemLogFormatter('[%(asctime)s] [%(threadName)s] : %(message)s')

        self.log = logging.getLogger(name)
        for handler in self.log.handlers[:]:
            self.log.removeHandler(handler)
            handler.close()
        self.log.setLevel(logging.DEBUG)
        # self.log.setLevel(logging.ERROR)  ## add ?
        # self.log.setLevel(settings.LOG_LEVEL)

        if file:
            # log_file = '{}/log/{}'.format(os.getcwd(), file)
            log_file = os.path.join(os.getcwd(), 'log', file)

            timed_file_handler = DailyPatternTimedRotatingFileHandler(log_file, when='midnight', backupCount=settings.log_ipc_preserve)
            timed_file_handler.setFormatter(formatter)
            timed_file_handler.setLevel(logging.DEBUG)
            self.log.addHandler(timed_file_handler)

        # stream_handler = StreamHandler()
        # stream_handler.setFormatter(colored_formatter)
        # stream_handler.setLevel(logging.INFO)
        # self.log.addHandler(stream_handler)

        self.log.info(f'###### {name} logger started ######')
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

    def error(self, message, args = None, exc_info = False):
        if args is not None:
            self.log.error(message, args, exc_info=exc_info)
        else:
            self.log.error(message, exc_info=exc_info)

    def critical(self, message, args = None, exc_info = False):
        if args is not None:
            self.log.critical(message, args, exc_info=exc_info)
        else:
            self.log.critical(message, exc_info=exc_info)


# Registry of live AsyncLoggerFile instances by logger name. A single atexit
# hook stops them all, so re-creating a logger never leaks atexit callbacks.
_async_logger_instances = {}


def _stop_all_async_loggers():
    for instance in list(_async_logger_instances.values()):
        instance.stop()
    _async_logger_instances.clear()


atexit.register(_stop_all_async_loggers)


class AsyncLoggerFile:
    def __init__(self, name, file=None, backup_count=None) -> None:
        self.name = name
        self.log = logging.getLogger(name)
        self.log.setLevel(logging.DEBUG)
        self.log.propagate = False

        existing = _async_logger_instances.get(name)
        if existing is not None:
            existing.stop()

        for handler in self.log.handlers[:]:
            self.log.removeHandler(handler)
            handler.close()

        self._listener = None
        self._file_handler = None

        if file:
            log_file = os.path.join(os.getcwd(), 'log', file)
            self._file_handler = DailyPatternTimedRotatingFileHandler(
                log_file,
                when='midnight',
                backupCount=backup_count if backup_count is not None else settings.log_ipc_preserve,
            )
            self._file_handler.setFormatter(UTCFormatter('[%(asctime)s] [%(levelname)s] [%(threadName)s]: %(message)s'))
            self._file_handler.setLevel(logging.DEBUG)

            log_queue = queue.SimpleQueue()
            queue_handler = QueueHandler(log_queue)
            queue_handler.setLevel(logging.DEBUG)
            self.log.addHandler(queue_handler)

            self._listener = QueueListener(log_queue, self._file_handler, respect_handler_level=True)
            self._listener.start()
            _async_logger_instances[name] = self

        self.log.info(f"###### {name} logger started ######")

    def stop(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

        if self._file_handler is not None:
            self._file_handler.close()
            self._file_handler = None

        if _async_logger_instances.get(self.name) is self:
            del _async_logger_instances[self.name]

    def debug(self, message, args=None):
        if args is not None:
            self.log.debug(message, extra=args)
        else:
            self.log.debug(message)

    def info(self, message, args=None):
        if args is not None:
            self.log.info(message, extra=args)
        else:
            self.log.info(message)

    def warning(self, message, args=None):
        if args is not None:
            self.log.warning(message, extra=args)
        else:
            self.log.warning(message)

    def error(self, message, args=None, exc_info=False):
        if isinstance(args, dict):
            self.log.error(message, extra=args, exc_info=exc_info)
        elif args is not None:
            self.log.error(message, args, exc_info=exc_info)
        else:
            self.log.error(message, exc_info=exc_info)

    def critical(self, message, args=None, exc_info=False):
        if isinstance(args, dict):
            self.log.critical(message, extra=args, exc_info=exc_info)
        elif args is not None:
            self.log.critical(message, args, exc_info=exc_info)
        else:
            self.log.critical(message, exc_info=exc_info)

glogger = None
