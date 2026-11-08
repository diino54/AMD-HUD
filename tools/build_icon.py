"""Build the Windows icon and PNG preview from the editable SVG source."""
from pathlib import Path
import struct

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]


def main():
    renderer = QSvgRenderer(str(ROOT / "assets/app-icon.svg"))
    if not renderer.isValid():
        raise RuntimeError("Cannot load the application icon SVG")
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    entries, payloads = [], []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Cannot encode the application icon")
        payload = bytes(data)
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                   1, 32, len(payload), offset))
        payloads.append(payload)
        offset += len(payload)
        if size == 256:
            (ROOT / "assets/app-icon.png").write_bytes(payload)
    (ROOT / "assets/app-icon.ico").write_bytes(
        struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries) + b"".join(payloads))
    print("Built application icon in 9 sizes (16–256 px).")


if __name__ == "__main__":
    main()
