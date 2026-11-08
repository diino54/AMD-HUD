"""Short, interruptible Qt feedback that never delays input or persists UI state."""
import ctypes
import sys
from functools import lru_cache

from PySide6.QtCore import QObject, QEvent, QEasingCurve, QRectF, QPointF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QIcon
from PySide6.QtWidgets import (QApplication, QPushButton, QCheckBox, QLineEdit,
                               QTabBar, QScrollArea, QGraphicsOpacityEffect, QLabel)
from PySide6.QtWidgets import QWidget


@lru_cache(maxsize=1)
def motion_enabled():
    if sys.platform == "win32":
        enabled = ctypes.c_int(1)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint,
                                                ctypes.c_void_p, ctypes.c_uint]
        user32.SystemParametersInfoW.restype = ctypes.c_int
        if user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return bool(enabled.value)  # SPI_GETCLIENTAREAANIMATION; read only.
    return True


def mix(first, second, amount):
    first, second = QColor(first), QColor(second)
    amount = max(0., min(1., amount))
    return QColor.fromRgbF(*(a + (b - a) * amount for a, b in
                             zip(first.getRgbF(), second.getRgbF())))


class MotionValue(QObject):
    def __init__(self, owner, initial, changed):
        super().__init__(owner)
        self.value = float(initial)
        self.changed = changed
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self._apply)

    def _apply(self, value):
        self.value = float(value)
        self.changed(self.value)

    def snap(self, value):
        self.animation.stop()
        self._apply(value)

    def to(self, value, duration=140, animated=True):
        start = self.value
        self.animation.stop()
        if not animated or not motion_enabled() or abs(self.value - value) < .001:
            self._apply(value)
            return
        # Reconfiguring a stopped QVariantAnimation at its old playback time can
        # emit an intermediate value. Keep reversal anchored to what was painted.
        blocked = self.animation.blockSignals(True)
        try:
            self.animation.setDuration(duration)
            self.animation.setStartValue(start)
            self.animation.setEndValue(float(value))
            self.animation.setCurrentTime(0)
        finally:
            self.animation.blockSignals(blocked)
        self._apply(start)
        self.animation.start()


class RevealViewport(QWidget):
    """Clip a full-height form instead of compressing its controls during reveal."""
    def __init__(self):
        super().__init__()
        self.content = QWidget(self)

    def sizeHint(self):
        return self.content.sizeHint()

    def minimumSizeHint(self):
        return QSize(0, 0)

    def layout_content(self):
        natural = max(0, self.content.sizeHint().height())
        self.content.setGeometry(0, 0, self.width(), natural)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_content()


class InteractionMotion(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        self.hover = MotionValue(self, 0, lambda _: widget.update())
        self.press = MotionValue(self, 0, lambda _: widget.update())
        self.focus = MotionValue(self, 0, lambda _: widget.update())
        self.enabled = MotionValue(self, widget.isEnabled(), lambda _: widget.update())
        widget.setAttribute(Qt.WA_Hover)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        kind = event.type()
        visible = watched.isVisible()
        if kind == QEvent.Enter:
            self.hover.to(1, animated=visible)
        elif kind == QEvent.Leave:
            self.hover.to(0, animated=visible)
        elif kind in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            self.press.to(1, 65, visible)
        elif kind == QEvent.MouseButtonRelease:
            self.press.to(0, 160, visible)
        elif kind == QEvent.KeyPress and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.press.to(1, 65, visible)
        elif kind == QEvent.KeyRelease:
            self.press.to(0, 160, visible)
        elif kind == QEvent.FocusIn:
            self.focus.to(1, 150, visible)
        elif kind == QEvent.FocusOut:
            self.focus.to(0, 150, visible)
            self.press.to(0, 100, visible)
        elif kind == QEvent.EnabledChange:
            self.enabled.to(float(watched.isEnabled()), 150, visible)
            if not watched.isEnabled():
                self.hover.snap(0)
                self.press.snap(0)
        elif kind == QEvent.Hide:
            for value in (self.hover, self.press, self.focus):
                value.snap(0)
            self.enabled.snap(float(watched.isEnabled()))
        return False


class MotionButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.feedback = InteractionMotion(self)
        self.disclosure = False
        self.disclosure_progress = 1.
        self.ripple_center = QPointF()
        self.ripple = MotionValue(self, 1, lambda _: self.update())
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.ripple_center = event.position()
            self.ripple.snap(0)
            self.ripple.to(1, 340, self.isVisible())
        super().mousePressEvent(event)

    def hideEvent(self, event):
        self.ripple.snap(1)
        super().hideEvent(event)

    def paintEvent(self, event):
        name = self.objectName()
        if name == "primary":
            base, hover, pressed, border = "#246bce", "#307bdf", "#1855ac", "#347cde"
            disabled, disabled_border, ink = "#202b3a", "#293b54", "#ffffff"
        elif name == "step":
            base, hover, pressed, border = "#191919", "#292929", "#121212", "#2c2c2c"
            disabled, disabled_border, ink = "#252525", "#303030", "#dddddd"
        elif self.disclosure:
            base, hover, pressed, border = "#00000000", "#12ffffff", "#18ffffff", "#00000000"
            disabled, disabled_border, ink = base, border, "#bdbdbd"
        else:
            base, hover, pressed, border = "#333333", "#3b3b3b", "#242424", "#373737"
            disabled, disabled_border, ink = "#252525", "#303030", "#dddddd"
        f = self.feedback
        fill = mix(mix(base, hover, f.hover.value), pressed, f.press.value)
        fill = mix(disabled, fill, f.enabled.value)
        stroke = mix(border, "#4a4a4a", f.hover.value * (0 if self.disclosure else 1))
        stroke = mix(stroke, "#9fbce3", f.focus.value)
        stroke = mix(disabled_border, stroke, f.enabled.value)
        ink = mix("#7f91ab" if name == "primary" else "#777777", ink, f.enabled.value)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(.6, .6, -.6, -.6)
        radius = 4 if self.disclosure else 7
        painter.setBrush(fill)
        painter.setPen(QPen(stroke, 1))
        painter.drawRoundedRect(rect, radius, radius)
        if self.ripple.value < 1 and self.isEnabled():
            clip = QPainterPath()
            clip.addRoundedRect(rect, radius, radius)
            painter.save()
            painter.setClipPath(clip)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(200, 218, 245, round(24 * (1 - self.ripple.value))))
            r = max(self.width(), self.height()) * self.ripple.value
            painter.drawEllipse(self.ripple_center, r, r)
            painter.restore()
        painter.setFont(self.font())
        painter.setPen(ink)
        offset = .65 * f.press.value
        if self.disclosure:
            painter.save()
            painter.translate(9, self.height() / 2)
            painter.rotate(90 * self.disclosure_progress)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(ink, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath(QPointF(-2, -3))
            path.lineTo(1, 0)
            path.lineTo(-2, 3)
            painter.drawPath(path)
            painter.restore()
            painter.drawText(rect.adjusted(23, offset, -8, offset), Qt.AlignLeft | Qt.AlignVCenter, self.text())
        else:
            icon_size = self.iconSize()
            has_icon = not self.icon().isNull()
            gap = 6 if has_icon and self.text() else 0
            text_width = self.fontMetrics().horizontalAdvance(self.text())
            total = text_width + (icon_size.width() if has_icon else 0) + gap
            x = (self.width() - total) / 2
            if has_icon:
                mode = QIcon.Normal if self.isEnabled() else QIcon.Disabled
                pixmap = self.icon().pixmap(icon_size, mode)
                painter.drawPixmap(QRectF(x, (self.height() - icon_size.height()) / 2 + offset,
                                          icon_size.width(), icon_size.height()), pixmap, QRectF(pixmap.rect()))
                x += icon_size.width() + gap
            painter.drawText(QRectF(x, offset, text_width + 1, self.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, self.text())


class MotionCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.feedback = InteractionMotion(self)
        self.check = MotionValue(self, self.isChecked(), lambda _: self.update())
        self.toggled.connect(lambda checked: self.check.to(float(checked), 170, self.isVisible()))
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        f = self.feedback
        rect = QRectF(1, (self.height() - 16) / 2, 16, 16)
        fill = mix("#111111", "#246bce", self.check.value)
        border = mix("#484848", "#438bea", self.check.value)
        border = mix(border, "#9fbce3", max(f.hover.value, f.focus.value))
        painter.setBrush(mix("#202020", fill, f.enabled.value))
        painter.setPen(QPen(mix("#353535", border, f.enabled.value), 1))
        painter.drawRoundedRect(rect, 4, 4)
        if self.check.value > .001:
            painter.save()
            painter.setClipRect(rect.adjusted(0, 0, -16 * (1 - self.check.value), 0))
            painter.setPen(QPen(QColor(255, 255, 255, round(255 * f.enabled.value)), 1.5,
                                Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath(QPointF(rect.left() + 4, rect.top() + 8))
            path.lineTo(rect.left() + 7, rect.top() + 11)
            path.lineTo(rect.left() + 12, rect.top() + 5)
            painter.drawPath(path)
            painter.restore()
        painter.setPen(mix("#777777", "#eeeeee" if f.focus.value else "#dddddd", f.enabled.value))
        painter.setFont(self.font())
        painter.drawText(QRectF(27, 0, max(0, self.width() - 27), self.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, self.text())


class MotionLineEdit(QLineEdit):
    def __init__(self, *args):
        super().__init__(*args)
        self.feedback = InteractionMotion(self)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = mix("#2c2c2c", "#444444", self.feedback.hover.value)
        color = mix(color, "#9fbce3", self.feedback.focus.value)
        if self.property("invalid"):
            color = QColor("#a64a50")
        painter.setPen(QPen(color, 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.6, .6, -.6, -.6), 5, 5)


class MotionTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.hovers = {}
        self.indicator = QRectF()
        self.slide = QVariantAnimation(self)
        self.slide.setDuration(180)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.slide.valueChanged.connect(self._move)
        self.currentChanged.connect(self._select)

    def _rect(self, index):
        return QRectF(self.tabRect(index)).adjusted(0, 0, -5, -16)

    def _move(self, rect):
        self.indicator = rect
        self.update()

    def _select(self, index):
        self.slide.stop()
        if index < 0:
            return
        target = self._rect(index)
        if not self.isVisible() or not motion_enabled() or self.indicator.isEmpty():
            self._move(target)
        else:
            self.slide.setStartValue(self.indicator)
            self.slide.setEndValue(target)
            self.slide.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.slide.stop()
        if self.currentIndex() >= 0:
            self._move(self._rect(self.currentIndex()))

    def mouseMoveEvent(self, event):
        hovered = self.tabAt(event.position().toPoint())
        for index in range(self.count()):
            if index not in self.hovers:
                self.hovers[index] = MotionValue(self, 0, lambda _: self.update())
            value = self.hovers[index]
            target = float(index == hovered)
            if (value.animation.endValue() if value.animation.state() == QVariantAnimation.Running else value.value) != target:
                value.to(target, 130)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        for value in self.hovers.values():
            value.to(0, 130)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self.slide.stop()
        if self.currentIndex() >= 0:
            self._move(self._rect(self.currentIndex()))
        for value in self.hovers.values():
            value.snap(0)
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for index in range(self.count()):
            hover = self.hovers[index].value if index in self.hovers else 0
            painter.setBrush(mix("#141414", "#242424", hover))
            painter.setPen(QPen(QColor("#2c2c2c"), 1))
            painter.drawRoundedRect(self._rect(index).adjusted(.5, .5, -.5, -.5), 6, 6)
        if self.currentIndex() >= 0:
            if self.indicator.isEmpty():
                self.indicator = self._rect(self.currentIndex())
            painter.setBrush(QColor("#303030"))
            painter.setPen(QPen(QColor("#3c3c3c"), 1))
            painter.drawRoundedRect(self.indicator.adjusted(.5, .5, -.5, -.5), 6, 6)
        painter.setFont(self.font())
        for index in range(self.count()):
            hover = self.hovers[index].value if index in self.hovers else 0
            painter.setPen(QColor("#eeeeee") if index == self.currentIndex() else mix("#999999", "#eeeeee", hover))
            painter.drawText(self._rect(index), Qt.AlignCenter, self.tabText(index))
        if self.hasFocus() and self.currentIndex() >= 0:
            painter.setPen(QPen(QColor("#9fbce3"), 1.5, Qt.SolidLine, Qt.RoundCap))
            rect = self._rect(self.currentIndex())
            painter.drawLine(QPointF(rect.center().x() - 12, rect.bottom() - 4),
                             QPointF(rect.center().x() + 12, rect.bottom() - 4))


class MotionScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scroll = QVariantAnimation(self)
        self.scroll.setEasingCurve(QEasingCurve.OutCubic)
        self.scroll.setDuration(140)
        self.scroll.valueChanged.connect(lambda value: self.verticalScrollBar().setValue(round(value)))
        self.verticalScrollBar().sliderPressed.connect(self.scroll.stop)
        self.verticalScrollBar().actionTriggered.connect(lambda _: self.scroll.stop())
        self.verticalScrollBar().rangeChanged.connect(lambda *_: self.scroll.stop())

    def wheelEvent(self, event):
        if not motion_enabled() or not event.pixelDelta().isNull() or event.modifiers() != Qt.NoModifier:
            self.scroll.stop()
            return super().wheelEvent(event)
        delta = event.angleDelta().y()
        bar = self.verticalScrollBar()
        if not delta or bar.maximum() == bar.minimum():
            return super().wheelEvent(event)
        target = float(self.scroll.endValue()) if self.scroll.state() == QVariantAnimation.Running else bar.value()
        target -= delta / 120 * max(1, QApplication.wheelScrollLines()) * bar.singleStep()
        target = max(bar.minimum(), min(bar.maximum(), target))
        self.scroll.stop()
        self.scroll.setStartValue(float(bar.value()))
        self.scroll.setEndValue(float(target))
        self.scroll.start()
        event.accept()

    def hideEvent(self, event):
        self.scroll.stop()
        super().hideEvent(event)


class ContentFade(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        self.effect = QGraphicsOpacityEffect(widget)
        self.effect.setOpacity(1)
        widget.setGraphicsEffect(self.effect)
        self.value = MotionValue(self, 1, self.effect.setOpacity)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Hide:
            self.value.snap(1)
        return False

    def reveal(self):
        if self.widget.isVisible() and motion_enabled():
            self.value.snap(.72)
            self.value.to(1, 170)
        else:
            self.value.snap(1)


class MotionLabel(QLabel):
    def __init__(self, *args):
        super().__init__(*args)
        self.fade = ContentFade(self)

    def setText(self, text):
        if self.text() == text:
            return
        super().setText(text)
        if hasattr(self, "fade"):
            self.fade.reveal()
