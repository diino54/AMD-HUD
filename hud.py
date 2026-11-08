"""Read-only ADLX GPU monitor and a lightweight Windows desktop HUD."""
import argparse
import ctypes
from ctypes import wintypes
import gc
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

from adlx import ADLX
from game_visibility import GameDetector
from fps_counter import FpsCounter
from single_instance import SingleInstance
from cpu_temperature import CpuTemperature
from backdrop import AcrylicBackdrop
from hud_control import HudControl
from font_support import DEFAULT_FONT, PrivateFont
from frametime_graph import GraphReveal, GraphScale, graph_columns, render_plot
from window_visibility import HudWindowVisibility, prevent_window_activation

ROOT = Path(__file__).resolve().parent
GRAPH_WINDOW_SECONDS = 7.0


class HudPanel(tk.Canvas):
    """Four fixed rows with Rosé Pine accents and a rounded one-pixel border."""
    def __init__(self, parent, config):
        self.config = config
        self.private_font = None
        family = DEFAULT_FONT
        if config.get("font_file"):
            try:
                self.private_font = PrivateFont(config["font_file"])
                family = self.private_font.family
            except (OSError, ValueError) as exc:
                print("Custom font unavailable; using Consolas: " + str(exc), file=sys.stderr)
        self.text_font = tkfont.Font(root=parent, family=family, size=config["font_size"])
        self.line_height = self.text_font.metrics("linespace")
        # Explicit pixel columns also support proportional custom fonts.
        self.label_width = max(self.text_font.measure("0" * 10), self.text_font.measure("DirectX 9"))
        self.middle_width = max(self.text_font.measure("0" * 9), self.text_font.measure("999.9GiB"))
        self.right_width = max(self.text_font.measure("0" * 12), self.text_font.measure("100.0°C"))
        self.panel_width = self.label_width + self.middle_width + self.right_width + 32
        self.panel_height = self.line_height * 4 + 24
        if config.get("frametime_graph", True):
            self.graph_font = tkfont.Font(root=parent, family=family, size=max(8, config["font_size"] - 2))
            self.graph_top = self.line_height * 4 + 24
            self.panel_height += self.graph_font.metrics("linespace") + config.get("frametime_graph_height", 48) + 12
        super().__init__(parent, width=self.panel_width, height=self.panel_height,
                         bg=config["background_color"], highlightthickness=0, bd=0)
        self.set_text(format_layout({}))

    def set_text(self, text):
        self.delete("metrics")
        # Background and border are rendered by the per-pixel-alpha layer.
        accents = self.config.get("row_colors", ["#9ccfd8", "#c4a7e7", "#f6c177", "#eb6f92"])
        for index, line in enumerate(text.splitlines()[:4]):
            y = 12 + self.line_height * index
            cells = (line[:10].rstrip(), line[10:19].strip(), line[19:].strip())
            for column, (x, anchor) in enumerate(((16, "nw"),
                    (16 + self.label_width + self.middle_width, "ne"), (self.panel_width - 16, "ne"))):
                color = accents[index % len(accents)] if column == 0 else self.config["text_color"]
                if cells[column] == "N/A":
                    color = self.config.get("muted_color", "#6e6a86")
                self.create_text(x, y, anchor=anchor, text=cells[column], font=self.text_font, fill=color, tags="metrics")

    def set_frametimes(self, samples):
        if not self.config.get("frametime_graph", True):
            return
        left, right = 16, self.panel_width - 16
        color = self.config.get("frametime_color", "#ebbcba")
        text_color = self.config["text_color"]
        top = self.graph_top + self.graph_font.metrics("linespace") + 5
        bottom = top + self.config.get("frametime_graph_height", 48) - 5
        if not hasattr(self, "_graph_items"):
            self.create_text(left, self.graph_top, anchor="nw", text="Frametime", font=self.graph_font,
                             fill=color, tags="frametime")
            waiting = self.create_text((left + right) / 2, (top + bottom) / 2,
                                       text="Waiting for frame data", font=self.graph_font,
                                       fill=text_color, tags="frametime")
            statistics = self.create_text(right, self.graph_top, anchor="ne", font=self.graph_font,
                                          fill=text_color, tags="frametime")
            self._graph_photo = tk.PhotoImage(master=self)
            line = self.create_image(left, top, anchor="nw", image=self._graph_photo,
                                     state="hidden", tags="frametime")
            self._graph_items = waiting, statistics, line
            self._graph_has_data = False
            self._graph_statistics = ""
            self._graph_scale = GraphScale()
            self._graph_reveal = GraphReveal()
        waiting_item, statistics_item, line_item = self._graph_items
        now = time.perf_counter()
        revealed, cursor = self._graph_reveal.update(samples, now, GRAPH_WINDOW_SECONDS)
        columns = graph_columns(revealed, cursor, GRAPH_WINDOW_SECONDS, right - left + 1, subpixel=True)
        # Always keep the progressively clipped tip, even when peak reduction
        # selects a different sample in the final time bucket.
        if revealed and revealed[-1][0] == cursor:
            tip = right - left, revealed[-1][1]
            if columns and abs(columns[-1][0] - tip[0]) < 1e-6:
                columns[-1] = tip
            else:
                columns.append(tip)
        if bool(columns) != self._graph_has_data:
            self.itemconfigure(waiting_item, state="hidden" if columns else "normal")
            self.itemconfigure(statistics_item, state="normal" if columns else "hidden")
            self.itemconfigure(line_item, state="normal" if columns else "hidden")
            self._graph_has_data = bool(columns)
        if not columns:
            self._graph_scale = GraphScale()
            return
        intervals = [interval for stamp, interval in samples if cursor - GRAPH_WINDOW_SECONDS <= stamp <= cursor]
        minimum, maximum = min(intervals), max(intervals)
        statistics = f"min {minimum:.1f} | max {maximum:.1f} ms"
        if self.graph_font.measure(statistics) + self.graph_font.measure("Frametime") + 12 > right - left:
            statistics = f"{minimum:.1f}–{maximum:.1f} ms"
        if statistics != self._graph_statistics:
            self.itemconfigure(statistics_item, text=statistics)
            self._graph_statistics = statistics
        ceiling = self._graph_scale.update(max(maximum, max(value for _, value in columns)), now)
        points = [(column, (1 - interval / ceiling) * (bottom - top)) for column, interval in columns]
        pixels = render_plot(points, right - left + 1, bottom - top + 2, color,
                             self.config["background_color"])
        self._graph_photo.configure(data=pixels, format="png")

    def destroy(self):
        try:
            super().destroy()
        finally:
            if self.private_font:
                self.private_font.close()


METRICS = {
    "fps": ("FPS", None, "fps"),
    "usage": ("GPU", "GPUUsage", "%"),
    "temperature": ("TEMP", "GPUTemperature", "°C"),
    "power": ("GPU POWER", "GPUPower", "W"),
    "vram": ("VRAM", "GPUVRAM", "MB"),
    "clock": ("CLOCK", "GPUClockSpeed", "MHz"),
    "fan": ("FAN", "GPUFanSpeed", "RPM"),
    "cpu_usage": ("CPU", "CPUUsage", "%"),
    "cpu_temperature": ("CPU TEMP", None, "°C"),
    "ram": ("RAM", "SystemRAM", "GiB"),
}


def format_layout(values, api_label="FPS"):
    def value(key, unit, decimals=0):
        reading = values.get(key)
        return "N/A" if reading is None else f"{reading:.{decimals}f}{unit}"

    fps = values.get("fps")
    frametime = "N/A" if fps is None or fps <= 0 else f"{1000 / fps:.1f} ms"
    rows = [
        ("GPU", value("usage", "%"), value("temperature", "°C")),
        ("CPU", value("cpu_usage", "%"), value("cpu_temperature", "°C")),
        ("RAM", value("ram", " GiB", 1), ""),
        (api_label, value("fps", " FPS"), frametime),
    ]
    return "\n".join(f"{caption:<10}{middle:>9}{right:>12}" for caption, middle, right in rows)


def load_config():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
    return validate_config(config)


def validate_config(config):
    config.setdefault("frametime_graph", True)
    config.setdefault("frametime_graph_height", 48)
    config.setdefault("frametime_color", "#ebbcba")
    if not isinstance(config["frametime_graph"], bool):
        raise ValueError("frametime_graph must be true or false")
    if not isinstance(config["frametime_graph_height"], int) or not 24 <= config["frametime_graph_height"] <= 160:
        raise ValueError("frametime_graph_height must be between 24 and 160 px")
    import re
    if not isinstance(config["frametime_color"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", config["frametime_color"]):
        raise ValueError("frametime_color must be #RRGGBB")
    config.setdefault("font_file", "")
    if not isinstance(config["font_file"], str):
        raise ValueError("font_file must be a font path or an empty string for the default font")
    defaults = {"border_enabled": True, "border_width": 1, "border_opacity": 1.0,
                "shadow_enabled": False, "shadow_x": 0, "shadow_y": 6,
                "shadow_opacity": .35, "shadow_color": "#000000", "shadow_blur": 16}
    for key, value in defaults.items():
        config.setdefault(key, value)
    for key in ("border_enabled", "shadow_enabled"):
        if not isinstance(config[key], bool):
            raise ValueError(key + " must be true or false")
    for key, minimum, maximum in (("border_width", 0, 8), ("shadow_x", -100, 100),
                                  ("shadow_y", -100, 100), ("shadow_blur", 0, 64)):
        if not isinstance(config[key], int) or not minimum <= config[key] <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
    for key in ("border_opacity", "shadow_opacity"):
        if not 0 <= config[key] <= 1:
            raise ValueError(key + " must be between 0 and 1")
    import re
    if not isinstance(config["shadow_color"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", config["shadow_color"]):
        raise ValueError("shadow_color must be #RRGGBB")
    if not isinstance(config["gpu_index"], int) or config["gpu_index"] < 0:
        raise ValueError("gpu_index must be a nonnegative integer")
    if not 250 <= config["refresh_ms"] <= 10000:
        raise ValueError("refresh_ms must be between 250 and 10000")
    if not 0.2 <= config["opacity"] <= 1.0:
        raise ValueError("opacity must be between 0.2 and 1.0")
    if not isinstance(config.get("blur", False), bool):
        raise ValueError("blur must be true or false")
    if not 0.2 <= config.get("blur_opacity", 0.88) <= 1.0:
        raise ValueError("blur_opacity must be between 0.2 and 1.0")
    if not config["metrics"] or any(key not in METRICS for key in config["metrics"]):
        raise ValueError("Invalid metrics list")
    if not 8 <= config["font_size"] <= 48:
        raise ValueError("font_size must be between 8 and 48")
    config.setdefault("corner_radius", 16)
    if not isinstance(config["corner_radius"], int) or not 0 <= config["corner_radius"] <= 100:
        raise ValueError("corner_radius must be an integer between 0 and 100")
    config.setdefault("games_only", True)
    config.setdefault("game_executables", [])
    config.setdefault("excluded_executables", ["wmplayer.exe", "losslessscaling.exe"])
    if not isinstance(config["games_only"], bool):
        raise ValueError("games_only must be true or false")
    for key in ("game_executables", "excluded_executables"):
        if not isinstance(config[key], list) or any(not isinstance(item, str) or not item.strip()
                                                  for item in config[key]):
            raise ValueError(key + " must be a list of executable paths/names")
    import ntpath
    if any(not ntpath.isabs(path) for path in config["game_executables"]):
        raise ValueError("game_executables must contain full executable paths")
    return config


class Monitor:
    def __init__(self, index):
        self.cpu_temperature = CpuTemperature()
        self.helper = ADLX.ADLXHelper()
        self.system = self.service = self.gpu = self.support = None
        self.initialized = False
        result = self.helper.Initialize()
        if result != ADLX.ADLX_RESULT.ADLX_OK:
            raise RuntimeError("ADLX initialization failed: " + str(result))
        self.initialized = True
        try:
            self.system = self.helper.GetSystemServices()
            self.service = self.system.GetPerformanceMonitoringServices()
            gpus = list(self.system.GetGPUs())
            if index >= len(gpus):
                raise ValueError("GPU index outside available GPU list")
            self.gpu = gpus[index]
            self.support = self.service.GetSupportedGPUMetrics(self.gpu)
            self.name = self.gpu.Name()
            self.version = self.helper.QueryVersion()
        except Exception:
            # No native interfaces may remain alive when ADLX terminates.
            gpus = None
            self.close()
            raise

    def read(self, keys):
        metrics = self.service.GetCurrentGPUMetrics(self.gpu)
        system_metrics = self.service.GetCurrentSystemMetrics() if any(
            key in keys for key in ("cpu_usage", "ram")) else None
        values = {}
        for key in keys:
            if key == "cpu_temperature":
                values[key] = self.cpu_temperature.read()
                continue
            if key in ("cpu_usage", "ram"):
                reading = getattr(system_metrics, METRICS[key][1])() if system_metrics else None
                values[key] = reading / 1024 if key == "ram" and reading is not None else reading
                continue
            if key == "fps":
                # Filled by the HUD's per-process PresentMon counter, not ADLX.
                values[key] = None
                continue
            method = METRICS[key][1]
            if getattr(self.support, "IsSupported" + method)():
                values[key] = getattr(metrics, method)()
            else:
                values[key] = None
        return {"gpu": self.name, "adlx_version": self.version, "metrics": values}

    def close(self):
        self.cpu_temperature.close()
        self.support = self.gpu = self.service = self.system = None
        gc.collect()
        if self.initialized:
            self.helper.Terminate()
            self.initialized = False


@prevent_window_activation()
def show_hud(monitor, config, smoke_test=False, control=None):
    # A fully opaque material has no visible blur: avoid an unnecessary native
    # backing window. For translucent acrylic use Windows' native 8px corners
    # on both layers so the material and the drawn border match exactly.
    config = dict(config)
    use_acrylic = config.get("blur", False) and config.get("blur_opacity", 0.88) < 1
    if config.get("blur", False) and not use_acrylic:
        config["opacity"] = 1.0
    if use_acrylic and config["corner_radius"]:
        config["corner_radius"] = 8
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.SetWindowLongW.restype = wintypes.LONG
    user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    root = tk.Tk()
    root.withdraw()  # Do not flash a panel on the desktop before checking the foreground game.
    root.title("AMD HUD")
    root.iconbitmap(default=str(ROOT / "assets/app-icon.ico"))
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", config["opacity"])
    root.geometry("{:+d}{:+d}".format(config["x"], config["y"]))
    root.configure(bg=config["background_color"])
    label = HudPanel(root, config)
    label.pack()
    registered = []
    samples = [0]
    detector = GameDetector(config)
    fps_counter = FpsCounter()
    manual_hidden = [False]
    visible = [False]
    backdrop = None
    smooth_frame = None
    shadow_layer = None
    outcome = [None]
    preview_until = [0.0]
    try:
        for identifier, key in [(1, 0x79), (2, 0x7A)]:
            if not user32.RegisterHotKey(None, identifier, 0x4003, key):
                if ctypes.get_last_error() == 1409:
                    raise RuntimeError("Shortcut Ctrl+Alt+F" + str(key - 0x6F) +
                                       " is already in use by another application.")
                raise RuntimeError("Cannot register Ctrl+Alt+F" + str(key - 0x6F) +
                                   "; Win32 error " + str(ctypes.get_last_error()))
            registered.append(identifier)

        def refresh():
            if not visible[0] and not smoke_test:
                root.after(config["refresh_ms"], refresh)
                return
            try:
                snapshot = monitor.read(config["metrics"])
                if "fps" in snapshot["metrics"]:
                    snapshot["metrics"]["fps"] = fps_counter.value()
                label.set_text(format_layout(snapshot["metrics"], fps_counter.api_label()))
                samples[0] += 1
            except Exception as exc:
                label.set_text(format_layout({}))
                print("ADLX read error: " + str(exc), file=sys.stderr)
            root.after(config["refresh_ms"], refresh)

        def refresh_graph():
            started = time.perf_counter()
            if visible[0]:
                label.set_frametimes(fps_counter.frametime_samples(GRAPH_WINDOW_SECONDS + 1.5))
            # Reuse canvas items at approximately 60 Hz, accounting for drawing
            # time. Hidden HUDs do not need animation-rate timer wakeups.
            delay = max(1, round(1000 / 60 - (time.perf_counter() - started) * 1000)) if visible[0] else 200
            root.after(delay, refresh_graph)

        def poll_hotkeys():
            if control:
                if control.poll("stop"):
                    root.destroy()
                    return
                if control.poll("reload"):
                    outcome[0] = "reload"
                    root.destroy()
                    return
                if control.poll("preview"):
                    import time
                    manual_hidden[0] = False
                    preview_until[0] = time.monotonic() + 10
            message = wintypes.MSG()
            while user32.PeekMessageW(ctypes.byref(message), None, 0x312, 0x312, 1):
                if message.wParam == 2:
                    root.destroy()
                    return
                if message.wParam == 1:
                    manual_hidden[0] = not manual_hidden[0]
            root.after(100, poll_hotkeys)

        root.update_idletasks()
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        style = user32.GetWindowLongW(hwnd, -20) | 0x08000000 | 0x80
        if config["click_through"]:
            style |= 0x80000 | 0x20
        user32.SetWindowLongW(hwnd, -20, style)
        window_visibility = HudWindowVisibility(root)
        if not use_acrylic and style & 0x80000:
            # At alpha=1 Tk removes WS_EX_LAYERED. Re-adding it for click-through
            # requires initializing its attributes, otherwise the HUD is invisible.
            if not user32.SetLayeredWindowAttributes(hwnd, 0, round(config["opacity"] * 255), 2):
                raise ctypes.WinError(ctypes.get_last_error())
        if use_acrylic:
            try:
                backdrop = AcrylicBackdrop(hwnd, config["background_color"], config.get("blur_opacity", 0.88))
                root.attributes("-alpha", 1.0)
                root.attributes("-transparentcolor", config["background_color"])
            except (OSError, RuntimeError, AttributeError) as exc:
                print("Acrylic unavailable; using plain background: " + str(exc), file=sys.stderr)

        smooth_frame = AcrylicBackdrop(hwnd, config["background_color"],
                                       1.0 if backdrop else config["opacity"], material=False,
                                       border=config.get("border_color", "#403d52"), border_only=bool(backdrop),
                                       border_width=config["border_width"] if config["border_enabled"] else 0,
                                       border_opacity=config["border_opacity"])
        if config["shadow_enabled"] and config["shadow_opacity"] > 0:
            shadow_layer = AcrylicBackdrop(hwnd, config["shadow_color"], config["shadow_opacity"],
                                            material=False, shadow={"x": config["shadow_x"],
                                            "y": config["shadow_y"], "blur": config["shadow_blur"]})
        root.attributes("-alpha", 1.0)
        root.attributes("-transparentcolor", config["background_color"])

        def poll_visibility():
            import time
            target = detector.current_target()
            should_show = not manual_hidden[0] and (smoke_test or time.monotonic() < preview_until[0]
                                                   or not config["games_only"] or target is not None)
            if should_show != visible[0]:
                visible[0] = should_show
                if should_show:
                    # Discard the last game's displayed values before revealing the panel.
                    label.set_text(format_layout({}))
                    label.set_frametimes([])
                window_visibility.set_visible(should_show)
            elif should_show:
                # A game can raise its own topmost window when changing display
                # mode without changing its foreground PID or HUD visibility.
                window_visibility.keep_above_game()
            if shadow_layer:
                shadow_layer.sync(should_show, config["corner_radius"])
            if backdrop:
                backdrop.sync(should_show, config["corner_radius"])
            smooth_frame.sync(should_show, config["corner_radius"])
            capture_needed = "fps" in config["metrics"] or config["frametime_graph"]
            fps_counter.target(target["pid"] if should_show and target and capture_needed else None)
            root.after(200, poll_visibility)

        poll_visibility()
        refresh()
        if config["frametime_graph"]:
            refresh_graph()
        poll_hotkeys()
        if smoke_test:
            root.after(3200, root.destroy)
        root.mainloop()
    finally:
        if shadow_layer:
            shadow_layer.close()
        if smooth_frame:
            smooth_frame.close()
        if backdrop:
            backdrop.close()
        fps_counter.stop()
        for identifier in registered:
            user32.UnregisterHotKey(None, identifier)
        try:
            root.destroy()
        except tk.TclError:
            pass
    if smoke_test:
        if samples[0] < 2:
            raise RuntimeError("HUD smoke test: insufficient successful readings")
        print(json.dumps({"hud_smoke_test": "passed", "successful_readings": samples[0]}))
    return outcome[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="Read one real GPU sample and exit")
    parser.add_argument("--smoke-test", action="store_true", help="Show HUD briefly and exit")
    parser.add_argument("--probe-game", action="store_true", help="Report recognized games and foreground app")
    args = parser.parse_args()
    monitor = None
    instance = None
    control = None
    try:
        if not args.probe and not args.probe_game:
            instance = SingleInstance(ROOT)
            if not instance.acquire():
                print("AMD HUD is already running. Ctrl+Alt+F10: toggle visibility in games; Ctrl+Alt+F11: close.")
                return 0
        config = load_config()
        if args.probe_game:
            print(json.dumps(GameDetector(config).diagnostic(), indent=2, ensure_ascii=True))
            return 0
        monitor = Monitor(config["gpu_index"])
        if args.probe:
            monitor.cpu_temperature.read(wait=1.5)
            print(json.dumps(monitor.read(config["metrics"]), indent=2))
        else:
            control = HudControl(ROOT)
            control.reset()
            while show_hud(monitor, config, args.smoke_test, control) == "reload":
                # Keep the single-instance lock while releasing native resources.
                monitor.close()
                monitor = None
                config = load_config()
                monitor = Monitor(config["gpu_index"])
        return 0
    except Exception as exc:
        print("AMD HUD: " + str(exc), file=sys.stderr)
        return 1
    finally:
        try:
            if monitor:
                monitor.close()
        finally:
            if instance:
                instance.close()
            if control:
                control.close()


if __name__ == "__main__":
    sys.exit(main())
