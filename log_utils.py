from datetime import datetime
import logging
import os
import re
from pathlib import Path


LOG_DATE_FORMAT = "%Y-%m-%d"


def get_dated_log_filename(filename, current_datetime=None):
    current_datetime = current_datetime or datetime.now()
    file_path = Path(filename)
    date_text = current_datetime.strftime(LOG_DATE_FORMAT)

    if file_path.suffix:
        return f"{file_path.stem}_{date_text}{file_path.suffix}"

    return f"{file_path.name}_{date_text}"


def get_dated_log_path(path, current_datetime=None):
    file_path = Path(path)
    return str(file_path.with_name(get_dated_log_filename(file_path.name, current_datetime)))


class DailyDatedFileHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding=None, delay=False, backupCount=0):
        self._logical_path = Path(filename)
        self.logicalFilename = os.path.abspath(str(self._logical_path))
        self.backupCount = backupCount
        self._current_date = None

        current_datetime = self._resolve_current_datetime()
        dated_path = self._build_path(current_datetime)
        os.makedirs(dated_path.parent, exist_ok=True)

        super().__init__(str(dated_path), mode=mode, encoding=encoding, delay=delay)

        self._current_date = current_datetime.date()
        self._delete_expired_files()

    def _resolve_current_datetime(self):
        return datetime.now()

    def _build_path(self, current_datetime):
        return self._logical_path.with_name(
            get_dated_log_filename(self._logical_path.name, current_datetime)
        )

    def _reopen_if_needed(self):
        current_datetime = self._resolve_current_datetime()
        if self._current_date == current_datetime.date():
            return

        self._current_date = current_datetime.date()

        if self.stream:
            self.stream.close()
            self.stream = None

        dated_path = self._build_path(current_datetime)
        os.makedirs(dated_path.parent, exist_ok=True)
        self.baseFilename = os.path.abspath(str(dated_path))

        if not self.delay:
            self.stream = self._open()

        self._delete_expired_files()

    def _delete_expired_files(self):
        if self.backupCount <= 0:
            return

        stem = self._logical_path.stem
        suffix = self._logical_path.suffix
        pattern = re.compile(rf"^{re.escape(stem)}_\d{{4}}-\d{{2}}-\d{{2}}{re.escape(suffix)}$")

        log_files = sorted(
            file_path
            for file_path in self._logical_path.parent.glob(f"{stem}_*{suffix}")
            if pattern.match(file_path.name)
        )

        keep_count = self.backupCount + 1
        for expired_file in log_files[:-keep_count]:
            expired_file.unlink(missing_ok=True)

    def emit(self, record):
        self._reopen_if_needed()
        super().emit(record)
