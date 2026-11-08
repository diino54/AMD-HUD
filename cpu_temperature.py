"""Reuse the installed AMD CPU Metrics Server; no extra driver or SDK required.

Private IPC layout verified against CPUMetricsServer 10,01,02,2068. Unknown
server builds are deliberately rejected rather than interpreting unknown data.
"""
import ctypes
from ctypes import wintypes
import hashlib
import math
import os
from pathlib import Path
import struct
import threading
import time

SERVER_HASH = "a7cfaded5ce503842a931c26126b16ec78fddd67a62e07f53671d2f7d5f85755"
MAPPING_NAME = "954b280e-5529-4492-bab2-bb7a502552f8"
PACKET_SIZE = 0x1F8


def decode_temperature(packet, previous_counter):
    if len(packet) != PACKET_SIZE:
        return None
    counter = struct.unpack_from("<I", packet, 0x1C0)[0]
    supported = struct.unpack_from("<H", packet, 0x78)[0]
    maximum = struct.unpack_from("<d", packet, 0x68)[0]
    temperature = struct.unpack_from("<d", packet, 0x1D8)[0]
    if counter == previous_counter or supported != 1 or maximum != 120.0:
        return None
    return temperature if math.isfinite(temperature) and 0 < temperature <= maximum else None


class CpuTemperature:
    def __init__(self):
        self.value = None
        self.updated = 0
        self.status = "not requested"
        self.request = threading.Event()
        self.stop_event = threading.Event()
        self.completed = threading.Event()
        self.thread = None
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "OpenFileMappingW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            "MapViewOfFile": ([wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t], ctypes.c_void_p),
            "OpenEventW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            "OpenMutexW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            "ReleaseMutex": ([wintypes.HANDLE], wintypes.BOOL),
            "SetEvent": ([wintypes.HANDLE], wintypes.BOOL),
            "UnmapViewOfFile": ([ctypes.c_void_p], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            method = getattr(self.k, name)
            method.argtypes, method.restype = args, result
        server = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "AMD/CNext/CNext/CPUMetricsServer.exe"
        try:
            self.compatible = hashlib.sha256(server.read_bytes()).hexdigest() == SERVER_HASH
            if not self.compatible:
                self.status = "unrecognized AMD CPU Metrics Server build"
        except OSError:
            self.compatible = False
            self.status = "AMD CPU Metrics Server not installed"

    def read(self, wait=0):
        if not self.compatible:
            return None
        if self.thread is None:
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
        self.completed.clear()
        self.request.set()
        if wait:
            self.completed.wait(wait)
        return self.value if time.monotonic() - self.updated <= 2.5 else None

    def _worker(self):
        last_attempt = float("-inf")
        while not self.stop_event.is_set():
            if not self.request.wait(0.2):
                continue
            self.request.clear()
            # AMD recommends at most one CPU parameter sample per second.
            if self.stop_event.wait(max(0, 1.0 - (time.monotonic() - last_attempt))):
                break
            last_attempt = time.monotonic()
            try:
                self.value = self._sample()
                self.updated = time.monotonic()
                self.status = "ok" if self.value is not None else "no fresh valid temperature"
            except (OSError, RuntimeError) as exc:
                self.value = None
                self.status = str(exc)
            finally:
                self.completed.set()

    def _sample(self):
        k = self.k
        handles = []
        view = None
        try:
            mapping = k.OpenFileMappingW(6, False, MAPPING_NAME)
            if not mapping:
                raise RuntimeError("AMD CPU Metrics Server is not running or its buffer is inaccessible")
            handles.append(mapping)
            view = k.MapViewOfFile(mapping, 6, 0, 0, PACKET_SIZE)
            if not view:
                raise ctypes.WinError(ctypes.get_last_error())
            event = k.OpenEventW(2, False, MAPPING_NAME + "_event")
            mutex = k.OpenMutexW(0x100001, False, MAPPING_NAME + "_mutex")
            handles.extend(handle for handle in (event, mutex) if handle)
            if not event or not mutex:
                raise RuntimeError("AMD CPU Metrics synchronization objects unavailable")
            if k.WaitForSingleObject(mutex, 200) not in (0, 0x80):
                return None
            try:
                original = ctypes.c_ubyte.from_address(view).value
                before = ctypes.c_uint32.from_address(view + 0x1C0).value
                if original not in (0, 1):
                    return None
                # This byte enables telemetry only. No tuning/control fields or
                # window messages are touched. Restore it after the single read.
                ctypes.c_ubyte.from_address(view).value = 1
                requested = k.SetEvent(event)
            finally:
                k.ReleaseMutex(mutex)
            try:
                if not requested:
                    raise ctypes.WinError(ctypes.get_last_error())
                deadline = time.monotonic() + 0.8
                while not self.stop_event.is_set() and time.monotonic() < deadline:
                    if k.WaitForSingleObject(mutex, 50) in (0, 0x80):
                        try:
                            packet = ctypes.string_at(view, PACKET_SIZE)
                        finally:
                            k.ReleaseMutex(mutex)
                        if struct.unpack_from("<I", packet, 0x1C0)[0] != before:
                            return decode_temperature(packet, before)
                    self.stop_event.wait(0.02)
                return None
            finally:
                if k.WaitForSingleObject(mutex, 2000) in (0, 0x80):
                    try:
                        ctypes.c_ubyte.from_address(view).value = original
                    finally:
                        k.ReleaseMutex(mutex)
                else:
                    raise RuntimeError("AMD CPU Metrics Server did not release its sampling mutex")
        finally:
            if view:
                k.UnmapViewOfFile(view)
            for handle in reversed(handles):
                k.CloseHandle(handle)

    def close(self):
        self.stop_event.set()
        self.request.set()
        if self.thread:
            self.thread.join(timeout=4)
