"""Recognize foreground games from read-only AMD profiles and user additions."""
import ctypes
from ctypes import wintypes
import json
import ntpath
import os
from pathlib import Path
import time


def normalize_path(value):
    return ntpath.normcase(ntpath.normpath(os.path.expandvars(value.strip().strip('"'))))


def profile_games(data, excluded):
    games = {}
    for entry in data.get("games", []):
        if not isinstance(entry, dict):
            continue
        if any(str(entry.get(flag, "FALSE")).upper() == "TRUE"
               for flag in ("uninstalled", "exe_is_launcher", "is_appforlink", "is_ai_app")):
            continue
        path = entry.get("exe_path", "")
        if not isinstance(path, str) or not path or not ntpath.isabs(path):
            continue
        path = normalize_path(path)
        if ntpath.basename(path) not in excluded:
            games[path] = entry.get("title") or ntpath.basename(path)
    return games


class GameDetector:
    def __init__(self, config):
        self.config = config
        self.games = {}
        self.last_reload = float("-inf")
        self.profile_error = None
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                          wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.reload()

    def reload(self):
        now = time.monotonic()
        if now - self.last_reload < 5:
            return
        self.last_reload = now
        excluded = {name.casefold() for name in self.config["excluded_executables"]}
        games = {}
        self.profile_error = None
        profile = self.config.get("amd_profiles_path") or os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "AMD", "CN", "gmdb.blb")
        try:
            data = json.loads(Path(os.path.expandvars(profile)).read_text(encoding="utf-8-sig"))
            games.update(profile_games(data, excluded))
        except (OSError, ValueError, AttributeError) as exc:
            # Missing or temporarily rewritten profiles must never show the HUD on the desktop.
            self.profile_error = str(exc)
        for path in self.config["game_executables"]:
            path = normalize_path(path)
            if ntpath.basename(path) not in excluded:
                games[path] = ntpath.basename(path)
        self.games = games

    def foreground(self):
        window = self.user32.GetForegroundWindow()
        if not window:
            return None, None
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        process = self.kernel32.OpenProcess(0x1000, False, pid.value)
        if not process:
            return None, None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not self.kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                return None, None
            return normalize_path(buffer.value), pid.value
        finally:
            self.kernel32.CloseHandle(process)

    def foreground_path(self):
        return self.foreground()[0]

    def current_target(self):
        self.reload()
        path, pid = self.foreground()
        if path in self.games:
            return {"name": self.games[path], "path": path, "pid": pid}
        return None

    def current_game(self):
        self.reload()
        return self.games.get(self.foreground_path())

    def diagnostic(self):
        self.reload()
        path = self.foreground_path()
        return {"foreground_executable": path, "foreground_game": self.games.get(path),
                "recognized_games": self.games, "profile_error": self.profile_error}
