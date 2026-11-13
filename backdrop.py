"""Native acrylic, antialiased frame and cached shadow backing windows."""
import ctypes as c
from ctypes import wintypes as w
import os
import math
from composition_backdrop import RoundedBackdrop


def rounded_pixels(width, height, radius, color, border, opacity=1.0, border_only=False,
                   border_width=1, border_opacity=1.0):
    """Premultiplied BGRA with fractional edge coverage, not a binary region."""
    def rgb(value):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    fill, stroke = rgb(color), rgb(border)
    radius = min(radius, width / 2, height / 2)
    pixels = bytearray(width * height * 4)
    def coverage(x, y, inset):
        r = max(0, radius - inset)
        qx = abs(x - width / 2) - (width / 2 - inset - r)
        qy = abs(y - height / 2) - (height / 2 - inset - r)
        distance = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
        return max(0.0, min(1.0, 0.5 - distance))
    for y in range(height):
        for x in range(width):
            outer = coverage(x + .5, y + .5, 0)
            inner = min(outer, coverage(x + .5, y + .5, border_width))
            edge = (outer - inner) * border_opacity
            if border_only:
                fill_weight = 0
            else:
                fill_weight = outer - edge
            alpha = (fill_weight + edge) * opacity
            red, green, blue = [round((fill[i] * fill_weight + stroke[i] * edge) * opacity) for i in range(3)]
            offset = (y * width + x) * 4
            pixels[offset:offset + 4] = bytes((blue, green, red, round(alpha * 255)))
    return bytes(pixels)


def shadow_padding(blur):
    return 3 * max(0, math.ceil(blur / 2)) + 2


def shadow_pixels(width, height, radius, color, opacity, blur):
    """Blur a rounded alpha mask with three separable box passes (Gaussian approximation)."""
    pad = shadow_padding(blur)
    canvas_width, canvas_height = width + 2 * pad, height + 2 * pad
    mask = [0.0] * (canvas_width * canvas_height)
    source = rounded_pixels(width, height, radius, "#ffffff", "#ffffff", border_width=0)
    for y in range(height):
        offset = (y + pad) * canvas_width + pad
        mask[offset:offset + width] = source[(y * width) * 4 + 3:((y + 1) * width) * 4:4]
    box_radius = max(0, math.ceil(blur / 2))
    if box_radius:
        divisor = 2 * box_radius + 1
        for _ in range(3):
            horizontal = [0.0] * len(mask)
            for y in range(canvas_height):
                row = y * canvas_width
                total = sum(mask[row:row + box_radius + 1])
                for x in range(canvas_width):
                    horizontal[row + x] = total / divisor
                    if x - box_radius >= 0:
                        total -= mask[row + x - box_radius]
                    if x + box_radius + 1 < canvas_width:
                        total += mask[row + x + box_radius + 1]
            vertical = [0.0] * len(mask)
            for x in range(canvas_width):
                total = sum(horizontal[y * canvas_width + x] for y in range(box_radius + 1))
                for y in range(canvas_height):
                    vertical[y * canvas_width + x] = total / divisor
                    if y - box_radius >= 0:
                        total -= horizontal[(y - box_radius) * canvas_width + x]
                    if y + box_radius + 1 < canvas_height:
                        total += horizontal[(y + box_radius + 1) * canvas_width + x]
            mask = vertical
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    pixels = bytearray(canvas_width * canvas_height * 4)
    for index, value in enumerate(mask):
        alpha = max(0, min(255, round(value * opacity)))
        pixels[index * 4:index * 4 + 4] = bytes((round(blue * alpha / 255), round(green * alpha / 255),
                                               round(red * alpha / 255), alpha))
    return canvas_width, canvas_height, bytes(pixels)


class AcrylicBackdrop:
    def __init__(self, foreground, color, opacity, *, material=True, border="#403d52", border_only=False,
                 border_width=1, border_opacity=1.0, shadow=None):
        self.window = None
        self.composition = None
        self.foreground = foreground
        self.material, self.color, self.opacity = material, color, opacity
        self.border, self.border_only = border, border_only
        self.border_width, self.border_opacity, self.shadow = border_width, border_opacity, shadow
        self.g = c.WinDLL("gdi32", use_last_error=True)
        self.u = c.WinDLL("user32", use_last_error=True)
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.dwm = c.WinDLL("dwmapi", use_last_error=True)
        self.dwm.DwmSetWindowAttribute.argtypes = [w.HWND, w.DWORD, c.c_void_p, w.DWORD]
        self.dwm.DwmSetWindowAttribute.restype = c.c_long
        self.callback_type = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

        class WindowClass(c.Structure):
            _fields_ = [("style", w.UINT), ("procedure", self.callback_type),
                        ("class_extra", c.c_int), ("window_extra", c.c_int),
                        ("instance", w.HINSTANCE), ("icon", w.HICON), ("cursor", w.HANDLE),
                        ("brush", w.HBRUSH), ("menu", w.LPCWSTR), ("name", w.LPCWSTR)]

        self.u.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        self.u.DefWindowProcW.restype = c.c_ssize_t
        self.u.RegisterClassW.argtypes = [c.POINTER(WindowClass)]
        self.u.RegisterClassW.restype = w.WORD
        self.u.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                          c.c_int, c.c_int, c.c_int, c.c_int,
                                          w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p]
        self.u.CreateWindowExW.restype = w.HWND
        self.u.SetWindowPos.argtypes = [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT]
        self.u.SetWindowPos.restype = w.BOOL
        self.u.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
        self.u.ShowWindow.argtypes = [w.HWND, c.c_int]
        self.u.DestroyWindow.argtypes = [w.HWND]
        self.u.UnregisterClassW.argtypes = [w.LPCWSTR, w.HINSTANCE]
        self.k.GetModuleHandleW.argtypes = [w.LPCWSTR]
        self.k.GetModuleHandleW.restype = w.HMODULE

        def procedure(hwnd, message, wp, lp):
            if message == 0x84:  # WM_NCHITTEST: input passes to the game.
                return -1
            if message == 0x83 and wp:  # Keep the whole framed window as client area.
                return 0
            return self.u.DefWindowProcW(hwnd, message, wp, lp)

        self.callback = self.callback_type(procedure)
        self.instance = self.k.GetModuleHandleW(None)
        self.class_name = "AMDHUD_Backdrop_" + str(os.getpid()) + "_" + str(id(self))
        wc = WindowClass()
        wc.procedure, wc.instance, wc.name = self.callback, self.instance, self.class_name
        if not self.u.RegisterClassW(c.byref(wc)):
            raise c.WinError(c.get_last_error())
        try:
            # Own window, no redirection bitmap and no painted client background.
            self.window = self.u.CreateWindowExW(0x082000A8 if material else 0x080800A8,
                                                  self.class_name, "AMD HUD backdrop",
                                                  0x80000000,
                                                  0, 0, 1, 1, None, None, self.instance, None)
            if not self.window:
                raise c.WinError(c.get_last_error())
            if material:
                # The compositor clips both live host blur and tint, without
                # applying a binary GDI region or DWM's fixed-radius corners.
                enabled, square = w.BOOL(True), c.c_int(1)
                result = self.dwm.DwmSetWindowAttribute(self.window, 17, c.byref(enabled), c.sizeof(enabled))
                if result < 0:
                    raise RuntimeError("Windows rejected the host backdrop brush")
                self.dwm.DwmSetWindowAttribute(self.window, 33, c.byref(square), c.sizeof(square))
                self.composition = RoundedBackdrop(self.window, color, opacity)
            self.last_size = None
        except Exception:
            self.close()
            raise

    def sync(self, visible, radius):
        if not visible:
            self.u.ShowWindow(self.window, 0)
            return
        rect = w.RECT()
        if not self.u.GetWindowRect(self.foreground, c.byref(rect)):
            return
        width, height = rect.right - rect.left, rect.bottom - rect.top
        shape = (width, height, radius)
        x, y = rect.left, rect.top
        if self.shadow is not None:
            pad = shadow_padding(self.shadow["blur"])
            x += self.shadow["x"] - pad
            y += self.shadow["y"] - pad
            if shape != self.last_size:
                shadow_width, shadow_height, pixels = shadow_pixels(width, height, radius, self.color,
                                                                   self.opacity, self.shadow["blur"])
                self.paint(shadow_width, shadow_height, radius, x, y, pixels=pixels)
                self.last_size = shape
            width, height = width + 2 * pad, height + 2 * pad
        elif not self.material and shape != self.last_size:
            self.paint(width, height, radius, rect.left, rect.top)
            self.last_size = shape
        if self.material and shape != self.last_size:
            self.composition.resize(width, height, radius)
            self.last_size = shape
        # Insert immediately below the text window, without taking focus.
        self.u.SetWindowPos(self.window, self.foreground, x, y, width, height, 0x50)

    def paint(self, width, height, radius, x, y, pixels=None):
        class BitmapInfo(c.Structure):
            _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG),
                        ("planes", w.WORD), ("bits", w.WORD), ("compression", w.DWORD),
                        ("image_size", w.DWORD), ("xppm", w.LONG), ("yppm", w.LONG),
                        ("used", w.DWORD), ("important", w.DWORD), ("colors", w.DWORD * 3)]
        class Blend(c.Structure):
            _fields_ = [("op", w.BYTE), ("flags", w.BYTE), ("alpha", w.BYTE), ("format", w.BYTE)]
        self.g.CreateCompatibleDC.argtypes = [w.HDC]
        self.g.CreateCompatibleDC.restype = w.HDC
        self.g.CreateDIBSection.argtypes = [w.HDC, c.POINTER(BitmapInfo), w.UINT, c.POINTER(c.c_void_p), w.HANDLE, w.DWORD]
        self.g.CreateDIBSection.restype = w.HBITMAP
        self.g.SelectObject.argtypes = [w.HDC, w.HANDLE]
        self.g.SelectObject.restype = w.HANDLE
        self.g.DeleteObject.argtypes = [w.HANDLE]
        self.g.DeleteDC.argtypes = [w.HDC]
        self.u.UpdateLayeredWindow.argtypes = [w.HWND, w.HDC, c.POINTER(w.POINT), c.POINTER(w.SIZE),
                                              w.HDC, c.POINTER(w.POINT), w.DWORD, c.POINTER(Blend), w.DWORD]
        self.u.UpdateLayeredWindow.restype = w.BOOL
        info = BitmapInfo()
        info.size, info.width, info.height, info.planes, info.bits = 40, width, -height, 1, 32
        dc = self.g.CreateCompatibleDC(None)
        bits = c.c_void_p()
        bitmap = self.g.CreateDIBSection(dc, c.byref(info), 0, c.byref(bits), None, 0)
        if not dc or not bitmap or not bits:
            if bitmap:
                self.g.DeleteObject(bitmap)
            if dc:
                self.g.DeleteDC(dc)
            raise c.WinError(c.get_last_error())
        previous = self.g.SelectObject(dc, bitmap)
        try:
            if pixels is None:
                pixels = rounded_pixels(width, height, radius, self.color, self.border, self.opacity,
                                        self.border_only, self.border_width, self.border_opacity)
            c.memmove(bits, pixels, len(pixels))
            destination, size, source, blend = w.POINT(x, y), w.SIZE(width, height), w.POINT(), Blend(0, 0, 255, 1)
            if not self.u.UpdateLayeredWindow(self.window, None, c.byref(destination), c.byref(size), dc,
                                              c.byref(source), 0, c.byref(blend), 2):
                raise c.WinError(c.get_last_error())
        finally:
            self.g.SelectObject(dc, previous)
            self.g.DeleteObject(bitmap)
            self.g.DeleteDC(dc)

    def close(self):
        try:
            if self.composition:
                self.composition.close()
                self.composition = None
        finally:
            if self.window:
                self.u.DestroyWindow(self.window)
                self.window = None
            self.u.UnregisterClassW(self.class_name, self.instance)
