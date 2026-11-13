"""Windows host-backdrop brush with a compositor-owned rounded clip.

ABI declarations follow the Windows SDK Windows.UI.Composition and desktop
interop headers. No SDK, generated binding, or compiler is needed at runtime.
"""
import atexit
import ctypes as c
from ctypes import wintypes as w
import threading
import time
import uuid


class Guid(c.Structure):
    _fields_ = [("bytes", c.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__()
        self.bytes[:] = uuid.UUID(value).bytes_le


class Vector2(c.Structure):
    _fields_ = [("x", c.c_float), ("y", c.c_float)]


class Color(c.Structure):
    _fields_ = [("a", c.c_ubyte), ("r", c.c_ubyte), ("g", c.c_ubyte), ("b", c.c_ubyte)]


def check(result, operation):
    if result < 0:
        raise OSError(f"{operation} failed (HRESULT 0x{result & 0xffffffff:08X})")


class Interface:
    """One owned COM reference; every interface uses its own vtable pointer."""
    def __init__(self, pointer):
        self.pointer = pointer

    def call(self, slot, types=(), *args):
        table = c.cast(self.pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
        function = c.WINFUNCTYPE(c.c_long, c.c_void_p, *types)(table[slot])
        check(function(self.pointer, *args), f"Composition method {slot}")

    def query(self, iid):
        pointer = c.c_void_p()
        self.call(0, (c.POINTER(Guid), c.POINTER(c.c_void_p)), c.byref(Guid(iid)), c.byref(pointer))
        return Interface(pointer)

    def create(self, slot, types=(), *args):
        pointer = c.c_void_p()
        self.call(slot, (*types, c.POINTER(c.c_void_p)), *args, c.byref(pointer))
        return Interface(pointer)

    def release(self):
        if self.pointer:
            table = c.cast(self.pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
            c.WINFUNCTYPE(w.ULONG, c.c_void_p)(table[2])(self.pointer)
            self.pointer = None

    def close_object(self):
        closable = self.query("30D5A829-7FA4-4026-83BB-D75BAE4EA99E")
        try:
            closable.call(6)  # IClosable.Close
        finally:
            closable.release()


_runtime = None


class CompositionRuntime:
    """One dispatcher queue on the HUD GUI thread, retained across reloads."""
    def __init__(self):
        self.thread = threading.get_ident()
        self.controller = None
        self.initialized = False
        self.base = c.WinDLL("combase")
        self.base.RoInitialize.argtypes = [w.DWORD]
        self.base.RoInitialize.restype = c.c_long
        self.base.RoUninitialize.argtypes = []
        self.base.RoUninitialize.restype = None
        self.base.WindowsCreateString.argtypes = [w.LPCWSTR, w.UINT, c.POINTER(c.c_void_p)]
        self.base.WindowsCreateString.restype = c.c_long
        self.base.WindowsDeleteString.argtypes = [c.c_void_p]
        self.base.WindowsDeleteString.restype = c.c_long
        self.base.RoActivateInstance.argtypes = [c.c_void_p, c.POINTER(c.c_void_p)]
        self.base.RoActivateInstance.restype = c.c_long
        self.base.RoGetActivationFactory.argtypes = [c.c_void_p, c.POINTER(Guid), c.POINTER(c.c_void_p)]
        self.base.RoGetActivationFactory.restype = c.c_long
        result = self.base.RoInitialize(0)
        # Qt or another GUI framework may already have initialized this thread.
        if result != -2147417850:  # RPC_E_CHANGED_MODE
            check(result, "RoInitialize")
            self.initialized = True
        try:
            factory = self.activate("Windows.System.DispatcherQueue", "A96D83D7-9371-4517-9245-D0824AC12C74")
            try:
                queue = factory.create(6)
                try:
                    exists = bool(queue.pointer.value)
                finally:
                    queue.release()
            finally:
                factory.release()
            if not exists:
                class Options(c.Structure):
                    _fields_ = [("size", w.DWORD), ("thread_type", c.c_int), ("apartment_type", c.c_int)]
                core = c.WinDLL("CoreMessaging")
                core.CreateDispatcherQueueController.argtypes = [Options, c.POINTER(c.c_void_p)]
                core.CreateDispatcherQueueController.restype = c.c_long
                pointer = c.c_void_p()
                check(core.CreateDispatcherQueueController(Options(c.sizeof(Options), 2, 0), c.byref(pointer)),
                      "CreateDispatcherQueueController")
                self.controller = Interface(pointer)
        except Exception:
            self.close()
            raise

    def activate(self, name, iid=None):
        string, pointer = c.c_void_p(), c.c_void_p()
        check(self.base.WindowsCreateString(name, len(name), c.byref(string)), "WindowsCreateString")
        try:
            if iid is None:
                check(self.base.RoActivateInstance(string, c.byref(pointer)), "RoActivateInstance " + name)
            else:
                check(self.base.RoGetActivationFactory(string, c.byref(Guid(iid)), c.byref(pointer)),
                      "RoGetActivationFactory " + name)
            return Interface(pointer)
        finally:
            self.base.WindowsDeleteString(string)

    def close(self):
        try:
            if self.controller:
                action = self.controller.create(7)  # ShutdownQueueAsync
                try:
                    info = action.query("00000036-0000-0000-C000-000000000046")  # IAsyncInfo
                    try:
                        # Teardown only: the dispatcher must drain on its owner
                        # thread before COM is uninitialized. No live GUI waits.
                        user32 = c.WinDLL("user32")
                        user32.PeekMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
                        user32.PeekMessageW.restype = w.BOOL
                        user32.TranslateMessage.argtypes = [c.POINTER(w.MSG)]
                        user32.TranslateMessage.restype = w.BOOL
                        user32.DispatchMessageW.argtypes = [c.POINTER(w.MSG)]
                        user32.DispatchMessageW.restype = c.c_ssize_t
                        user32.MsgWaitForMultipleObjectsEx.argtypes = [w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.DWORD]
                        user32.MsgWaitForMultipleObjectsEx.restype = w.DWORD
                        deadline = time.perf_counter() + 5
                        status, message = c.c_int(), w.MSG()
                        while True:
                            info.call(7, (c.POINTER(c.c_int),), c.byref(status))
                            if status.value != 0:
                                break
                            if time.perf_counter() >= deadline:
                                raise RuntimeError("Composition dispatcher shutdown timed out")
                            while user32.PeekMessageW(c.byref(message), None, 0, 0, 1):
                                user32.TranslateMessage(c.byref(message))
                                user32.DispatchMessageW(c.byref(message))
                            user32.MsgWaitForMultipleObjectsEx(0, None, 10, 0x04FF, 4)
                    finally:
                        info.release()
                finally:
                    action.release()
        finally:
            if self.controller:
                self.controller.release()
                self.controller = None
            if self.initialized:
                self.base.RoUninitialize()
                self.initialized = False


def close_composition_runtime():
    global _runtime
    if _runtime is not None:
        try:
            _runtime.close()
        finally:
            _runtime = None


atexit.register(close_composition_runtime)


class RoundedBackdrop:
    """Live host blur and tint clipped together with fractional edge coverage."""
    def __init__(self, hwnd, color, opacity):
        global _runtime
        self.references = []
        self.target = self.compositor = None
        self.last_shape = None
        if _runtime is None:
            _runtime = CompositionRuntime()
        if _runtime.thread != threading.get_ident():
            raise RuntimeError("Composition backdrop must stay on the HUD GUI thread")
        try:
            compositor = self.own(_runtime.activate("Windows.UI.Composition.Compositor"))
            self.compositor = compositor
            main = self.own(compositor.query("B403CA50-7F8C-4E83-985F-CC45060036D8"))
            interop = self.own(compositor.query("29E691FA-4567-4DCA-B319-D0F207EB6807"))
            desktop = self.own(interop.create(3, (w.HWND, w.BOOL), hwnd, False))
            self.target = self.own(desktop.query("A1BEA8BA-D726-4663-8129-6B5E7927FFA6"))
            root = self.own(main.create(9))  # CreateContainerVisual
            self.root = self.visual(root)
            children = self.own(root.create(6))
            host_factory = self.own(compositor.query("C9DD8EF0-6EB1-4E3C-A658-675D9C64D4AB"))
            host = self.own(host_factory.create(6))
            blur_brush = self.own(host.query("AB0D7608-30C0-40E9-B568-B60A6BD1FB46"))
            red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            tint = self.own(main.create(8, (Color,), Color(round(opacity * 255), red, green, blue)))
            tint_brush = self.own(tint.query("AB0D7608-30C0-40E9-B568-B60A6BD1FB46"))
            self.sprites = []
            for brush in (blur_brush, tint_brush):
                sprite = self.own(main.create(22))  # CreateSpriteVisual
                sprite.call(7, (c.c_void_p,), brush.pointer)  # ISpriteVisual.put_Brush
                visual = self.visual(sprite)
                self.sprites.append(visual)
                children.call(9, (c.c_void_p,), visual.pointer)  # InsertAtTop
            geometry_factory = self.own(compositor.query("48EA31AD-7FCD-4076-A79C-90CC4B852C9B"))
            self.geometry = self.own(geometry_factory.create(20))  # CreateRoundedRectangleGeometry
            geometry = self.own(self.geometry.query("E985217C-6A17-4207-ABD8-5FD3DD612A9D"))
            clip_factory = self.own(compositor.query("7A38B2BD-CEC8-4EEB-830F-D8D07AEDEBC3"))
            geometric_clip = self.own(clip_factory.create(7, (c.c_void_p,), geometry.pointer))
            clip = self.own(geometric_clip.query("1CCD2A52-CFC7-4ACE-9983-146BB8EB6A3C"))
            self.root.call(15, (c.c_void_p,), clip.pointer)  # IVisual.put_Clip
            self.target.call(7, (c.c_void_p,), self.root.pointer)
        except Exception:
            self.close()
            raise

    def own(self, interface):
        self.references.append(interface)
        return interface

    def visual(self, interface):
        return self.own(interface.query("117E202D-A859-4C89-873B-C2AA566788E3"))

    def resize(self, width, height, radius):
        shape = width, height, radius
        if shape == self.last_shape:
            return
        radius = max(0, min(radius, width / 2, height / 2))
        size = Vector2(width, height)
        for visual in (self.root, *self.sprites):
            visual.call(36, (Vector2,), size)  # IVisual.put_Size
        self.geometry.call(11, (Vector2,), size)
        self.geometry.call(7, (Vector2,), Vector2(radius, radius))
        self.last_shape = shape

    def close(self):
        try:
            if self.target:
                self.target.call(7, (c.c_void_p,), None)
                self.target.close_object()
            if self.compositor:
                self.compositor.close_object()
        finally:
            for reference in reversed(self.references):
                reference.release()
            self.references.clear()
            self.target = self.compositor = None
