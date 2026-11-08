"""Local control events shared by the HUD and its settings window."""
import ctypes
from ctypes import wintypes
from single_instance import SingleInstance


class HudControl:
    def __init__(self, directory):
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self.k.CreateEventW.restype = wintypes.HANDLE
        self.k.SetEvent.argtypes = [wintypes.HANDLE]
        self.k.ResetEvent.argtypes = [wintypes.HANDLE]
        self.k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.k.WaitForSingleObject.restype = wintypes.DWORD
        self.k.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        self.k.OpenMutexW.restype = wintypes.HANDLE
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.name = SingleInstance(directory).name
        self.events = {}
        try:
            for action in ("stop", "reload", "preview"):
                handle = self.k.CreateEventW(None, False, False, self.name + "-" + action)
                if not handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                self.events[action] = handle
        except Exception:
            self.close()
            raise

    def running(self):
        handle = self.k.OpenMutexW(0x100000, False, self.name)
        if handle:
            self.k.CloseHandle(handle)
        return bool(handle)

    def send(self, action):
        return bool(self.k.SetEvent(self.events[action]))

    def poll(self, action):
        return self.k.WaitForSingleObject(self.events[action], 0) == 0

    def reset(self):
        for handle in self.events.values():
            self.k.ResetEvent(handle)

    def close(self):
        for handle in self.events.values():
            self.k.CloseHandle(handle)
        self.events.clear()
