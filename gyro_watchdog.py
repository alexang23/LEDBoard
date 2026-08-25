"""
Lightweight, cross-platform (Windows + Linux) liveness watchdog.

Long-running worker threads (E84 port threads, SerialPortHandler readers,
MQTTSvc, WebServiceSvc, ...) call `touch(name)` once per loop iteration.
A single background thread here periodically checks whether any registered
name has gone quiet for longer than expected, and if so logs a CRITICAL
message plus a full stack dump of every live thread.

This is deliberately signal-free: SIGUSR1-based stack dumping is the usual
trick on Linux, but this project also ships a Windows build (e84_event.py
vs. e84_event_linux.py), so a plain polling thread using
sys._current_frames() is used instead, which works identically on both
platforms.

A stalled/deadlocked thread stops touching in, which is exactly what this
catches: the watchdog does not depend on the stuck thread doing anything.

Note: the module is named gyro_watchdog (not watchdog) to avoid colliding
with the widely installed PyPI `watchdog` file-watcher package.
"""

import sys
import time
import threading
import traceback

_last_seen = {}
_max_gap = {}
_lock = threading.Lock()
_watchdog_started = False
_watchdog_lock = threading.Lock()

_DEFAULT_MAX_GAP = 15

# Hard cap on how long a stack dump may take. sys._current_frames() can block
# on a thread that holds the GIL in a native call; a dump that wedges forever
# must never take down the watchdog thread itself.
_DUMP_TIMEOUT_SECONDS = 5


def touch(name, max_gap=None):
    """Call once per loop iteration from any thread you want monitored.

    max_gap: seconds this name is allowed to go quiet for before it's
    considered stalled. Only needs to be passed once per name (e.g. on the
    first touch()) - later calls can omit it and the registered value is
    kept. Defaults to the watchdog's global stale_after if never set.
    """
    with _lock:
        _last_seen[name] = time.monotonic()
        if max_gap is not None:
            _max_gap[name] = max_gap


def unregister(name):
    """Call when a monitored thread/loop is shutting down intentionally,
    so it doesn't get flagged as stalled after it has legitimately stopped."""
    with _lock:
        _last_seen.pop(name, None)
        _max_gap.pop(name, None)


def _collect_stack_dump():
    lines = []
    names_by_ident = {t.ident: t.name for t in threading.enumerate()}
    for ident, frame in sys._current_frames().items():
        thread_name = names_by_ident.get(ident, f"unnamed-{ident}")
        lines.append(f"--- thread '{thread_name}' (ident={ident}) ---")
        try:
            lines.extend(traceback.format_stack(frame))
        except Exception:
            lines.append("(stack unavailable)")
    return "".join(lines)


def _dump_all_stacks():
    # Best-effort, time-bounded: run the dump on a separate daemon thread and
    # only wait _DUMP_TIMEOUT_SECONDS for it. A wedged frame (GIL held in a C
    # call) or a thread torn down mid-exit must never stall the monitor.
    results = []

    def _worker():
        try:
            results.append(_collect_stack_dump())
        except Exception as exc:
            results.append(f"(stack dump failed: {exc})")

    worker = threading.Thread(target=_worker, daemon=True, name="WatchdogDump")
    worker.start()
    worker.join(timeout=_DUMP_TIMEOUT_SECONDS)
    if worker.is_alive():
        return "(stack dump timed out after {}s - a thread is wedged holding the GIL?)".format(
            _DUMP_TIMEOUT_SECONDS
        )
    return results[0] if results else "(stack dump unavailable)"


def _log_critical(logger, message):
    # The watchdog runs unsupervised; never crash the monitor just because a
    # particular logger object lacks a critical() method.
    log_method = getattr(logger, "critical", None) or getattr(logger, "error", None)
    if log_method is None:
        return
    try:
        log_method(message)
    except Exception:
        pass


def start_watchdog(logger, stale_after=_DEFAULT_MAX_GAP, check_every=5):
    """Start the background watchdog thread (idempotent - safe to call more
    than once; only the first call actually starts it).

    stale_after: seconds without a touch() before a name is considered stalled
    check_every: how often to check
    """
    global _watchdog_started
    with _watchdog_lock:
        if _watchdog_started:
            return
        _watchdog_started = True

    def _run():
        already_flagged = set()
        while True:
            time.sleep(check_every)
            now = time.monotonic()
            with _lock:
                snapshot = dict(_last_seen)
                gaps = dict(_max_gap)

            stale = {
                n: now - t
                for n, t in snapshot.items()
                if now - t > gaps.get(n, stale_after)
            }

            if stale:
                newly_stale = {
                    n: age for n, age in stale.items() if n not in already_flagged
                }
                if newly_stale:
                    _log_critical(
                        logger,
                        "watchdog : stalled (no heartbeat): "
                        + ", ".join(f"{n} ({age:.0f}s)" for n, age in newly_stale.items()),
                    )
                    _log_critical(logger, "watchdog : full stack dump follows:")
                    _log_critical(logger, _dump_all_stacks())
                already_flagged = set(stale.keys())
            else:
                already_flagged = set()

    threading.Thread(target=_run, daemon=True, name="Watchdog").start()