"""Vela-inspired controls in the existing three-tab settings layout."""
import copy
import ntpath
import subprocess
import sys
import ctypes
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QSize, QPointF, QVariantAnimation, QLocale
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QIntValidator, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QTabWidget, QScrollArea, QColorDialog,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox)
from PySide6.QtWidgets import QLayout
from hud import ROOT, load_config
from game_visibility import GameDetector
from hud_control import HudControl
from settings_store import PALETTE, digest, write_config
from font_support import DEFAULT_FONT, PrivateFont, font_family
from ui_motion import (MotionButton, MotionCheckBox, MotionLineEdit, MotionTabBar,
                       MotionScrollArea, MotionLabel, ContentFade, MotionValue, RevealViewport, motion_enabled)

STYLE = """
QWidget { color: #dddddd; font-size: 13px; background: transparent; }
QLabel#heading { color: #f2f2f2; font-size: 22px; font-weight: 600; }
QLabel#secondary { color: #909090; font-size: 12px; }
QLabel#message { color: #aaaaaa; font-size: 12px; }
QLabel#message[error="true"] { color: #efaaaa; }
QPushButton { background: #333333; border: 1px solid #373737; border-radius: 7px;
    min-height: 32px; padding: 0 12px; color: #dddddd; }
QPushButton:hover { background: #3b3b3b; border-color: #4a4a4a; }
QPushButton:pressed { background: #242424; border-color: #242424; }
QPushButton:focus { border-color: #9fbce3; }
QPushButton:disabled { background: #252525; color: #777777; border-color: #303030; }
QPushButton#primary { background: #246bce; border-color: #347cde; color: white; }
QPushButton#primary:hover { background: #307bdf; border-color: #438bea; }
QPushButton#primary:pressed { background: #1855ac; }
QPushButton#primary:disabled { background: #202b3a; border-color: #293b54; color: #7f91ab; }
QPushButton#sectionHeader { background: transparent; border: 1px solid transparent;
    border-radius: 4px; color: #bdbdbd; font-weight: 600; text-align: left;
    min-height: 28px; padding: 0; }
QPushButton#sectionHeader:hover { background: rgba(255, 255, 255, 8); color: #eeeeee; }
QPushButton#sectionHeader:focus { border-color: #9fbce3; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { background: #141414; color: #999999; border: 1px solid #2c2c2c;
    border-radius: 6px; padding: 8px 20px; margin-right: 5px; margin-bottom: 16px; }
QTabBar::tab:selected { color: #eeeeee; background: #303030; border-color: #3c3c3c; }
QTabBar::tab:hover { color: #eeeeee; background: #242424; }
QLineEdit { background: #111111; border: 1px solid #2c2c2c; border-radius: 5px;
    min-height: 30px; padding: 0 8px; selection-background-color: #246bce; }
QLineEdit:hover { border-color: #444444; }
QLineEdit:focus { border-color: #9fbce3; }
QLineEdit[invalid="true"] { background: #28181a; border-color: #a64a50; color: #f2f2f2; }
QPushButton#step { background: #191919; border-color: #2c2c2c; min-width: 26px;
    max-width: 26px; padding: 0; font-size: 16px; }
QPushButton#step:hover { background: #292929; }
QCheckBox { spacing: 10px; min-height: 28px; }
QCheckBox::indicator { width: 16px; height: 16px; background: #111111;
    border: 1px solid #484848; border-radius: 4px; }
QCheckBox::indicator:checked { background: #246bce; border-color: #438bea; image: url('@CHECK@'); }
QCheckBox::indicator:hover { border-color: #9fbce3; }
QCheckBox:focus { color: white; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #3c3c3c; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTreeWidget { background: #111111; alternate-background-color: #151515;
    border: 1px solid #2c2c2c; border-radius: 5px; outline: none; }
QTreeWidget::item { padding: 8px 5px; border-bottom: 1px solid #202020; }
QTreeWidget::item:selected { background: #203858; color: #eeeeee; }
QHeaderView::section { background: #191919; color: #909090; border: none;
    border-bottom: 1px solid #303030; padding: 9px 7px; font-size: 12px; }
QToolTip { background: #202020; color: #dddddd; border: 1px solid #404040; padding: 6px; }
QMessageBox, QColorDialog, QFileDialog { background: #151515; }
"""
STYLE = STYLE.replace("@CHECK@", (ROOT / "assets/check.svg").as_posix())
PERCENT_FIELDS = ("opacity", "blur_opacity", "border_opacity", "shadow_opacity")


def step_icon(plus=False):
    pixmap = QPixmap(32, 32)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#dddddd"), 1.3, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(4, 8, 12, 8)
    if plus:
        painter.drawLine(8, 4, 8, 12)
    painter.end()
    return QIcon(pixmap)


class CollapsibleSection(QWidget):
    """An inline disclosure heading; collapse never changes settings values."""
    def __init__(self, title):
        super().__init__()
        self.title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        self.header = MotionButton(title)
        self.header.disclosure = True
        self.header.setObjectName("sectionHeader")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setAutoDefault(False)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setAccessibleName(title + " section")
        self.clip = RevealViewport()
        self.content = self.clip.content
        layout.addWidget(self.header)
        layout.addWidget(self.clip)
        self.reveal = MotionValue(self, 1, self.paint_reveal)
        self.reveal.animation.finished.connect(self.finish_reveal)
        self.header.toggled.connect(self.update_expanded)
        self.update_expanded(True)

    def update_expanded(self, expanded):
        action = ("Collapse " if expanded else "Expand ") + self.title + " section"
        self.header.setToolTip(action)
        self.header.setAccessibleDescription(("Expanded. " if expanded else "Collapsed. ") + action)
        if expanded:
            self.clip.show()
            self.content.show()
        animated = self.isVisible() and motion_enabled()
        self.reveal.to(float(expanded), max(60, round(220 * abs(float(expanded) - self.reveal.value))), animated)
        if not animated or self.reveal.animation.state() != QVariantAnimation.Running:
            self.finish_reveal()

    def paint_reveal(self, progress):
        natural = max(0, self.content.layout().sizeHint().height()) if self.content.layout() else 0
        self.clip.setMaximumHeight(round(natural * progress))
        self.clip.layout_content()
        self.layout().setSpacing(round(8 * progress))
        self.header.disclosure_progress = progress
        self.header.update()

    def finish_reveal(self):
        expanded = self.header.isChecked()
        self.content.setVisible(expanded)
        self.clip.setVisible(expanded)
        self.clip.setMaximumHeight(16777215 if expanded else 0)
        self.clip.updateGeometry()
        self.layout().setSpacing(8 if expanded else 0)

    def set_expanded(self, expanded, animated=True):
        self.header.setChecked(expanded)
        if not animated:
            self.reveal.snap(float(expanded))
            self.finish_reveal()


class NumberEdit(QWidget):
    changed = Signal()

    def __init__(self, caption, minimum, maximum, step=1):
        super().__init__()
        self.minimum, self.maximum = minimum, maximum
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        minus, plus = MotionButton(), MotionButton()
        minus.setIcon(step_icon())
        plus.setIcon(step_icon(True))
        self.edit = MotionLineEdit()
        self.edit.setAlignment(Qt.AlignCenter)
        self.edit.setFixedWidth(64)
        self.edit.setAccessibleName(caption)
        self.edit.setValidator(QIntValidator(minimum, maximum, self))
        for button, title in ((minus, "Decrease"), (plus, "Increase")):
            button.setObjectName("step")
            button.setAccessibleName(title + ": " + caption)
            button.setToolTip(title + ": " + caption)
        for widget in (minus, self.edit, plus):
            layout.addWidget(widget)
        self.setFixedWidth(130)
        minus.clicked.connect(lambda: self.nudge(-step))
        plus.clicked.connect(lambda: self.nudge(step))
        self.edit.textChanged.connect(self.edited)

    def edited(self):
        self.edit.setProperty("invalid", False)
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)
        self.changed.emit()

    def nudge(self, delta):
        try:
            value = int(self.edit.text())
        except ValueError:
            value = self.minimum
        self.edit.setText(str(max(self.minimum, min(self.maximum, value + delta))))

    def set_value(self, value):
        self.edit.setText(str(value))

    def value(self):
        try:
            value = int(self.edit.text())
            if not self.minimum <= value <= self.maximum:
                raise ValueError
            return value
        except ValueError:
            parent = self.parentWidget()
            while parent is not None:
                if isinstance(parent, CollapsibleSection):
                    parent.set_expanded(True, animated=False)
                parent = parent.parentWidget()
            self.edit.setProperty("invalid", True)
            self.edit.style().unpolish(self.edit)
            self.edit.style().polish(self.edit)
            self.edit.setFocus()
            raise ValueError(f"{self.edit.accessibleName()}: enter a value between {self.minimum} and {self.maximum}.")

    def wheelEvent(self, event):
        event.ignore()


class SaveButton(MotionButton):
    """Paint-only, slow availability feedback; geometry never animates."""
    def __init__(self, title):
        super().__init__(title)
        self.progress = 0.0
        self.glow = QVariantAnimation(self)
        self.glow.setDuration(2400)
        self.glow.setLoopCount(-1)
        self.glow.setStartValue(0.0)
        self.glow.setKeyValueAt(.5, 1.0)
        self.glow.setEndValue(0.0)
        self.glow.valueChanged.connect(self.animate)

    def animate(self, progress):
        self.progress = progress
        self.update()

    def set_dirty(self, dirty):
        self.setEnabled(dirty)
        if dirty and self.isVisible() and motion_enabled() and self.glow.state() != QVariantAnimation.Running:
            self.glow.start()
        elif not dirty:
            self.glow.stop()
            self.progress = 0
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isEnabled():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(159, 188, 227, round(25 + 60 * self.progress)), 1))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.7, .7, -.7, -.7), 7, 7)

    def hideEvent(self, event):
        self.glow.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.isEnabled() and motion_enabled():
            self.glow.start()


class SettingsApp(QWidget):
    def __init__(self):
        super().__init__()
        if not getattr(QApplication.instance(), "_hud_fonts_loaded", False):
            for filename in ("NotoSans-Regular.ttf", "NotoSans-SemiBold.ttf"):
                QFontDatabase.addApplicationFont(str(ROOT / "assets/fonts" / filename))
            QApplication.instance()._hud_fonts_loaded = True
        self.control = HudControl(ROOT)
        self.values, self.colors, self.swatches = {}, {}, {}
        self.sections = {}
        self.page_fades = []
        self.manual_games = []
        self.font_file = ""
        self.loading = True
        self.loaded = self.loaded_digest = self.snapshot = None
        self.setWindowTitle("AMD HUD — Settings")
        self.setWindowIcon(QIcon(str(ROOT / "assets/app-icon.ico")))
        self.resize(720, 720)
        self.setMinimumSize(700, 700)
        self.setStyleSheet(STYLE)
        self.setFont(QFont("Noto Sans" if "Noto Sans" in QFontDatabase.families() else "Segoe UI"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        heading = QLabel("AMD HUD")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        layout.addWidget(self.note("Overlay appearance and behavior"))
        layout.addSpacing(8)
        self.tabs = QTabWidget()
        self.tabs.setTabBar(MotionTabBar(self.tabs))
        layout.addWidget(self.tabs, 1)
        self.appearance, self.behavior, self.games = [self.tab(title) for title in ("Appearance", "Behavior", "Games")]
        self.build_appearance()
        self.build_behavior()
        self.build_games()
        self.tabs.currentChanged.connect(lambda index: self.page_fades[index].reveal())
        self.message = MotionLabel()
        self.message.setObjectName("message")
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(34)
        layout.addWidget(self.message)
        self.running_text = MotionLabel("")
        self.running_text.setObjectName("secondary")
        self.running_text.setWordWrap(True)
        layout.addWidget(self.running_text)
        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.start_button = self.button("Start HUD", self.start)
        self.stop_button = self.button("Stop", self.stop)
        self.preview_button = self.button("Preview 10 s", self.preview)
        for button in (self.start_button, self.stop_button, self.preview_button):
            actions.addWidget(button)
        actions.addStretch(1)
        self.load_button = self.button("Reload saved", self.load)
        self.save_button = SaveButton("Save and apply")
        self.save_button.setAccessibleName("Save and apply")
        self.save_button.clicked.connect(self.save)
        self.save_button.setObjectName("primary")
        self.save_button.setShortcut("Ctrl+S")
        actions.addWidget(self.load_button)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.load()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_status)
        self.timer.start(750)
        self.poll_status()

    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QRadialGradient(QPointF(self.width() * .5, self.height() * .35), max(self.width(), self.height()))
        gradient.setColorAt(0, QColor("#121212"))
        gradient.setColorAt(1, QColor("#090909"))
        painter.fillRect(self.rect(), gradient)

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and QApplication.platformName() == "windows":
            dark = ctypes.c_int(1)
            ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(ctypes.c_void_p(int(self.winId())),
                                                        20, ctypes.byref(dark), ctypes.sizeof(dark))

    def button(self, title, handler):
        button = MotionButton(title)
        button.setAccessibleName(title)
        button.clicked.connect(handler)
        return button

    def tab(self, caption):
        scroll = MotionScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        self.page_fades.append(ContentFade(scroll.viewport()))
        self.tabs.addTab(scroll, caption)
        return content

    def note(self, text):
        label = QLabel(text)
        label.setObjectName("secondary")
        label.setWordWrap(True)
        return label

    def number(self, grid, row, caption, key, minimum, maximum, step=1):
        label = QLabel(caption)
        number = NumberEdit(caption, minimum, maximum, step)
        label.setBuddy(number.edit)
        grid.addWidget(label, row, 0)
        grid.addWidget(number, row, 1, Qt.AlignLeft)
        number.changed.connect(self.update_dirty)
        self.values[key] = number

    def checkbox(self, grid, row, caption, key):
        checkbox = MotionCheckBox(caption)
        checkbox.setAccessibleName(caption)
        checkbox.toggled.connect(self.update_dirty)
        grid.addWidget(checkbox, row, 0, 1, 3)
        self.values[key] = checkbox

    def form(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 6, 16, 16)
        layout.setSpacing(14)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(0, 210)
        grid.setColumnStretch(2, 1)
        return layout, grid

    def build_appearance(self):
        layout, grid = self.form(self.appearance)
        self.checkbox(grid, 0, "Background blur (Acrylic)", "blur")
        self.number(grid, 1, "Blurred background opacity (%)", "blur_opacity", 20, 100)
        self.number(grid, 2, "Plain background opacity (%)", "opacity", 20, 100)
        self.number(grid, 3, "Text size", "font_size", 8, 48)
        self.number(grid, 4, "Corner radius (px)", "corner_radius", 0, 100)
        font_row = QHBoxLayout()
        font_row.setSpacing(6)
        self.font_display = MotionLineEdit()
        self.font_display.setReadOnly(True)
        self.font_display.setAccessibleName("HUD font")
        self.font_display.setMinimumWidth(70)
        self.font_choose = self.button("Choose font…", self.choose_font)
        self.font_reset = self.button("Reset to default", self.reset_font)
        font_row.addWidget(self.font_display, 1)
        font_row.addWidget(self.font_choose)
        font_row.addWidget(self.font_reset)
        grid.addWidget(QLabel("Font"), 5, 0)
        grid.addLayout(font_row, 5, 1, 1, 2)
        self.checkbox(grid, 6, "Show frametime graph", "frametime_graph")
        self.number(grid, 7, "Graph height (px)", "frametime_graph_height", 24, 160)
        graph_color = self.button("Choose color…", lambda: self.choose_color("frametime_color"))
        grid.addWidget(QLabel("Graph color"), 8, 0)
        grid.addWidget(graph_color, 8, 1, Qt.AlignLeft)
        self.swatches.setdefault("frametime_color", []).append(graph_color)
        layout.addLayout(grid)
        colors = QGridLayout()
        colors.setSpacing(8)
        names = [("Background", "background_color"), ("Text", "text_color"), ("Border", "border_color"),
                 ("Unavailable data", "muted_color"), ("GPU", "row_0"), ("CPU", "row_1"),
                 ("RAM", "row_2"), ("FPS / API", "row_3")]
        for index, (caption, key) in enumerate(names):
            button = self.button(caption, lambda checked=False, k=key: self.choose_color(k))
            button.setIconSize(QSize(12, 12))
            colors.addWidget(button, index // 4, index % 4)
            self.swatches.setdefault(key, []).append(button)
        layout.addLayout(colors)
        layout.addWidget(self.button("Restore Rosé Pine colors", self.restore_palette), 0, Qt.AlignLeft)
        layout.addWidget(self.note("Blur uses 8 px system corners. Fully opaque backgrounds use the custom corner radius."))
        for heading, entries, color_key in (
            ("Border", [("border_enabled", "Enable border", None),
                       ("border_width", "Border width (px)", (0, 8)),
                       ("border_opacity", "Border opacity (%)", (0, 100))], "border_color"),
            ("Shadow", [("shadow_enabled", "Enable shadow", None),
                      ("shadow_x", "Shadow X offset (px)", (-100, 100)),
                      ("shadow_y", "Shadow Y offset (px)", (-100, 100)),
                      ("shadow_opacity", "Shadow opacity (%)", (0, 100)),
                      ("shadow_blur", "Shadow blur (px)", (0, 64))], "shadow_color")):
            section = CollapsibleSection(heading)
            self.sections[heading.lower()] = section
            layout.addWidget(section)
            grid = QGridLayout(section.content)
            grid.setSizeConstraint(QLayout.SetNoConstraint)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)
            grid.setColumnMinimumWidth(0, 210)
            grid.setColumnStretch(2, 1)
            for row, (key, caption, bounds) in enumerate(entries):
                if bounds is None:
                    self.checkbox(grid, row, caption, key)
                else:
                    self.number(grid, row, caption, key, *bounds)
            label = QLabel("Border color" if heading == "Border" else "Shadow color")
            color_button = self.button("Choose color…", lambda checked=False, k=color_key: self.choose_color(k))
            grid.addWidget(label, len(entries), 0)
            grid.addWidget(color_button, len(entries), 1, Qt.AlignLeft)
            self.swatches.setdefault(color_key, []).append(color_button)
        self.values["shadow_enabled"].toggled.connect(self.synchronize_effects)
        self.values["border_enabled"].toggled.connect(self.synchronize_effects)
        layout.addStretch(1)

    def synchronize_effects(self):
        for prefix, keys in (("border", ("border_width", "border_opacity")),
                             ("shadow", ("shadow_x", "shadow_y", "shadow_opacity", "shadow_blur"))):
            enabled = self.values[prefix + "_enabled"].isChecked()
            for key in keys:
                self.values[key].setEnabled(enabled)
            for button in self.swatches.get(prefix + "_color", []):
                button.setEnabled(enabled)

    def build_behavior(self):
        layout, grid = self.form(self.behavior)
        self.number(grid, 0, "X position (px)", "x", -20000, 20000)
        self.number(grid, 1, "Y position (px)", "y", -20000, 20000)
        self.number(grid, 2, "Metrics refresh interval (ms)", "refresh_ms", 250, 10000, 250)
        self.number(grid, 3, "GPU index", "gpu_index", 0, 15)
        self.checkbox(grid, 4, "Show only over the active game", "games_only")
        self.checkbox(grid, 5, "Pass clicks through to the game", "click_through")
        layout.addLayout(grid)
        layout.addWidget(self.note("Ctrl+Alt+F10 — toggle visibility\nCtrl+Alt+F11 — close HUD\n\n"
                                  "The preview shows the saved HUD for 10 seconds, including outside games.\n"
                                  "Closing this window does not stop the HUD."))
        layout.addStretch(1)

    def build_games(self):
        layout = QVBoxLayout(self.games)
        layout.setContentsMargins(16, 6, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self.note("Games from AMD profiles and manually added games"))
        self.game_list = QTreeWidget()
        self.game_list.setAccessibleName("Games recognized by the HUD")
        self.game_list.setHeaderLabels(["Game", "Source", "Executable"])
        self.game_list.setRootIsDecorated(False)
        self.game_list.setAlternatingRowColors(True)
        self.game_list.setTextElideMode(Qt.ElideMiddle)
        self.game_list.setColumnWidth(0, 195)
        self.game_list.setColumnWidth(1, 75)
        self.game_list.header().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.game_list, 1)
        actions = QHBoxLayout()
        actions.addWidget(self.button("Add game…", self.add_game))
        self.remove_button = self.button("Remove manual entry", self.remove_game)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.game_list.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.note("Choose the actual game executable. AMD profiles are detected automatically."))

    def say(self, text, error=False):
        self.message.setText(text)
        self.message.setProperty("error", error)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)

    def show_colors(self):
        for key, buttons in self.swatches.items():
            color = self.colors[key]
            pixmap = QPixmap(12, 12)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor("#707070"), .7))
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(.5, .5, 11, 11), 3, 3)
            painter.end()
            for button in buttons:
                button.setIcon(QIcon(pixmap))
                button.setToolTip(color.upper())

    def choose_color(self, key):
        color = QColorDialog.getColor(QColor(self.colors[key]), self, "HUD color", QColorDialog.DontUseNativeDialog)
        if color.isValid():
            self.colors[key] = color.name()
            self.show_colors()
            self.update_dirty()

    def restore_palette(self):
        self.colors = {key: value for key, value in PALETTE.items() if key != "row_colors"}
        self.colors.update({"row_" + str(i): value for i, value in enumerate(PALETTE["row_colors"])})
        self.show_colors()
        self.update_dirty()

    def update_font_display(self):
        if not self.font_file:
            self.font_display.setText("Default (" + DEFAULT_FONT + ")")
            self.font_display.setToolTip("Built-in default font. Text size is configured separately.")
        else:
            try:
                self.font_display.setText(font_family(self.font_file))
                self.font_display.setToolTip(self.font_file)
            except (OSError, ValueError):
                self.font_display.setText("Unavailable font")
                self.font_display.setToolTip(self.font_file + "\nThe HUD will use Consolas until this file is available.")
        self.font_reset.setEnabled(bool(self.font_file))

    def choose_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a HUD font", "", "Font files (*.ttf *.otf)",
                                             options=QFileDialog.DontUseNativeDialog)
        if not path:
            return
        try:
            font = PrivateFont(path)
            try:
                self.font_file = font.path
            finally:
                font.close()
            self.update_font_display()
            self.update_dirty()
        except (OSError, ValueError) as exc:
            self.say("Could not load font: " + str(exc), True)

    def reset_font(self):
        self.font_file = ""
        self.update_font_display()
        self.update_dirty()

    def load(self):
        try:
            before = digest()
            config = load_config()
            if digest() != before:
                raise RuntimeError("The settings file is being changed. Try reloading it.")
            self.loading = True
            self.loaded, self.loaded_digest = config, before
            for key, widget in self.values.items():
                value = config.get(key, True if key == "blur" else .88)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(value)
                else:
                    widget.set_value(round(value * 100) if key in PERCENT_FIELDS else value)
            self.colors = {key: config.get(key, value) for key, value in PALETTE.items() if key != "row_colors"}
            self.colors.update({"row_" + str(i): value for i, value in enumerate(config.get("row_colors", PALETTE["row_colors"]))})
            self.manual_games = list(config["game_executables"])
            self.font_file = config.get("font_file", "")
            self.update_font_display()
            self.show_colors()
            self.synchronize_effects()
            self.populate_games()
            self.snapshot = self.collect()
            self.say("All changes saved.")
        except Exception as exc:
            self.say("Could not load settings: " + str(exc), True)
        finally:
            self.loading = False
            self.update_dirty()

    def populate_games(self):
        config = copy.deepcopy(self.loaded)
        config["game_executables"] = []
        detector = GameDetector(config)
        self.game_list.clear()
        for path, title in detector.games.items():
            item = QTreeWidgetItem([title, "AMD", path])
            item.setToolTip(0, title)
            item.setToolTip(2, path)
            self.game_list.addTopLevelItem(item)
        for index, path in enumerate(self.manual_games):
            item = QTreeWidgetItem([ntpath.basename(path), "Manual", path])
            item.setData(0, Qt.UserRole, index)
            item.setToolTip(2, path)
            self.game_list.addTopLevelItem(item)
        self.selection_changed()

    def selection_changed(self):
        selected = self.game_list.selectedItems()
        removable = bool(selected and selected[0].data(0, Qt.UserRole) is not None)
        self.remove_button.setEnabled(removable)
        self.remove_button.setToolTip("Remove an entry added in this window" if removable else "Select a manually added game. AMD profiles are not modified.")

    def add_game(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a game executable", "", "Game executable (*.exe)",
                                             options=QFileDialog.DontUseNativeDialog)
        if path and ntpath.normcase(path) not in [ntpath.normcase(p) for p in self.manual_games]:
            self.manual_games.append(path)
            self.populate_games()
            self.update_dirty()

    def remove_game(self):
        selected = self.game_list.selectedItems()
        if selected and (index := selected[0].data(0, Qt.UserRole)) is not None:
            self.manual_games.pop(index)
            self.populate_games()
            self.update_dirty()

    def collect(self, validate=True):
        config = copy.deepcopy(self.loaded)
        for key, widget in self.values.items():
            if isinstance(widget, QCheckBox):
                config[key] = widget.isChecked()
            else:
                number = widget.value() if validate else widget.edit.text()
                if not validate:
                    try:
                        number = int(number)
                    except ValueError:
                        config[key] = number
                        continue
                config[key] = number / 100 if key in PERCENT_FIELDS else number
        config.update({key: self.colors[key] for key in PALETTE if key != "row_colors"})
        config["row_colors"] = [self.colors["row_" + str(i)] for i in range(4)]
        config["game_executables"] = self.manual_games[:]
        config["font_file"] = self.font_file
        return config

    def is_dirty(self):
        return self.loaded is not None and self.collect(validate=False) != self.snapshot

    def update_dirty(self):
        if self.loading or self.loaded is None:
            return
        dirty = self.is_dirty()
        self.save_button.set_dirty(dirty)
        self.save_button.setToolTip("Save changes and reload the HUD (Ctrl+S)" if dirty else "No unsaved changes")
        self.setWindowTitle("AMD HUD — Settings" + (" •" if dirty else ""))
        if not self.message.property("error"):
            self.say("You have unsaved changes. Apply them when ready." if dirty else "All changes saved.")

    def save(self):
        try:
            config = self.collect()
            write_config(config, expected_digest=self.loaded_digest)
            self.loaded, self.snapshot = copy.deepcopy(config), copy.deepcopy(config)
            self.loaded_digest = digest()
            if self.control.running():
                self.control.send("reload")
            self.say("Saved and applied." if self.control.running() else "Saved. These settings will be used the next time the HUD starts.")
            self.update_dirty()
            return True
        except Exception as exc:
            self.say("Could not save: " + str(exc), True)
            return False

    def start(self):
        if self.control.running():
            return
        self.control.reset()
        try:
            with (ROOT / "hud-output.log").open("w") as stdout, (ROOT / "hud-error.log").open("w") as stderr:
                subprocess.Popen([sys.executable, str(ROOT / "hud.py")], cwd=ROOT, stdout=stdout, stderr=stderr,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            self.say("Starting the saved HUD…")
        except OSError as exc:
            self.say("Could not start the HUD: " + str(exc), True)

    def stop(self):
        if self.control.running():
            self.control.send("stop")
            self.say("Stopping the HUD…")

    def preview(self):
        if self.control.running():
            self.control.send("preview")
            self.say("Previewing the saved configuration for 10 seconds. Unsaved changes remain in the editor.")

    def poll_status(self):
        running = self.control.running()
        self.running_text.setText("HUD is running" if running else "HUD is stopped")
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.preview_button.setEnabled(running)
        self.start_button.setToolTip("Start with the saved configuration")
        self.stop_button.setToolTip("Stop the HUD and keep settings open")
        self.preview_button.setToolTip("Show the saved HUD for 10 seconds" if running else "Start the HUD first")

    def closeEvent(self, event):
        if self.is_dirty():
            box = QMessageBox(self)
            box.setWindowTitle("Unsaved changes")
            box.setText("Save your changes to the HUD settings?")
            save = box.addButton("Save", QMessageBox.AcceptRole)
            discard = box.addButton("Discard", QMessageBox.DestructiveRole)
            cancel = box.addButton("Cancel", QMessageBox.RejectRole)
            box.setDefaultButton(cancel)
            box.exec()
            if box.clickedButton() == cancel or box.clickedButton() not in (save, discard):
                event.ignore()
                return
            if box.clickedButton() == save and not self.save():
                event.ignore()
                return
        self.timer.stop()
        self.control.close()
        event.accept()


def main():
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ROOT / "assets/app-icon.ico")))
    app.setStyle("Fusion")
    window = SettingsApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
