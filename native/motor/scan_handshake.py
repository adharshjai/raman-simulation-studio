"""Port of RamanAutofocus/RamanAutofocus/scan_handshake.h and line_scan_plan.h.

Same semantics and timings as the Windows headers: one outstanding point per session,
files are published atomically (temporary file + rename), the ACK is polled every 20 ms
and a PAUSED/HOLD reply with a changing heartbeat keeps the 30 s contact timeout alive.
"""

from __future__ import annotations

import os
import time
from typing import List

ACK_POLL_SECONDS = 0.020          # scan_handshake.h:45  sleep_for(20ms)
DEFAULT_ACK_TIMEOUT_MS = 30000    # scan_handshake.h:25  timeoutMs = 30000


def publish(path: str, text) -> bool:
    """scan_handshake.h:11-20 - write `<path>.tmp`, then rename over `path` (up to 20
    attempts, 10 ms apart). rename(2) replaces atomically on POSIX."""
    data = text if isinstance(text, bytes) else str(text).encode("utf-8")
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as out:
            out.write(data)
            out.flush()
    except OSError:
        return False
    for _attempt in range(20):
        try:
            os.replace(tmp, path)
            return True
        except OSError:
            time.sleep(0.010)
    return False


# ---- safety stop (addition, no counterpart in scan_handshake.h) ------------------------------
# The scan is also cancelled when the controller that started this program is gone (crash, force
# quit, Qt Creator's Stop button: the parent process id changes when it dies) or when the program
# is asked to terminate (request_stop, called from the signal handlers in raman_autofocus.py).
# Every wait loop already checks cancelled(), so the existing cancel path does the work: the move
# in progress is stopped immediately, nothing further is commanded, the controllers are closed.
# Windows does not re-parent orphans: there the controller is the process named by
# RAMAN_CONTROLLER_PID (the controller always sets it), watched through a handle opened at start,
# which says when that process has ended even after its pid has been reused.
_WINDOWS = os.name == "nt"


def _recorded_controller_pid() -> int:
    try:
        recorded = int(os.environ.get("RAMAN_CONTROLLER_PID", "") or 0)
    except ValueError:
        recorded = 0
    return recorded if recorded > 1 else 0


def _controller_pid() -> int:
    """The process to watch. A live parent is the controller (the launcher execs, so our parent is
    whoever started it). Only when this process is already orphaned does the pid handed down in
    RAMAN_CONTROLLER_PID count: that process is gone, and controller_gone() says so at once.
    On Windows it is the pid of RAMAN_CONTROLLER_PID, else the parent's."""
    if _WINDOWS:
        return _recorded_controller_pid() or os.getppid()
    parent = os.getppid()
    if parent > 1:
        return parent
    return _recorded_controller_pid() or parent


class _WindowsProcessWatch:
    """A SYNCHRONIZE handle to the controller, opened once (Windows only)."""

    _SYNCHRONIZE = 0x00100000
    _QUERY_LIMITED = 0x1000

    def __init__(self, pid: int):
        import ctypes
        from ctypes import wintypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self._kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self._kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        self._kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        self._kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        self.gone_at_start = False
        self._handle = self._kernel32.OpenProcess(self._SYNCHRONIZE | self._QUERY_LIMITED, False, pid) if pid > 1 else None
        if pid > 1 and not self._handle:
            self.gone_at_start = True
        elif self._handle and self._created(self._handle) > self._created(self._kernel32.GetCurrentProcess()):
            self.gone_at_start = True   # a process started after this one: the pid was reused

    def _created(self, handle) -> int:
        import ctypes
        from ctypes import wintypes
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self._kernel32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            return 0
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime

    def gone(self) -> bool:
        if self.gone_at_start:
            return True
        return bool(self._handle) and self._kernel32.WaitForSingleObject(self._handle, 0) == 0


_ORIGINAL_PARENT = _controller_pid()
try:
    _CONTROLLER_WATCH = _WindowsProcessWatch(_ORIGINAL_PARENT) if _WINDOWS else None
except (OSError, AttributeError):
    _CONTROLLER_WATCH = None
_stop_reason = ""


def request_stop(reason: str) -> None:
    """Ask for the scan to be cancelled; the first reason is kept."""
    global _stop_reason
    if not _stop_reason:
        _stop_reason = str(reason) or "stop requested"


def stop_reason() -> str:
    """Why the safety stop cancelled the scan, or "" when it did not."""
    return _stop_reason


def reset_stop() -> None:
    """Forget a previous stop request (tests run the program several times in one process)."""
    global _stop_reason
    _stop_reason = ""


def controller_gone() -> bool:
    """True when this process has been re-parented, i.e. the process that started it died. A
    parent id of 1 at start means there was no controller to watch. On Windows: true when the
    controller's process has ended."""
    if _WINDOWS:
        return _CONTROLLER_WATCH is not None and _CONTROLLER_WATCH.gone()
    return _ORIGINAL_PARENT > 1 and os.getppid() != _ORIGINAL_PARENT


def safety_stop_pending() -> bool:
    """True when a stop was requested or the controller is gone (cancel.txt is not looked at)."""
    if _stop_reason:
        return True
    if controller_gone():
        request_stop("the controller process %d is gone" % _ORIGINAL_PARENT)
        return True
    return False


def cancelled(directory: str) -> bool:
    """scan_handshake.h:21-23 - the controller publishes `cancel.txt` to stop the scan. Addition: a requested stop or a vanished controller cancels the scan as well."""
    if os.path.exists(os.path.join(directory, "cancel.txt")):
        return True
    return safety_stop_pending()


def _read_first_line(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.readline()
    except OSError:
        return ""


def wait_for_ack(directory: str, run: str, point: int, timeout_ms: int = DEFAULT_ACK_TIMEOUT_MS) -> bool:
    """scan_handshake.h:24-48 - poll response.txt for `ACK <run> <point> <state> <heartbeat>`."""
    last_contact = time.monotonic()
    previous_heartbeat = ""
    while not cancelled(directory):
        tokens = _read_first_line(os.path.join(directory, "response.txt")).split()
        # `row >> tag >> actualRun >> actualPoint >> state >> heartbeat` needs five fields and a
        # numeric point id; otherwise the line is ignored.
        if len(tokens) >= 5 and tokens[2].isdigit():
            tag, actual_run, actual_point, state, heartbeat = tokens[0], tokens[1], int(tokens[2]), tokens[3], tokens[4]
            if tag == "ACK" and actual_run == run and actual_point == point:
                if state == "OK":
                    return True
                if state == "FAIL":
                    return False
                if state in ("PAUSED", "HOLD") and heartbeat != previous_heartbeat:
                    previous_heartbeat = heartbeat
                    last_contact = time.monotonic()
        if (time.monotonic() - last_contact) * 1000.0 >= timeout_ms:
            return False
        time.sleep(ACK_POLL_SECONDS)
    return False


# ---- line_scan_plan.h -------------------------------------------------------------------
def line_scan_positions(steps_per_mm: int = 34700) -> List[int]:
    """line_scan_plan.h:4-8 - absolute device coordinates after homing, 0..24 mm every 2 mm;
    both endpoints are acquired."""
    return [mm * steps_per_mm for mm in range(0, 25, 2)]


def line_scan_within_limits(points: List[int], minimum: int, maximum: int) -> bool:
    """line_scan_plan.h:9-13"""
    if not points or minimum >= maximum:
        return False
    for point in points:
        if point < minimum or point > maximum:
            return False
    return True
