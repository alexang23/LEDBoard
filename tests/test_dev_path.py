"""Tests for Controller._dev_path, the COM-number to serial-device-path
mapping shared by both LED boards.

The mapping mirrors SmartIO-E84-Japan's _e84_dev_path so the same COM
number means the same Linux device in both projects:

  win32                 -> COM{com}
  linux, COM_TYPE == 1  -> /dev/ttyUSB{com-1}   (USB serial adapter)
  linux, COM_TYPE == 0  -> /dev/ttyS{com-1}    (RS-232 COM port)

Config defaults are asserted too: they must be 0 (COM port) so existing
deployments keep today's behavior until a site opts into USB explicitly.
"""

import pytest

from config import settings
from controller import Controller


# _dev_path branches on sys.platform, so tests monkeypatch it instead of
# depending on the platform the suite happens to run on.

@pytest.mark.parametrize("com,com_type,expected", [
    (5, 0, "COM5"),
    (10, 1, "COM10"),
])
def test_dev_path_windows_is_always_com_n(monkeypatch, com, com_type, expected):
    monkeypatch.setattr("sys.platform", "win32")
    assert Controller._dev_path(com, com_type) == expected


@pytest.mark.parametrize("com,com_type,expected", [
    (5, 1, "/dev/ttyUSB4"),
    (10, 1, "/dev/ttyUSB9"),
])
def test_dev_path_linux_usb_is_zero_based(monkeypatch, com, com_type, expected):
    monkeypatch.setattr("sys.platform", "linux")
    assert Controller._dev_path(com, com_type) == expected


@pytest.mark.parametrize("com,com_type,expected", [
    (5, 0, "/dev/ttyS4"),
    (10, 0, "/dev/ttyS9"),
])
def test_dev_path_linux_serial_is_zero_based(monkeypatch, com, com_type, expected):
    monkeypatch.setattr("sys.platform", "linux")
    assert Controller._dev_path(com, com_type) == expected


def test_com_type_defaults_to_com_port():
    assert settings.LEDBOARD_COM_TYPE == 0
    assert settings.LEDBOARD2_COM_TYPE == 0
