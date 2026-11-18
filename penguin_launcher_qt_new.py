#!/usr/bin/env python3
"""
Penguin Launcher (PyQt6) - Lunar-style interface.

Requirements:  pip install PyQt6   (and on Linux: sudo apt install libxcb-cursor0)
               a JDK/JRE, e.g. openjdk-21-jre
Keep this file next to penguin_core.py (the backend), then run:
               python3 penguin_launcher_qt.py
"""
import hashlib
import re
import shutil
import subprocess
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QObject, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QRadialGradient)
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                             QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QScrollArea, QSlider, QStackedWidget, QToolButton,
                             QVBoxLayout, QWidget)

import penguin_core as core

try:
    import penguin_updater as updater   # optional: auto-update support
except ImportError:
    updater = None

# Versions offered in "Add version". Taken from penguin_core.ALLOWED_VERSIONS when present
# (edit it there), with this built-in list as a fallback so a mismatched core file can't crash the GUI.
ALLOWED_VERSIONS = getattr(core, "ALLOWED_VERSIONS", [
    "1.21.1", "1.21.3", "1.21.4", "1.21.5", "1.21.6", "1.21.7",
    "1.21.8", "1.21.10", "1.21.11", "26.1.2", "26.2", "26.3",
])

BLUE, VIOLET = "#3b82ff", "#8b5cf6"
GRADIENT = f"qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {BLUE}, stop:1 {VIOLET})"
GRADIENT_HOVER = "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5a98ff, stop:1 #a078ff)"

QSS = f"""
* {{ font-size: 13px; color: #e8ebf5; }}
QMainWindow, QDialog, QWidget#root, QWidget#page {{ background: #0a0c12; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ---- top bar ---- */
QFrame#topbar {{ background: #0d1019; border: none; border-bottom: 1px solid #1b2030; }}
QLabel#logo {{ font-size: 17px; font-weight: 800; }}
QPushButton#tab {{ background: transparent; border: none; border-bottom: 2px solid transparent;
                   color: #8b93a8; font-weight: 700; padding: 20px 20px 18px 20px; }}
QPushButton#tab:hover {{ color: #e8ebf5; }}
QPushButton#tab:checked {{ color: #ffffff; border-bottom: 2px solid #5b8cff; }}

/* ---- text ---- */
QLabel#h1 {{ font-size: 24px; font-weight: 800; }}
QLabel#h2 {{ font-size: 15px; font-weight: 700; }}
QLabel#muted {{ color: #7c859a; }}
QLabel#title {{ font-size: 14px; font-weight: 700; }}
QLabel#kicker {{ color: #8fa4d8; font-size: 11px; font-weight: 800; }}
QLabel#heroTitle {{ font-size: 40px; font-weight: 800; }}
QLabel#chipHero {{ background: rgba(255,255,255,18); color: #d7ddf0; border-radius: 12px;
                   padding: 4px 13px; font-weight: 600; }}
QLabel#chip {{ background: #1a2033; color: #9fb0d8; border-radius: 9px; padding: 2px 9px; font-size: 11px; }}

/* ---- buttons ---- */
QPushButton#launch {{ background: {GRADIENT}; color: white; font-size: 19px; font-weight: 800;
                      border: none; border-radius: 14px; padding: 0 52px; min-height: 62px; }}
QPushButton#launch:hover {{ background: {GRADIENT_HOVER}; }}
QPushButton#launch:disabled {{ background: #232840; color: #6b7390; }}
QPushButton#accent {{ background: {GRADIENT}; color: white; font-weight: 700; border: none;
                      border-radius: 10px; padding: 9px 20px; }}
QPushButton#accent:hover {{ background: {GRADIENT_HOVER}; }}
QPushButton#accent:disabled {{ background: #232840; color: #6b7390; }}
QPushButton#ghost {{ background: transparent; border: 1px solid #2a3150; border-radius: 10px;
                     padding: 8px 16px; font-weight: 600; }}
QPushButton#ghost:hover {{ background: #151b2e; border-color: #3a4570; }}
QPushButton#danger {{ background: transparent; border: 1px solid #5a2a31; color: #ff7b86;
                      border-radius: 10px; padding: 8px 16px; font-weight: 600; }}
QPushButton#danger:hover {{ background: #2a1519; }}
QPushButton#glassbtn {{ background: rgba(255,255,255,16); border: 1px solid rgba(255,255,255,32);
                        border-radius: 12px; padding: 0 22px; min-height: 60px; font-weight: 700; }}
QPushButton#glassbtn:hover {{ background: rgba(255,255,255,28); }}
QPushButton#glassSmall {{ background: rgba(255,255,255,16); border: 1px solid rgba(255,255,255,32);
                          border-radius: 10px; padding: 9px 16px; font-weight: 700; }}
QPushButton#glassSmall:hover {{ background: rgba(255,255,255,28); }}
QToolButton#more {{ background: rgba(255,255,255,16); border: 1px solid rgba(255,255,255,32);
                    border-radius: 12px; min-height: 60px; min-width: 52px; font-size: 20px; }}
QToolButton#more:hover {{ background: rgba(255,255,255,28); }}
QToolButton#more::menu-indicator {{ image: none; }}
QPushButton#seg {{ background: #121624; border: 1px solid #1f2540; border-radius: 8px; margin-right: 6px;
                   padding: 8px 18px; font-weight: 600; color: #9aa4bf; }}
QPushButton#seg:checked {{ background: rgba(91,140,255,40); border-color: #5b8cff; color: #8fb2ff; }}
QPushButton#console {{ background: transparent; border: none; color: #7c859a; padding: 4px 8px; }}
QPushButton#console:hover {{ color: #e8ebf5; }}

/* ---- cards ---- */
QFrame#card, QFrame#panel {{ background: #121624; border: 1px solid #1f2540; border-radius: 14px; }}
QFrame#card:hover {{ border-color: #3a4a8a; }}
QFrame#glass {{ background: rgba(255,255,255,12); border: 1px solid rgba(255,255,255,26); border-radius: 16px; }}
QFrame#tile {{ background: #121624; border: 2px solid #1f2540; border-radius: 14px; }}
QFrame#tile:hover {{ border-color: #3a4a8a; }}
QFrame#tile[selected="true"] {{ border: 2px solid #5b8cff; background: #151b32; }}
QFrame#tileAdd {{ background: transparent; border: 2px dashed #2a3150; border-radius: 14px; }}
QFrame#tileAdd:hover {{ border-color: #5b8cff; background: #11162a; }}
QFrame#hero {{ background: transparent; border: none; }}

QFrame#banner {{ background: rgba(91,140,255,34); border: 1px solid #5b8cff; border-radius: 12px; }}

/* ---- inputs ---- */
QLineEdit, QComboBox, QPlainTextEdit, QListWidget {{
    background: #121624; border: 1px solid #1f2540; border-radius: 10px; padding: 8px 11px;
    selection-background-color: {BLUE}; selection-color: white; }}
QLineEdit:focus, QComboBox:focus {{ border-color: #5b8cff; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{ background: #121624; border: 1px solid #1f2540; outline: 0;
                               selection-background-color: {BLUE}; selection-color: white; }}
QComboBox#pill {{ background: rgba(255,255,255,16); border: 1px solid rgba(255,255,255,32);
                  border-radius: 12px; padding: 0 18px; min-height: 60px; min-width: 230px;
                  font-size: 14px; font-weight: 700; }}
QComboBox#pill:hover {{ background: rgba(255,255,255,28); }}
QPlainTextEdit {{ font-family: monospace; font-size: 12px; color: #a9b3cc; }}
QListWidget::item {{ padding: 6px 4px; border-radius: 6px; }}
QListWidget::item:selected {{ background: rgba(91,140,255,45); color: #e8ebf5; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3a4570; background: #121624; }}
QCheckBox::indicator:checked {{ background: {BLUE}; border-color: {BLUE}; }}

QProgressBar {{ background: #121624; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {GRADIENT}; border-radius: 2px; }}
QSlider::groove:horizontal {{ height: 6px; background: #1f2540; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {GRADIENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; background: #ffffff; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #252c47; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #34406a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #252c47; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: #34406a; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QMenu {{ background: #121624; border: 1px solid #1f2540; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba(91,140,255,45); }}
QToolTip {{ background: #121624; color: #e8ebf5; border: 1px solid #1f2540; padding: 4px; }}
"""


# --------------------------------------------------------------------------- helpers
def fmt(n):
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def avatar(name, size=56):
    """Gradient tile with the first letter, colour derived from the name."""
    hue = int(hashlib.md5(name.encode()).hexdigest()[:4], 16) % 360
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor.fromHsv(hue, 170, 235))
    grad.setColorAt(1, QColor.fromHsv((hue + 45) % 360, 210, 150))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    p.fillPath(path, grad)
    font = QFont()
    font.setPixelSize(int(size * 0.45))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, (name[:1] or "?").upper())
    p.end()
    return pix


def rounded(pix, size, radius=12):
    pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                     Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    p.drawPixmap((size - pix.width()) // 2, (size - pix.height()) // 2, pix)
    p.end()
    return out


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w:
            w.setParent(None)
            w.deleteLater()


def button(text, kind="ghost"):
    b = QPushButton(text)
    b.setObjectName(kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def label(text, name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def open_path(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def mod_names(inst, limit=7):
    """(enabled mod count, list of short display names)."""
    mods_dir = core.game_dir(inst) / "mods"
    files = sorted(f.name for f in mods_dir.glob("*.jar")) if mods_dir.exists() else []
    names = []
    for f in files:
        base = f[:-4]
        short = re.split(r"[-_+]v?\d", base, maxsplit=1)[0] or base
        names.append(short.replace("-", " ").replace("_", " "))
    return len(files), names[:limit]


class Bridge(QObject):
    """Lets worker threads run code / log on the GUI thread."""
    call = pyqtSignal(object)
    log = pyqtSignal(str)


# --------------------------------------------------------------------------- custom widgets
class HeroFrame(QFrame):
    """Big banner with a painted gradient / glow background."""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 20, 20)
        p.setClipPath(path)

        base = QLinearGradient(r.topLeft(), r.bottomRight())
        base.setColorAt(0, QColor("#141a36"))
        base.setColorAt(1, QColor("#0b0e1a"))
        p.fillRect(r, base)

        for cx, cy, rad, col in ((0.88, 0.05, 0.60, QColor(59, 130, 255, 95)),
                                 (0.10, 1.05, 0.65, QColor(139, 92, 246, 85))):
            glow = QRadialGradient(r.width() * cx, r.height() * cy, r.width() * rad)
            clear = QColor(col)
            clear.setAlpha(0)
            glow.setColorAt(0, col)
            glow.setColorAt(1, clear)
            p.fillRect(r, glow)

        p.setPen(QPen(QColor(255, 255, 255, 20), 2))
        for x in range(14, int(r.width()), 30):
            for y in range(14, int(r.height()), 30):
                p.drawPoint(x, y)

        p.setClipping(False)
        p.setPen(QPen(QColor("#222a4a"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class TileCard(QFrame):
    def __init__(self, inst, selected, on_click):
        super().__init__()
        self.setObjectName("tile")
        self.setProperty("selected", selected)
        self.setFixedSize(176, 132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.inst, self.on_click = inst, on_click
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(4)
        icon = QLabel()
        icon.setPixmap(avatar(inst["name"], 44))
        icon.setFixedSize(44, 44)
        lay.addWidget(icon)
        lay.addSpacing(4)
        name = inst["name"]
        title = label(self.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 146), "title")
        title.setToolTip(name)
        lay.addWidget(title)
        lay.addWidget(label(f"{inst['mc']} · {inst['loader'].title()}", "muted"))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.on_click(self.inst)


class AddTile(QFrame):
    def __init__(self, on_click):
        super().__init__()
        self.setObjectName("tileAdd")
        self.setFixedSize(176, 132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.on_click = on_click
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus = label("＋", "h1")
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(plus)
        t = label("Add version", "muted")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.on_click()


class ResultCard(QFrame):
    def __init__(self, hit, win):
        super().__init__()
        self.setObjectName("card")
        self.hit = hit
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 14, 14, 14)
        row.setSpacing(14)
        self.icon = QLabel()
        self.icon.setFixedSize(64, 64)
        self.icon.setPixmap(avatar(hit["title"], 64))
        row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(label(hit["title"], "title"))
        head.addWidget(label(f"by {hit.get('author', '?')}", "muted"))
        head.addStretch()
        col.addLayout(head)
        desc = hit.get("description", "")
        col.addWidget(label(desc if len(desc) < 190 else desc[:187] + "…", wrap=True))
        chips = QHBoxLayout()
        chips.setSpacing(6)
        chips.addWidget(label(f"⬇ {fmt(hit.get('downloads'))}", "muted"))
        chips.addWidget(label(f"♥ {fmt(hit.get('follows'))}", "muted"))
        for c in (hit.get("display_categories") or hit.get("categories") or [])[:3]:
            chips.addWidget(label(c, "chip"))
        chips.addStretch()
        col.addLayout(chips)
        row.addLayout(col, 1)

        self.btn = button("Install pack" if hit["project_type"] == "modpack" else "Install", "accent")
        self.btn.clicked.connect(lambda: win.install_hit(hit, self.btn))
        row.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignTop)

    def set_icon_bytes(self, data):
        pix = QPixmap()
        if pix.loadFromData(data):
            self.icon.setPixmap(rounded(pix, 64, 14))


# --------------------------------------------------------------------------- dialogs
class AddVersionDialog(QDialog):
    """Pick a Minecraft version and a profile (optimized presets, vanilla or empty loader)."""

    def __init__(self, versions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add version")
        self.setMinimumWidth(520)
        self.versions = versions
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(10)
        lay.addWidget(label("Add a version", "h1"))
        lay.addWidget(label("Pick a Minecraft version and a profile. Optimization mods are "
                            "downloaded and installed for you.", "muted", wrap=True))
        lay.addSpacing(4)

        self.version = QComboBox()
        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Minecraft", self.version)
        lay.addLayout(form)

        lay.addWidget(label("Profile", "muted"))
        self.profiles = QListWidget()
        self.profiles.setSpacing(3)
        for key, p in core.PRESETS.items():
            it = QListWidgetItem(f"{p['title']}\n{p['desc']}")
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setSizeHint(QSize(0, 58))
            self.profiles.addItem(it)
        self.profiles.setFixedHeight(min(len(core.PRESETS), 6) * 64 + 12)
        self.profiles.setCurrentRow(0)
        lay.addWidget(self.profiles)
        self.mods_lbl = label("", "muted", wrap=True)
        lay.addWidget(self.mods_lbl)

        self.name = QLineEdit()
        form2 = QFormLayout()
        form2.addRow("Name", self.name)
        lay.addLayout(form2)

        row = QHBoxLayout()
        row.addStretch()
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        create = button("Install", "accent")
        create.clicked.connect(self.accept)
        create.setDefault(True)
        row.addWidget(cancel)
        row.addWidget(create)
        lay.addSpacing(4)
        lay.addLayout(row)

        self.fill_versions()
        self.profiles.currentRowChanged.connect(self.refresh)
        self.version.currentTextChanged.connect(self.refresh)
        self.refresh()

    def fill_versions(self):
        self.version.clear()
        available = {v["id"] for v in self.versions}
        ids = [v for v in ALLOWED_VERSIONS if v in available] or list(ALLOWED_VERSIONS)
        self.version.addItems(ids)

    def key(self):
        it = self.profiles.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else "optimized"

    def default_name(self):
        return f"{self.version.currentText()} {core.PRESETS[self.key()]['short']}"

    def refresh(self, *_):
        mods = core.preset_mods(core.PRESETS[self.key()])
        pretty = ", ".join(m.replace("-", " ").title() for m in mods)
        self.mods_lbl.setText(f"Includes: {pretty}" if mods else "No mods will be installed.")
        self.name.setPlaceholderText(self.default_name())

    def values(self):
        return self.name.text().strip() or self.default_name(), self.version.currentText(), self.key()


class ModsDialog(QDialog):
    def __init__(self, inst, on_changed, on_browse, parent=None):
        super().__init__(parent)
        self.inst, self.on_changed, self.on_browse = inst, on_changed, on_browse
        self.mods_dir = core.game_dir(inst) / "mods"
        self.setWindowTitle(f"Mods — {inst['name']}")
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(10)
        lay.addWidget(label(f"{inst['name']}", "h1"))
        lay.addWidget(label("Tick a mod to enable it, untick to disable it.", "muted"))
        self.lst = QListWidget()
        self.lst.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.lst.itemChanged.connect(self.item_changed)
        lay.addWidget(self.lst, 1)
        row = QHBoxLayout()
        browse = button("Browse Modrinth", "accent")
        browse.clicked.connect(lambda: (self.accept(), self.on_browse(self.inst)))
        remove = button("Remove selected", "danger")
        remove.clicked.connect(self.remove_selected)
        folder = button("Open folder")
        folder.clicked.connect(lambda: (self.mods_dir.mkdir(parents=True, exist_ok=True), open_path(self.mods_dir)))
        row.addWidget(browse)
        row.addWidget(remove)
        row.addWidget(folder)
        row.addStretch()
        close = button("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.reload()

    def reload(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        if self.mods_dir.exists():
            for f in sorted(self.mods_dir.iterdir()):
                if f.name.endswith((".jar", ".jar.disabled")):
                    disabled = f.name.endswith(".disabled")
                    it = QListWidgetItem(f.name.removesuffix(".disabled"))
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    it.setCheckState(Qt.CheckState.Unchecked if disabled else Qt.CheckState.Checked)
                    it.setData(Qt.ItemDataRole.UserRole, f.name)
                    self.lst.addItem(it)
        self.lst.blockSignals(False)

    def item_changed(self, it):
        old = self.mods_dir / it.data(Qt.ItemDataRole.UserRole)
        enabled = it.checkState() == Qt.CheckState.Checked
        new = self.mods_dir / (it.text() if enabled else it.text() + ".disabled")
        if old != new and old.exists():
            old.rename(new)
            it.setData(Qt.ItemDataRole.UserRole, new.name)

    def remove_selected(self):
        items = self.lst.selectedItems()
        if not items:
            return
        if QMessageBox.question(self, "Remove mods", f"Delete {len(items)} mod file(s)?") != \
                QMessageBox.StandardButton.Yes:
            return
        for it in items:
            (self.mods_dir / it.data(Qt.ItemDataRole.UserRole)).unlink(missing_ok=True)
        self.reload()
        self.on_changed()


# --------------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    PROGRESS_RE = re.compile(r"^([A-Za-z ]+): (\d+)/(\d+)$")

    def __init__(self):
        super().__init__()
        self.setWindowTitle(core.APP_NAME)
        self.resize(1200, 780)
        self.setMinimumSize(1000, 660)
        self.cfg = core.load_config()
        self.versions = None
        self.instances = []
        self.selected_dir = self.cfg.get("last_instance")
        self.state = {}               # instance dir -> "starting" | "running"
        self._busy = 0
        self.pending_update = None
        self._discovered = False
        self._icon_cache = {}
        self._icon_pool = ThreadPoolExecutor(max_workers=6)
        self.bridge = Bridge()
        self.bridge.call.connect(self.on_call)
        self.bridge.log.connect(self.on_log)
        self.build_ui()
        self.refresh_home()
        self.bg(self.fetch_versions)
        if self.cfg.get("auto_update", True):
            QTimer.singleShot(1500, self.check_updates)

    # ---- threading plumbing
    @pyqtSlot(object)
    def on_call(self, fn):
        fn()

    def log(self, msg):
        self.bridge.log.emit(str(msg))

    @pyqtSlot(str)
    def on_log(self, msg):
        msg = msg.rstrip("\n")
        m = self.PROGRESS_RE.match(msg)
        if m:
            self.progress.setRange(0, int(m.group(3)))
            self.progress.setValue(int(m.group(2)))
            self.status.setText(f"{m.group(1)}  {m.group(2)}/{m.group(3)}")
        else:
            if self._busy:
                self.progress.setRange(0, 0)
            first = msg.splitlines()[0] if msg else ""
            self.status.setText(first[:140])
        self.console.appendPlainText(msg)

    def set_busy(self, delta):
        self._busy = max(0, self._busy + delta)
        if self._busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)

    def bg(self, fn, *args, done=None, fail=None):
        self.set_busy(+1)

        def run():
            ok, res = True, None
            try:
                res = fn(*args)
            except Exception as e:
                ok = False
                self.log(f"Error: {e}")
                self.log(traceback.format_exc(limit=3))

            def finish():
                self.set_busy(-1)
                if ok:
                    if done:
                        done(res)
                else:
                    self.status.setText("Something went wrong — see the console")
                    self.set_console(True)
                    if fail:
                        fail()
            self.bridge.call.emit(finish)

        threading.Thread(target=run, daemon=True).start()

    def fetch_versions(self):
        self.versions = core.list_versions()
        self.log(f"Loaded {len(self.versions)} Minecraft versions")

    # ---- layout
    def build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # top bar
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(64)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(24, 0, 20, 0)
        bl.setSpacing(4)
        bl.addWidget(label("🐧  PENGUIN", "logo"))
        bl.addSpacing(34)
        self.nav = QButtonGroup(self)
        for i, text in enumerate(("HOME", "DISCOVER", "SETTINGS")):
            b = QPushButton(text)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav.addButton(b, i)
            bl.addWidget(b)
        self.nav.button(0).setChecked(True)
        self.nav.idClicked.connect(self.on_nav)
        bl.addStretch()
        imp = button("Import .mrpack")
        imp.clicked.connect(self.import_mrpack)
        add = button("＋  Add version", "accent")
        add.clicked.connect(self.add_version)
        bl.addWidget(imp)
        bl.addSpacing(8)
        bl.addWidget(add)
        outer.addWidget(bar)

        # pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_home())
        self.stack.addWidget(self.build_discover())
        self.stack.addWidget(self.build_settings())
        outer.addWidget(self.stack, 1)

        # footer: progress + status + console
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        outer.addWidget(self.progress)
        foot = QHBoxLayout()
        foot.setContentsMargins(24, 6, 16, 6)
        self.status = label("Ready", "muted")
        foot.addWidget(self.status, 1)
        self.console_btn = button("Console ▴", "console")
        self.console_btn.clicked.connect(lambda: self.set_console(not self.console.isVisible()))
        foot.addWidget(self.console_btn)
        outer.addLayout(foot)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(3000)
        self.console.setFixedHeight(170)
        self.console.setVisible(False)
        outer.addWidget(self.console)

    def set_console(self, show):
        self.console.setVisible(show)
        self.console_btn.setText("Console ▾" if show else "Console ▴")

    def page(self, margins=(32, 26, 32, 16)):
        w = QWidget()
        w.setObjectName("page")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(*margins)
        lay.setSpacing(14)
        return w, lay

    def scroller(self, host, horizontal=False):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(host)
        if horizontal:
            sc.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return sc

    # ---- HOME page
    def build_home(self):
        w, lay = self.page((28, 22, 28, 10))
        lay.setSpacing(16)

        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bnl = QHBoxLayout(self.banner)
        bnl.setContentsMargins(18, 10, 12, 10)
        self.banner_lbl = label("", "title")
        bnl.addWidget(self.banner_lbl, 1)
        self.banner_btn = button("Update && restart", "accent")
        self.banner_btn.clicked.connect(self.install_update)
        later = button("Later")
        later.clicked.connect(self.banner.hide)
        bnl.addWidget(self.banner_btn)
        bnl.addWidget(later)
        self.banner.hide()
        lay.addWidget(self.banner)

        self.hero = HeroFrame()
        self.hero.setObjectName("hero")
        self.hero.setMinimumHeight(340)
        hl = QHBoxLayout(self.hero)
        hl.setContentsMargins(42, 34, 32, 34)
        hl.setSpacing(30)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.h_kicker = label("SELECTED VERSION", "kicker")
        self.h_title = label("Welcome", "heroTitle")
        self.chip_row = QHBoxLayout()
        self.chip_row.setSpacing(8)
        left.addWidget(self.h_kicker)
        left.addWidget(self.h_title)
        left.addLayout(self.chip_row)
        left.addStretch()

        row = QHBoxLayout()
        row.setSpacing(12)
        self.btn_launch = QPushButton("LAUNCH")
        self.btn_launch.setObjectName("launch")
        self.btn_launch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_launch.clicked.connect(self.launch_selected)
        self.sel_cb = QComboBox()
        self.sel_cb.setObjectName("pill")
        self.sel_cb.activated.connect(self.on_pick)
        self.btn_mods = button("🧩  Mods", "glassbtn")
        self.btn_mods.clicked.connect(lambda: self.selected() and self.manage_mods(self.selected()))
        self.more = QToolButton()
        self.more.setObjectName("more")
        self.more.setText("⋯")
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.more)
        menu.addAction("Open folder", lambda: self.selected() and open_path(core.game_dir(self.selected())))
        menu.addAction("Add mods from Modrinth…", lambda: self.selected() and self.go_discover(self.selected()))
        menu.addSeparator()
        menu.addAction("Delete…", lambda: self.selected() and self.delete_instance(self.selected()))
        self.more.setMenu(menu)
        for wdg in (self.btn_launch, self.sel_cb, self.btn_mods, self.more):
            row.addWidget(wdg)
        row.addStretch()
        left.addLayout(row)
        hl.addLayout(left, 1)

        self.glass = QFrame()
        self.glass.setObjectName("glass")
        self.glass.setFixedWidth(290)
        gl = QVBoxLayout(self.glass)
        gl.setContentsMargins(20, 18, 20, 18)
        gl.setSpacing(8)
        gl.addWidget(label("INSTALLED MODS", "kicker"))
        self.mods_lbl = label("", wrap=True)
        self.mods_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        gl.addWidget(self.mods_lbl, 1)
        manage = button("Manage mods", "glassSmall")
        manage.clicked.connect(lambda: self.selected() and self.manage_mods(self.selected()))
        gl.addWidget(manage)
        hl.addWidget(self.glass)
        lay.addWidget(self.hero)

        lay.addWidget(label("Your versions", "h2"))
        self.tiles_host = QWidget()
        self.tiles_lay = QHBoxLayout(self.tiles_host)
        self.tiles_lay.setContentsMargins(0, 2, 0, 2)
        self.tiles_lay.setSpacing(14)
        sc = self.scroller(self.tiles_host, horizontal=True)
        sc.setFixedHeight(168)
        lay.addWidget(sc)
        lay.addStretch()
        return w

    def selected(self):
        return next((i for i in self.instances if i["dir"] == self.selected_dir), None)

    def select_instance(self, inst):
        self.selected_dir = inst["dir"]
        self.cfg["last_instance"] = inst["dir"]
        core.save_config(self.cfg)
        self.refresh_home()

    def on_pick(self, idx):
        d = self.sel_cb.itemData(idx)
        inst = next((i for i in self.instances if i["dir"] == d), None)
        if inst:
            self.select_instance(inst)

    def refresh_home(self):
        self.instances = core.list_instances()
        dirs = [i["dir"] for i in self.instances]
        if self.selected_dir not in dirs:
            self.selected_dir = dirs[0] if dirs else None

        clear_layout(self.tiles_lay)
        for inst in self.instances:
            self.tiles_lay.addWidget(TileCard(inst, inst["dir"] == self.selected_dir, self.select_instance))
        self.tiles_lay.addWidget(AddTile(self.add_version))
        self.tiles_lay.addStretch()

        self.sel_cb.blockSignals(True)
        self.sel_cb.clear()
        for inst in self.instances:
            self.sel_cb.addItem(inst["name"], inst["dir"])
        if self.selected_dir:
            self.sel_cb.setCurrentIndex(self.sel_cb.findData(self.selected_dir))
        self.sel_cb.blockSignals(False)

        current = self.target_cb.currentData()
        self.target_cb.blockSignals(True)
        self.target_cb.clear()
        for inst in self.instances:
            self.target_cb.addItem(f"{inst['name']}  ({inst['mc']} {inst['loader']})", inst["dir"])
        i = self.target_cb.findData(self.selected_dir or current)
        self.target_cb.setCurrentIndex(i if i >= 0 else 0)
        self.target_cb.blockSignals(False)
        self.update_hero()

    def update_hero(self):
        inst = self.selected()
        clear_layout(self.chip_row)
        has = inst is not None
        for wdg in (self.sel_cb, self.btn_mods, self.more):
            wdg.setEnabled(has)
        if not has:
            self.h_kicker.setText("GET STARTED")
            self.h_title.setText("Welcome")
            self.chip_row.addWidget(label("Add a version to start playing — optimized profiles are ready to go.",
                                          "chipHero"))
            self.chip_row.addStretch()
            self.mods_lbl.setText("Nothing installed yet.")
            self.btn_launch.setText("ADD VERSION")
            self.btn_launch.setEnabled(True)
            return
        self.h_kicker.setText("SELECTED VERSION")
        self.h_title.setText(inst["name"])
        n_mods, names = mod_names(inst)
        for text in (f"Minecraft {inst['mc']}", inst["loader"].title(),
                     f"{n_mods} mod{'s' if n_mods != 1 else ''}" if inst["loader"] != "vanilla" else "No mods"):
            self.chip_row.addWidget(label(text, "chipHero"))
        self.chip_row.addStretch()
        if names:
            more = f"\n+ {n_mods - len(names)} more" if n_mods > len(names) else ""
            self.mods_lbl.setText("\n".join(f"•  {n}" for n in names) + more)
        else:
            self.mods_lbl.setText("No mods installed." if inst["loader"] != "vanilla"
                                  else "Vanilla profile — no mods.")
        st = self.state.get(inst["dir"])
        self.btn_launch.setText({"starting": "PREPARING…", "running": "PLAYING"}.get(st, "LAUNCH"))
        self.btn_launch.setEnabled(st is None)

    # ---- DISCOVER page
    def build_discover(self):
        w, lay = self.page()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label("Discover", "h1"))
        col.addWidget(label("Browse mods and modpacks from Modrinth", "muted"))
        lay.addLayout(col)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.q = QLineEdit()
        self.q.setPlaceholderText("Search Modrinth…")
        self.q.returnPressed.connect(self.search)
        bar.addWidget(self.q, 1)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.type_group = QButtonGroup(self)
        self.btn_mod, self.btn_pack = QPushButton("Mods"), QPushButton("Modpacks")
        for i, b in enumerate((self.btn_mod, self.btn_pack)):
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.type_group.addButton(b, i)
            seg.addWidget(b)
        self.btn_mod.setChecked(True)
        self.type_group.idClicked.connect(lambda _: self.search())
        bar.addLayout(seg)
        go = button("Search", "accent")
        go.clicked.connect(self.search)
        bar.addWidget(go)
        lay.addLayout(bar)

        opts = QHBoxLayout()
        opts.setSpacing(10)
        opts.addWidget(label("Install into", "muted"))
        self.target_cb = QComboBox()
        self.target_cb.setMinimumWidth(240)
        opts.addWidget(self.target_cb)
        self.chk_match = QCheckBox("Only show mods compatible with this version")
        self.chk_match.setChecked(True)
        opts.addWidget(self.chk_match)
        opts.addStretch()
        lay.addLayout(opts)

        self.res_host = QWidget()
        self.res_lay = QVBoxLayout(self.res_host)
        self.res_lay.setContentsMargins(0, 4, 6, 4)
        self.res_lay.setSpacing(10)
        self.res_lay.addStretch()
        lay.addWidget(self.scroller(self.res_host), 1)
        return w

    # ---- SETTINGS page
    def build_settings(self):
        w, lay = self.page()
        lay.addWidget(label("Settings", "h1"))
        panel = QFrame()
        panel.setObjectName("panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(24, 22, 24, 22)
        pl.setSpacing(12)

        pl.addWidget(label("Memory", "h2"))
        mrow = QHBoxLayout()
        self.s_mem = QSlider(Qt.Orientation.Horizontal)
        self.s_mem.setRange(2, 64)  # steps of 512 MB
        self.s_mem.setMaximumWidth(380)
        self.s_mem.setValue(max(2, min(64, int(self.cfg["memory_mb"]) // 512)))
        self.mem_lbl = label("")
        self.s_mem.valueChanged.connect(self.update_mem_label)
        self.s_mem.valueChanged.connect(lambda _: self.save_settings())
        self.update_mem_label()
        mrow.addWidget(self.s_mem)
        mrow.addWidget(self.mem_lbl)
        mrow.addStretch()
        pl.addLayout(mrow)
        pl.addSpacing(8)

        pl.addWidget(label("Java", "h2"))
        jrow = QHBoxLayout()
        self.s_java = QLineEdit(self.cfg["java_path"])
        self.s_java.setPlaceholderText("Auto-detect (leave empty)")
        self.s_java.setMaximumWidth(380)
        self.s_java.editingFinished.connect(self.save_settings)
        browse = button("Browse…")
        browse.clicked.connect(self.browse_java)
        jrow.addWidget(self.s_java)
        jrow.addWidget(browse)
        jrow.addStretch()
        pl.addLayout(jrow)
        pl.addSpacing(8)
        pl.addWidget(label("Updates", "h2"))
        urow = QHBoxLayout()
        self.chk_update = QCheckBox("Check for updates on startup")
        self.chk_update.setChecked(self.cfg.get("auto_update", True))
        self.chk_update.toggled.connect(lambda _: self.save_settings())
        check_now = button("Check now")
        check_now.clicked.connect(lambda: self.check_updates(manual=True))
        urow.addWidget(self.chk_update)
        urow.addWidget(check_now)
        urow.addStretch()
        pl.addLayout(urow)
        pl.addWidget(label(f"Version {core.APP_VERSION}", "muted"))
        pl.addSpacing(8)
        pl.addWidget(label(f"Changes are saved automatically.   Data folder: {core.DATA}", "muted"))
        lay.addWidget(panel)
        lay.addStretch()
        return w

    # ---- auto update
    def check_updates(self, manual=False):
        if updater is None or not updater.enabled():
            if manual:
                QMessageBox.information(self, core.APP_NAME,
                                        "Updates aren't set up yet.\nSet UPDATE_MANIFEST_URL in penguin_updater.py.")
            return

        def work():
            manifest, err = None, None
            try:
                manifest = updater.check_for_update(core.APP_VERSION)
            except Exception as e:      # offline etc. - stay quiet unless the user asked
                err = e
            self.bridge.call.emit(lambda: self.on_update_result(manifest, err, manual))
        threading.Thread(target=work, daemon=True).start()

    def on_update_result(self, manifest, err, manual):
        if manifest:
            self.pending_update = manifest
            notes = (manifest.get("notes") or "").strip().splitlines()
            extra = f" — {notes[0]}" if notes else ""
            self.banner_lbl.setText(f"Update {manifest['version']} is available{extra}")
            self.banner_btn.setEnabled(True)
            self.banner_btn.setText("Update && restart")
            self.banner.show()
        elif manual:
            self.status.setText(f"Couldn't check for updates: {err}" if err else "You're up to date.")

    def install_update(self):
        m = self.pending_update
        if not m:
            return
        self.banner_btn.setEnabled(False)
        self.banner_btn.setText("Updating…")
        self.bg(updater.apply_update, m, self.log, done=lambda _: self.after_update(m),
                fail=lambda: (self.banner_btn.setEnabled(True), self.banner_btn.setText("Retry")))

    def after_update(self, m):
        QMessageBox.information(self, core.APP_NAME,
                                f"Updated to {m['version']}. The launcher will now restart.")
        updater.restart()
        QApplication.quit()

    # ---- navigation
    def on_nav(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 1 and not self._discovered:
            self._discovered = True
            self.search()

    def go_discover(self, inst=None):
        if inst:
            i = self.target_cb.findData(inst["dir"])
            if i >= 0:
                self.target_cb.setCurrentIndex(i)
            self.btn_mod.setChecked(True)
        self.nav.button(1).setChecked(True)
        self.stack.setCurrentIndex(1)
        self._discovered = True
        self.search()

    # ---- settings
    def update_mem_label(self):
        self.mem_lbl.setText(f"{self.s_mem.value() * 512 / 1024:.1f} GB")

    def browse_java(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select java executable", "/usr/lib/jvm")
        if path:
            self.s_java.setText(path)
            self.save_settings()

    def save_settings(self):
        self.cfg.update(memory_mb=self.s_mem.value() * 512, java_path=self.s_java.text().strip(),
                        auto_update=self.chk_update.isChecked() if hasattr(self, "chk_update") else True)
        core.save_config(self.cfg)

    # ---- instances
    def target_instance(self):
        d = self.target_cb.currentData()
        return next((i for i in self.instances if i["dir"] == d), None)

    def add_version(self):
        if self.versions is None:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self.versions = core.list_versions()
            except Exception as e:
                QMessageBox.critical(self, core.APP_NAME, f"Couldn't fetch the version list:\n{e}")
                return
            finally:
                QApplication.restoreOverrideCursor()
        dlg = AddVersionDialog(self.versions, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, ver, key = dlg.values()
        self.bg(self.create_preset, name, ver, key, done=self.after_create)

    def create_preset(self, name, ver, key):
        inst = core.create_from_preset(name, ver, key, self.log)
        self.log(f"'{inst['name']}' is ready to play")
        return inst

    def after_create(self, inst):
        self.selected_dir = inst["dir"]
        self.cfg["last_instance"] = inst["dir"]
        core.save_config(self.cfg)
        self.refresh_home()

    def manage_mods(self, inst):
        ModsDialog(inst, self.refresh_home, self.go_discover, self).exec()
        self.refresh_home()

    def delete_instance(self, inst):
        if QMessageBox.question(self, "Delete version",
                                f"Delete '{inst['name']}' including its worlds and mods?") \
                == QMessageBox.StandardButton.Yes:
            shutil.rmtree(inst["dir"], ignore_errors=True)
            self.refresh_home()

    def import_mrpack(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import modpack", "", "Modrinth modpack (*.mrpack)")
        if path:
            self.bg(self.do_import, path, done=self.after_create)

    def do_import(self, path):
        inst = core.install_mrpack(path, None, self.log)
        core.prepare(inst, self.log)
        self.log(f"Imported '{inst['name']}'")
        return inst

    # ---- launching
    def set_state(self, d, st):
        if st is None:
            self.state.pop(d, None)
        else:
            self.state[d] = st
        self.update_hero()

    def launch_selected(self):
        inst = self.selected()
        if inst:
            self.play(inst)
        else:
            self.add_version()

    def play(self, inst):
        d = inst["dir"]
        self.set_state(d, "starting")
        self.bg(self.launch, inst, fail=lambda: self.set_state(d, None))

    def launch(self, inst):
        d = inst["dir"]
        vdata, classpath, natives_dir, assets_dir = core.prepare(inst, self.log)
        required = vdata.get("javaVersion", {}).get("majorVersion", 8)
        java = core.find_java(required, self.cfg["java_path"])
        cmd = core.build_command(vdata, inst, self.cfg, java, classpath, natives_dir, assets_dir)
        gdir = core.game_dir(inst)
        gdir.mkdir(parents=True, exist_ok=True)
        logfile = gdir / "launcher.log"
        self.log(f"Launching {inst['name']} with {java}")
        out = open(logfile, "w")
        proc = subprocess.Popen(cmd, cwd=gdir, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        self.bridge.call.emit(lambda: self.set_state(d, "running"))

        def waiter():
            code = proc.wait()
            out.close()
            self.log(f"Game exited with code {code}" + ("" if code == 0 else f" — see {logfile}"))
            self.bridge.call.emit(lambda: self.set_state(d, None))
        threading.Thread(target=waiter, daemon=True).start()

    # ---- modrinth
    def search(self):
        ptype = "modpack" if self.btn_pack.isChecked() else "mod"
        inst = self.target_instance() if (self.chk_match.isChecked() and ptype == "mod") else None
        self.chk_match.setEnabled(ptype == "mod")
        self.bg(core.mr_search, self.q.text().strip(), ptype,
                inst["mc"] if inst else None, inst["loader"] if inst else None, done=self.show_hits)

    def show_hits(self, hits):
        clear_layout(self.res_lay)
        if not hits:
            self.res_lay.addWidget(label("No results.", "muted"))
        for hit in hits:
            card = ResultCard(hit, self)
            self.res_lay.addWidget(card)
            if hit.get("icon_url"):
                self.load_icon(hit["icon_url"], card)
        self.res_lay.addStretch()
        self.status.setText(f"{len(hits)} result(s)")

    def load_icon(self, url, card):
        def apply(data):
            try:
                card.set_icon_bytes(data)
            except RuntimeError:  # card was deleted by a newer search
                pass

        if url in self._icon_cache:
            apply(self._icon_cache[url])
            return

        def fetch():
            try:
                data = core.http_get(url, timeout=15)
            except Exception:
                return
            self._icon_cache[url] = data
            self.bridge.call.emit(lambda: apply(data))
        self._icon_pool.submit(fetch)

    def install_hit(self, hit, btn):
        pid, title = hit["project_id"], hit["title"]

        def safe(fn):
            def wrapper(*a):
                try:
                    fn(*a)
                except RuntimeError:
                    pass
            return wrapper

        def ok(_):
            btn.setText("Installed ✓")
            self.refresh_home()

        def bad():
            btn.setEnabled(True)
            btn.setText("Retry")

        if hit["project_type"] == "modpack":
            btn.setEnabled(False)
            btn.setText("Installing…")
            self.bg(self.install_pack, pid, title, done=safe(ok), fail=safe(bad))
            return
        inst = self.target_instance()
        if not inst:
            QMessageBox.information(self, core.APP_NAME, "Add a version first.")
            return
        if inst["loader"] == "vanilla":
            QMessageBox.information(self, core.APP_NAME,
                                    "Vanilla profiles can't use mods — pick a Fabric or Quilt version.")
            return
        btn.setEnabled(False)
        btn.setText("Installing…")
        self.bg(self.install_one_mod, pid, inst, done=safe(ok), fail=safe(bad))

    def install_one_mod(self, pid, inst):
        core.install_mod(pid, inst, self.log)
        self.log("Done")

    def install_pack(self, pid, title):
        inst = core.install_modpack_project(pid, title, self.log)
        core.prepare(inst, self.log)
        self.log(f"Modpack '{title}' installed as a new version")
        return inst


def main():
    for d in (core.INSTANCES, core.VERSIONS, core.LIBS, core.ASSETS, core.CACHE):
        d.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setApplicationName(core.APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
