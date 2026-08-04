from __future__ import annotations

import ctypes
import os
import sys
from typing import Any

from stories_yggdrasil_osc.app_v0814 import run

_MUTEX_NAME = r"Local\StoriesOfYggdrasilOSCDesktop"
_ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance() -> Any | None:
    """Prevent duplicate Desktop OSC processes from binding the same UDP port.

    The Windows application previously allowed a second launch, which created a
    second Sam.py poller and then failed to bind the local OSC port with WinError
    10048. A named mutex is process-wide, requires no extra dependency, and is
    released automatically if the process crashes.
    """
    if os.name != "nt":
        return object()

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_bool

    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Stories Of Yggdrasil OSC is already running.",
                "Stories Of Yggdrasil OSC",
                0x40,
            )
        except Exception:
            pass
        return None

    return (kernel32, handle)


def _release_single_instance(instance: Any | None) -> None:
    if os.name != "nt" or not instance:
        return
    try:
        kernel32, handle = instance
        kernel32.CloseHandle(handle)
    except Exception:
        pass


def main() -> int:
    instance = _acquire_single_instance()
    if instance is None:
        return 0
    try:
        run()
        return 0
    finally:
        _release_single_instance(instance)


if __name__ == "__main__":
    sys.exit(main())
