# Placing conftest.py at the repo root makes pytest insert the root directory
# into sys.path (default importmode=prepend), so the test suite can import the
# project's flat-layout modules (config, device_io, mqtt_svc2) directly.

import pytest

import device_io
import device_io_linux


@pytest.fixture(params=[device_io, device_io_linux], ids=["device_io", "device_io_linux"])
def ledbutton_cls(request):
    """The LEDButton class from both the Windows module (device_io) and the
    Linux deployment copy (device_io_linux), so every test using this fixture
    runs its behavior assertions against both modules and the copy cannot
    silently drift."""
    return request.param.LEDButton

