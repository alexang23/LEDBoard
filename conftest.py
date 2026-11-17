# Placing conftest.py at the repo root makes pytest insert the root directory
# into sys.path (default importmode=prepend), so the test suite can import the
# project's flat-layout modules (config, device_io, mqtt_svc2) directly.
