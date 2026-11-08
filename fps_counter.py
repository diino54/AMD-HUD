"""Read process-specific rendered FPS from PresentMon's ETW stream."""
from collections import deque
import csv
import os
from pathlib import Path
import subprocess
import threading
import time
import math
import ctypes


class FpsCounter:
    def __init__(self):
        self.executable = Path(__file__).resolve().parent / "vendor/PresentMon/PresentMon-2.6.0-x64.exe"
        self.session = "AMDHUD-" + str(os.getpid())
        self.process = None
        self.reader = None
        self.pid = None
        self.samples = deque(maxlen=32768)
        self.lock = threading.Lock()
        self.retry_at = 0
        self.runtime = None
        self.active_chain = None
        self.pending_chain = None
        self.pending_since = 0
        self.chain_started_at = float("-inf")
        frequency = ctypes.c_longlong()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_longlong)]
        kernel32.QueryPerformanceFrequency.restype = ctypes.c_int
        if not kernel32.QueryPerformanceFrequency(ctypes.byref(frequency)) or frequency.value <= 0:
            raise ctypes.WinError(ctypes.get_last_error())
        self.qpc_frequency = frequency.value

    def target(self, pid):
        if pid == self.pid and (pid is None or self.process.poll() is None):
            return
        if pid is not None and pid == self.pid and time.perf_counter() < self.retry_at:
            return
        self.stop()
        if pid is None:
            return
        args = [str(self.executable), "--process_id", str(pid), "--output_stdout",
                "--no_console_stats", "--v1_metrics", "--qpc_time", "--no_track_gpu", "--no_track_input",
                "--session_name", self.session, "--stop_existing_session"]
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, encoding="utf-8-sig", errors="replace",
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        self.pid = pid
        self.retry_at = time.perf_counter() + 5
        self.reader = threading.Thread(target=self._read, args=(self.process,), daemon=True)
        self.reader.start()

    def _read(self, process):
        with process.stdout:
            for row in csv.DictReader(process.stdout):
                try:
                    interval = float(row["msBetweenPresents"])
                    chain = row["SwapChainAddress"]
                    timestamp = int(row["QPCTime"]) / self.qpc_frequency
                    if math.isfinite(interval) and interval > 0 and int(row["ProcessID"]) == self.pid:
                        with self.lock:
                            self.samples.append((timestamp, chain, interval))
                            self.runtime = row.get("Runtime")
                except (KeyError, ValueError, TypeError):
                    continue

    def api_label(self):
        # DXGI covers several DirectX versions; do not claim DirectX 12.
        return {"DXGI": "DirectX", "D3D9": "DirectX 9"}.get(self.runtime, self.runtime or "FPS")

    def value(self):
        now = time.perf_counter()
        groups = {}
        with self.lock:
            for timestamp, chain, interval in self.samples:
                if 0 <= now - timestamp <= 1.5:
                    groups.setdefault(chain, []).append(interval)
        if not groups:
            return None
        # Multiple swap chains must not multiply the reported FPS.
        intervals = max(groups.values(), key=len)
        return 1000 * len(intervals) / sum(intervals)

    def frametime_samples(self, window_seconds=10.0):
        now = time.perf_counter()
        with self.lock:
            samples = list(self.samples)
        recent_counts = {}
        for timestamp, chain, _ in samples:
            if 0 <= now - timestamp <= 1.5:
                recent_counts[chain] = recent_counts.get(chain, 0) + 1
        if not recent_counts:
            return []
        candidate = max(recent_counts, key=recent_counts.get)
        if self.active_chain not in recent_counts:
            if self.active_chain is not None:
                self.chain_started_at = now
            self.active_chain = candidate
            self.pending_chain = None
        elif candidate != self.active_chain and recent_counts[candidate] >= recent_counts[self.active_chain] * 1.5:
            if self.pending_chain != candidate:
                self.pending_chain, self.pending_since = candidate, now
            elif now - self.pending_since >= .5:
                self.active_chain = candidate
                self.chain_started_at = now
                self.pending_chain = None
        else:
            self.pending_chain = None
        chain = self.active_chain
        return [(timestamp, interval) for timestamp, candidate, interval in samples
                if candidate == chain and timestamp >= self.chain_started_at
                and 0 <= now - timestamp <= window_seconds]

    def stop(self):
        process = self.process
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            if self.reader is not None:
                self.reader.join(timeout=2)
            # Terminating the consumer may leave an ETW session; close only ours.
            subprocess.run([str(self.executable), "--session_name", self.session,
                            "--terminate_existing_session"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
                           timeout=5, check=False)
        self.process = self.reader = self.pid = None
        self.active_chain = self.pending_chain = None
        self.pending_since = 0
        self.chain_started_at = float("-inf")
        with self.lock:
            self.samples.clear()
            self.runtime = None
