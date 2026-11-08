"""Keep exactly one HUD running per project directory and Windows session."""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path


class SingleInstance:
    def __init__(self, directory):
        identity = os.path.normcase(str(Path(directory).resolve()))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        self.name = "Local\\AMDHUD-" + digest
        self.handle = None
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel32.CreateMutexW.restype = wintypes.HANDLE
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def acquire(self):
        if self.handle is not None:
            return True
        ctypes.set_last_error(0)
        handle = self.kernel32.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        if error == 183:  # ERROR_ALREADY_EXISTS
            self.kernel32.CloseHandle(handle)
            return False
        self.handle = handle
        return True

    def close(self):
        if self.handle is not None:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None
