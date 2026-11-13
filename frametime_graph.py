"""Time-based reduction for a frametime sparkline; preserve frame spikes."""
import math

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen


class GraphScale:
    """Expand for real spikes immediately; let the range contract gradually."""
    def __init__(self):
        self.ceiling = None
        self.updated_at = None

    def update(self, maximum, now):
        target = max(16.7, maximum * 1.15)
        if self.ceiling is None or target >= self.ceiling:
            self.ceiling = target
        else:
            elapsed = max(0, now - self.updated_at)
            self.ceiling = target + (self.ceiling - target) * math.exp(-elapsed / .75)
        self.updated_at = now
        return self.ceiling


class GraphReveal:
    """Advance a drawing cursor through measured frames, never past known data."""
    PLAYBACK_DELAY = .25
    def __init__(self):
        self.cursor = None
        self.updated_at = None
        self.latest = None
        self.viewport = None

    def update(self, samples, now, window_seconds):
        samples = sorted((stamp, value) for stamp, value in samples
                         if math.isfinite(stamp) and math.isfinite(value)
                         and value > 0 and stamp <= now)
        if not samples:
            self.__init__()
            return [], now
        first, latest = samples[0][0], samples[-1][0]
        if self.cursor is None or latest < self.latest:
            # Start with the first point, so even the initial delivery batch is
            # drawn progressively instead of appearing as a completed line.
            self.cursor = first
            self.viewport = first
        else:
            elapsed = max(0, now - self.updated_at)
            # Scrolling follows elapsed QPC time even when delivery runs dry.
            # Only the drawing boundary stops at the latest measured frame.
            self.viewport += elapsed
            # Keep a small delivery buffer so ordinary CSV batches do not make
            # playback repeatedly reach the end and stop. Never invent frames.
            available = max(first, min(latest, now - self.PLAYBACK_DELAY))
            self.cursor = max(self.cursor, min(available, self.viewport))
        self.updated_at, self.latest = now, latest
        revealed = []
        previous = None
        for stamp, value in samples:
            if stamp <= self.cursor:
                previous = stamp, value
                if stamp >= self.viewport - window_seconds:
                    revealed.append((stamp, value))
            else:
                if previous is not None and self.cursor > previous[0]:
                    fraction = (self.cursor - previous[0]) / (stamp - previous[0])
                    # This is the clipped endpoint of a known straight segment,
                    # not an extra measurement or a prediction of the next frame.
                    revealed.append((self.cursor, previous[1] + fraction * (value - previous[1])))
                break
        return revealed, self.cursor


def render_plot(points, width, height, color, background):
    """Render straight subpixel segments with antialiasing for the Tk image item."""
    image = QImage(width, height, QImage.Format_RGB32)
    # Tk's color-keyed text window also uses this backing color. Keeping it
    # identical makes the unused image area transparent with the rest of Tk.
    image.fill(QColor(background))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(color), 1.25, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if len(points) == 1:
            painter.drawPoint(*points[0])
        elif points:
            path = QPainterPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            painter.drawPath(path)
    finally:
        painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Cannot render the frametime graph")
    return bytes(data)


def graph_columns(samples, now, window_seconds, width, subpixel=False):
    if width < 2 or window_seconds <= 0:
        return []
    columns = {}
    bucket_seconds = window_seconds / (width - 1)
    for timestamp, interval in samples:
        age = now - timestamp
        if not math.isfinite(interval) or interval <= 0 or not 0 <= age <= window_seconds:
            continue
        position = min(width - 1, (1 - age / window_seconds) * (width - 1))
        # Anchor reduction to sample time, not the moving screen pixel grid.
        # Otherwise scrolling alone changes which peaks are joined together.
        bucket = math.floor(timestamp / bucket_seconds)
        if bucket not in columns or interval > columns[bucket][1]:
            columns[bucket] = (position if subpixel else int(position), interval)
    return [point for _, point in sorted(columns.items())]
