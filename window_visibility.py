"""Show the Tk HUD without activating it or changing the game's focus."""
import ctypes
from ctypes import wintypes
from contextlib import contextmanager


@contextmanager
def prevent_window_activation():
    """Veto activation and focus requests on this HUD GUI thread only."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                      wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type,
                                       wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HANDLE
    user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                     wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    @callback_type
    def callback(code, wp, lp):
        if code in (5, 9):  # HCBT_ACTIVATE, HCBT_SETFOCUS: prevent the operation.
            return 1
        return user32.CallNextHookEx(None, code, wp, lp)

    # WH_CBT is thread-local: no injection, other application hooks, or input
    # interception. Install before Tk creates its initial native wrapper.
    hook = user32.SetWindowsHookExW(5, callback, None, kernel32.GetCurrentThreadId())
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        user32.UnhookWindowsHookEx(hook)


class HudWindowVisibility:
    def __init__(self, root):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetParent.argtypes = [wintypes.HWND]
        self.user32.GetParent.restype = wintypes.HWND
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                             ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                             ctypes.c_int, wintypes.UINT]
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.client = root.winfo_id()
        self.window = self.user32.GetParent(self.client) or self.client

    def set_visible(self, visible):
        if not visible:
            self.user32.ShowWindow(self.window, 0)  # SW_HIDE
            return
        # Tk's deiconify/restack path can activate the wrapper even when it has
        # WS_EX_NOACTIVATE. Map the client and wrapper directly instead.
        self.user32.ShowWindow(self.client, 4)  # SW_SHOWNOACTIVATE
        if not self.user32.SetWindowPos(self.window, wintypes.HWND(-1), 0, 0, 0, 0,
                                        0x0001 | 0x0002 | 0x0010 | 0x0040):
            raise ctypes.WinError(ctypes.get_last_error())

    def keep_above_game(self):
        """Recover z-order after a game's display-mode or topmost transition."""
        if not self.user32.SetWindowPos(self.window, wintypes.HWND(-1), 0, 0, 0, 0,
                                        0x0001 | 0x0002 | 0x0010):
            # TOPMOST, NOSIZE, NOMOVE, NOACTIVATE. Do not map a hidden window.
            raise ctypes.WinError(ctypes.get_last_error())
