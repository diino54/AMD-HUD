"""Load a user-supplied TTF/OTF privately, without installing it in Windows."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct

DEFAULT_FONT = "Consolas"


def font_path(value):
    path = Path(os.path.expandvars(value)).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return path.resolve()


def font_family(value):
    path = font_path(value)
    if path.suffix.lower() not in (".ttf", ".otf"):
        raise ValueError("Choose a TrueType (.ttf) or OpenType (.otf) font file.")
    data = path.read_bytes()
    try:
        if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            raise ValueError("The selected file is not a supported font.")
        tables = struct.unpack_from(">H", data, 4)[0]
        for index in range(tables):
            tag, _, offset, length = struct.unpack_from(">4sIII", data, 12 + index * 16)
            if tag != b"name":
                continue
            table = data[offset:offset + length]
            _, count, storage = struct.unpack_from(">HHH", table)
            candidates = []
            for record in range(count):
                platform, encoding, language, name_id, size, start = struct.unpack_from(">HHHHHH", table, 6 + record * 12)
                if name_id not in (1, 16) or platform not in (0, 1, 3):
                    continue
                raw = table[storage + start:storage + start + size]
                try:
                    family = raw.decode("utf-16-be" if platform in (0, 3) else "mac_roman").strip("\x00 ")
                except UnicodeError:
                    continue
                if family:
                    # GDI selects the legacy family, including face-specific names.
                    candidates.append(((name_id == 1, platform == 3, language == 0x409), family))
            if candidates:
                return max(candidates)[1]
            break
    except struct.error as exc:
        raise ValueError("The selected font file is incomplete or invalid.") from exc
    raise ValueError("The font does not contain a usable family name.")


class PrivateFont:
    def __init__(self, value):
        self.path = str(font_path(value))
        self.family = font_family(self.path)
        self.loaded = False
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        self.gdi.AddFontResourceExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
        self.gdi.AddFontResourceExW.restype = ctypes.c_int
        self.gdi.RemoveFontResourceExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
        self.gdi.RemoveFontResourceExW.restype = wintypes.BOOL
        if not self.gdi.AddFontResourceExW(self.path, 0x10, None):
            raise ValueError("Windows could not load this font. Choose another TTF or OTF file.")
        self.loaded = True

    def close(self):
        if self.loaded:
            self.gdi.RemoveFontResourceExW(self.path, 0x10, None)
            self.loaded = False
