"""Whole-file locks between processes, on macOS, Linux and Windows.

flock(2) where it exists; on Windows a lock on the first byte of the file (msvcrt.locking), which
behaves the same way here: the holder is one open file, a second open of the same file waits (or
is refused at once), and the lock goes away with the file or with the process that held it.
"""

from __future__ import annotations

import os
import time

if os.name == "nt":
    import msvcrt

    _RETRY_SECONDS = 0.05

    def lock(handle, blocking: bool = True) -> bool:
        """Lock the open file `handle`. Returns False, at once, when another holder has it and
        `blocking` is false; otherwise waits for it."""
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                if not blocking:
                    return False
                time.sleep(_RETRY_SECONDS)

    def unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def lock(handle, blocking: bool = True) -> bool:
        """Lock the open file `handle`. Returns False, at once, when another holder has it and
        `blocking` is false; otherwise waits for it."""
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            return False
        return True

    def unlock(handle) -> None:
        fcntl.flock(handle, fcntl.LOCK_UN)
