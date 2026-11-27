# -*- coding: utf-8 -*-
"""
相机照片工具：批量重命名 + 批量替换内容
- PySide6 + qfluentwidgets
- OPPO Sans 字体（免费商用）
"""
import os
import re
import sys
import json
import shutil
import datetime
from dataclasses import dataclass
from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QFontDatabase, QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
    QTableWidgetItem, QHeaderView, QMessageBox, QSpinBox, QSizePolicy,
)
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, setTheme, Theme,
    PushButton, ComboBox, CheckBox, LineEdit, BodyLabel,
    CaptionLabel, CardWidget, StrongBodyLabel, InfoBar, InfoBarPosition,
    FluentIcon as FIF, RadioButton, PrimaryPushButton, HyperlinkLabel,
    TableWidget,
)

APP_TITLE = "相机照片工具"
GITHUB_URL = "https://github.com/yelina123/camera-renamer"
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".camera_renamer_settings.json")


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


DEFAULT_SETTINGS = {
    "rename": {
        "prefix": "", "start": 1, "end": 0,
        "zfill": True, "digits": 3, "fsuffix": "", "forcext": "",
    },
    "rename_out": {
        "mode": "copy", "dir": "", "conflict": 0,
    },
    "replace": {
        "backup": False, "backup_dir": "",
    },
}


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(DEFAULT_SETTINGS))


def save_settings(s: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save settings failed:", e)


# ---------------------------------------------------------------------------
# 数据模型 & 公共工具
# ---------------------------------------------------------------------------
@dataclass
class FileItem:
    path: str

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def ext(self) -> str:
        return os.path.splitext(self.path)[1]

    @property
    def size(self) -> int:
        try: return os.path.getsize(self.path)
        except OSError: return 0

    @property
    def mtime(self) -> float:
        try: return os.path.getmtime(self.path)
        except OSError: return 0.0


def add_paths(items: list[FileItem], paths: list[str]) -> int:
    existing = {it.path for it in items}
    added = 0
    for p in paths:
        p = os.path.abspath(p)
        if p in existing or not os.path.isfile(p):
            continue
        items.append(FileItem(p))
        existing.add(p)
        added += 1
    return added


_NAT_RE = re.compile(r"(\d+)")


def natural_key(s: str):
    """自然排序键：把字符串里的数字段按数值比较。

    幻灯片 1 / 幻灯片 2 / 幻灯片 10 -> 1, 2, 10
    而不是字典序 1, 10, 2。
    """
    parts = _NAT_RE.split(s.lower())
    key = []
    for i, p in enumerate(parts):
        if i % 2 == 1:      # 数字段
            key.append((0, int(p)))
        else:               # 文本段
            key.append((1, p))
    key.append((1, s.lower()))   # 等值时用原串兜底，保证顺序稳定
    return key


def sort_items(items: list[FileItem], key: str, asc: bool):
    kf = {"name": lambda it: natural_key(it.name),
          "mtime": lambda it: (it.mtime, natural_key(it.name)),
          "size": lambda it: (it.size, natural_key(it.name))}[key]
    items.sort(key=kf, reverse=not asc)


def size_str(n: int) -> str:
    kb = n / 1024
    return f"{kb:.1f} KB" if kb < 1024 else f"{kb/1024:.2f} MB"


# ---------------------------------------------------------------------------
# 相机识别
#   典型目录结构：D:\DCIM\100MEDIA\100_0123.jpeg
#   也兼容 100CANON / 100MSDCF / 100APPLE 这类写法
# ---------------------------------------------------------------------------
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".heic", ".heif", ".tif", ".tiff",
    ".bmp", ".gif", ".webp", ".cr2", ".cr3", ".nef", ".arw", ".dng",
    ".raf", ".orf", ".rw2", ".pef", ".srw",
}

MEDIA_DIR_RE = re.compile(r"^(\d{3})([A-Za-z]+)$")     # 100MEDIA
CAM_NAME_RE = re.compile(r"^(.+?)(\d+)(\.[A-Za-z0-9]+)$")  # 100_0123.jpeg


@dataclass
class CameraInfo:
    root: str          # 媒体目录，如 D:\DCIM\100MEDIA
    drive: str         # 盘符，如 D:\
    folder: str        # 媒体目录名，如 100MEDIA
    prefix: str        # 文件名里的前缀，如 100_
    digits: int        # 数字位数，如 4
    last_num: int      # 相机里已有最大编号，如 123
    count: int         # 该目录图片数量
    last_file: str     # 最后一支文件名
    ext: str           # 该目录的扩展名，如 .jpeg
    mtime: float = 0.0

    @property
    def next_num(self) -> int:
        return self.last_num + 1

    @property
    def overflow(self) -> bool:
        return self.next_num >= 10 ** self.digits

    @property
    def next_name(self) -> str:
        return f"{self.prefix}{str(self.next_num).zfill(self.digits)}{self.ext}"

    @property
    def summary(self) -> str:
        return f"{self.drive}  ·  DCIM\\{self.folder}  ·  已有 {self.count} 张，最后一张 {self.last_file}"


def _drive_roots(roots=None) -> list[str]:
    """枚举可能的相机盘符。Windows 下扫 A:-Z:；其他平台供测试用。"""
    if roots is not None:
        return list(roots)
    out = []
    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            d = f"{letter}:\\"
            if os.path.isdir(d):
                out.append(d)
    else:
        env = os.environ.get("CAMERA_TEST_ROOT")
        if env:
            out.append(env)
    return out


def _analyze_media_dir(path: str, drive: str, folder: str):
    try:
        names = os.listdir(path)
    except OSError:
        return None

    count = 0
    best = None  # (编号, 前缀, 位数, 扩展名, 文件名)
    for f in names:
        ext = os.path.splitext(f)[1]
        if ext.lower() not in IMAGE_EXTS:
            continue
        m = CAM_NAME_RE.match(f)
        if not m:
            continue
        count += 1
        num = int(m.group(2))
        cand = (num, m.group(1), len(m.group(2)), ext, f)
        if best is None or cand[0] > best[0]:
            best = cand

    if not best:
        return None

    try:
        mt = os.path.getmtime(path)
    except OSError:
        mt = 0.0

    num, prefix, digits, ext, fname = best
    return CameraInfo(root=path, drive=drive, folder=folder, prefix=prefix,
                      digits=digits, last_num=num, count=count, last_file=fname,
                      ext=ext, mtime=mt)


def scan_cameras(roots=None) -> list[CameraInfo]:
    """扫描所有盘符，返回识别到的相机媒体目录（每个盘符取最近使用的一个）。"""
    found = []
    for drive in _drive_roots(roots):
        dcim = os.path.join(drive, "DCIM")
        if not os.path.isdir(dcim):
            continue
        try:
            subs = [d for d in os.listdir(dcim)
                    if MEDIA_DIR_RE.match(d) and os.path.isdir(os.path.join(dcim, d))]
        except OSError:
            continue

        best = None
        for sub in subs:
            info = _analyze_media_dir(os.path.join(dcim, sub), drive, sub)
            if not info:
                continue
            # 取最近改动过的那个目录（相机换号后会新建 101MEDIA）
            if best is None or (info.mtime, info.count, info.last_num) > \
                               (best.mtime, best.count, best.last_num):
                best = info
        if best:
            found.append(best)
    return found


def make_table(table: TableWidget, headers: list[str]):
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(TableWidget.NoEditTriggers)
    table.setSelectionBehavior(TableWidget.SelectRows)
    table.setBorderVisible(True)
    table.setBorderRadius(8)
    h = table.horizontalHeader()
    h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    for i in range(1, len(headers) - 1):
        h.setSectionResizeMode(i, QHeaderView.Stretch)
    h.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeToContents)


# ---------------------------------------------------------------------------
# 主页
# ---------------------------------------------------------------------------
class HomePage(QWidget):
    goRename = Signal()
    goReplace = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(16)
        title = StrongBodyLabel("相机照片工具", self)
        title.setStyleSheet("font-size:22px;")
        lay.addWidget(title)
        lay.addWidget(BodyLabel("选择你要做的事：", self))
        lay.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(20)
        c1 = CardWidget(self)
        l1 = QVBoxLayout(c1)
        l1.setContentsMargins(24, 24, 24, 24)
        l1.setSpacing(10)
        l1.addWidget(StrongBodyLabel("📝 批量重命名", self))
        l1.addWidget(BodyLabel("给文件加前缀和编号，可直接导入相机\n例如 DSC001.jpg, DSC002.jpg", self))
        l1.addStretch(1)
        b1 = PrimaryPushButton("进入重命名", self)
        b1.clicked.connect(self.goRename.emit)
        l1.addWidget(b1)
        row.addWidget(c1, 1)

        c2 = CardWidget(self)
        l2 = QVBoxLayout(c2)
        l2.setContentsMargins(24, 24, 24, 24)
        l2.setSpacing(10)
        l2.addWidget(StrongBodyLabel("🔄 批量替换内容", self))
        l2.addWidget(BodyLabel("保留旧文件名，用新文件内容覆盖\n例如把 a.jpg 的内容换成新拍的 raw", self))
        l2.addStretch(1)
        b2 = PrimaryPushButton("进入替换", self)
        b2.clicked.connect(self.goReplace.emit)
        l2.addWidget(b2)
        row.addWidget(c2, 1)
        lay.addLayout(row)
        lay.addStretch(2)


# ---------------------------------------------------------------------------
# 重命名：文件列表
# ---------------------------------------------------------------------------
class RenameFilePage(QWidget):
    itemsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[FileItem] = []
        self.sort_key = "name"; self.sort_asc = True
        self._build(); self.setAcceptDrops(True)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20); lay.setSpacing(10)
        bar = QHBoxLayout()
        self.btn_add = PushButton("添加文件", self, FIF.FOLDER)
        self.btn_dir = PushButton("添加文件夹", self, FIF.IOT)
        self.btn_rm = PushButton("移除选中", self, FIF.DELETE)
        self.btn_clr = PushButton("清空", self, FIF.CANCEL)
        self.sort = ComboBox(self)
        self.sort.addItems(["名称↑", "名称↓", "时间↑", "时间↓", "大小↑", "大小↓"])
        self.sort.setCurrentIndex(0)
        for w in (self.btn_add, self.btn_dir, self.btn_rm, self.btn_clr):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(CaptionLabel("排序：", self))
        bar.addWidget(self.sort)
        lay.addLayout(bar)

        self.table = TableWidget(self)
        make_table(self.table, ["#", "原文件名", "新文件名（预览）", "大小"])
        lay.addWidget(self.table, 1)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Stretch)

        self.hint = CaptionLabel("提示：可直接把文件或文件夹拖到本窗口", self)
        self.hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.hint)

        self.btn_add.clicked.connect(self._pick_files)
        self.btn_dir.clicked.connect(self._pick_dir)
        self.btn_rm.clicked.connect(self._remove)
        self.btn_clr.clicked.connect(self._clear)
        self.sort.currentIndexChanged.connect(self._onsort)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        paths = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if not p: continue
            if os.path.isdir(p):
                for r, _, fs in os.walk(p):
                    for f in fs: paths.append(os.path.join(r, f))
            elif os.path.isfile(p):
                paths.append(p)
        self._add(paths)

    def _pick_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "选择照片", "")
        self._add(fs)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not d: return
        paths = []
        for r, _, fs in os.walk(d):
            for f in fs: paths.append(os.path.join(r, f))
        self._add(paths)

    def _add(self, paths):
        if add_paths(self.items, paths):
            sort_items(self.items, self.sort_key, self.sort_asc)
            self.refresh()
            self.itemsChanged.emit()

    def _remove(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.items): self.items.pop(r)
        self.refresh(); self.itemsChanged.emit()

    def _clear(self):
        self.items.clear(); self.refresh(); self.itemsChanged.emit()

    def _onsort(self, idx):
        km = [("name", True), ("name", False), ("mtime", True),
              ("mtime", False), ("size", True), ("size", False)]
        self.sort_key, self.sort_asc = km[idx]
        sort_items(self.items, self.sort_key, self.sort_asc)
        self.refresh(); self.itemsChanged.emit()

    def refresh(self, new_names=None):
        self.table.setRowCount(len(self.items))
        for i, it in enumerate(self.items):
            nn = new_names[i] if new_names else ""
            vals = [str(i + 1), it.name, nn, size_str(it.size)]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c == 0: item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, c, item)


# ---------------------------------------------------------------------------
# 重命名：命名规则
# ---------------------------------------------------------------------------
class RenameRulePage(CardWidget):
    ruleChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(14)
        lay.addWidget(StrongBodyLabel("命名格式", self))

        r1 = QHBoxLayout()
        r1.addWidget(BodyLabel("前缀：", self))
        self.prefix = LineEdit(self)
        self.prefix.setPlaceholderText("例如 DSC_ 或 IMG-（分隔符直接写在前缀里）")
        r1.addWidget(self.prefix, 1)
        self.btn_detect = PushButton("从示例文件识别", self, FIF.SEARCH)
        self.btn_detect.setToolTip("选一张现有照片，自动识别前缀和数字位数")
        r1.addWidget(self.btn_detect)
        lay.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(BodyLabel("起始号：", self))
        self.start = QSpinBox(self); self.start.setRange(1, 999999); self.start.setValue(1)
        self.start.setFixedWidth(110); r2.addWidget(self.start)
        r2.addWidget(BodyLabel("终止号：", self))
        self.end = QSpinBox(self); self.end.setRange(0, 999999); self.end.setValue(0)
        self.end.setSpecialValueText("自动"); self.end.setFixedWidth(110)
        r2.addWidget(self.end)
        self.zfill = CheckBox("补零到", self); self.zfill.setChecked(True)
        r2.addWidget(self.zfill)
        self.digits = QSpinBox(self); self.digits.setRange(1, 10); self.digits.setValue(3)
        self.digits.setFixedWidth(70); r2.addWidget(self.digits)
        r2.addWidget(BodyLabel("位", self)); r2.addStretch(1)
        lay.addLayout(r2)

        # 统一 SpinBox 样式
        spin_qss = """
            QSpinBox {
                border: 1px solid #d0d0d0; border-radius: 6px;
                padding: 4px 8px; background: white; min-height: 20px;
            }
            QSpinBox:focus { border-color: #0067c0; }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 18px; border: none; background: transparent;
            }
        """
        for w in (self.start, self.end, self.digits):
            w.setStyleSheet(spin_qss)

        r3 = QHBoxLayout()
        lab1 = BodyLabel("固定后缀：", self)
        lab1.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        r3.addWidget(lab1)
        self.fsuffix = LineEdit(self); self.fsuffix.setPlaceholderText("例如 _v2（可留空）")
        self.fsuffix.setFixedWidth(200); r3.addWidget(self.fsuffix)
        r3.addSpacing(20)
        lab2 = BodyLabel("扩展名：", self)
        lab2.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        r3.addWidget(lab2)
        self.forcext = LineEdit(self)
        self.forcext.setPlaceholderText("留空=保留原扩展名，填 .jpg 则强制改")
        self.forcext.setFixedWidth(260); r3.addWidget(self.forcext)
        r3.addStretch(1)
        lay.addLayout(r3)

        lay.addWidget(StrongBodyLabel("实时预览", self))
        self.preview = BodyLabel("示例：DSC001.jpg", self)
        self.preview.setStyleSheet("color:#0067c0; font-size:14px;")
        lay.addWidget(self.preview)
        lay.addStretch(1)

        self.prefix.textChanged.connect(self._emit)
        self.start.valueChanged.connect(self._emit)
        self.end.valueChanged.connect(self._emit)
        self.digits.valueChanged.connect(self._emit)
        self.zfill.stateChanged.connect(self._onzfill)
        self.fsuffix.textChanged.connect(self._emit)
        self.forcext.textChanged.connect(self._emit)
        self.btn_detect.clicked.connect(self._detect)
        self._onzfill()
        self.load_defaults()

    def load_defaults(self, d: dict = None):
        d = d or DEFAULT_SETTINGS["rename"]
        self.prefix.blockSignals(True); self.prefix.setText(d.get("prefix", "")); self.prefix.blockSignals(False)
        self.start.blockSignals(True); self.start.setValue(d.get("start", 1)); self.start.blockSignals(False)
        self.end.blockSignals(True); self.end.setValue(d.get("end", 0)); self.end.blockSignals(False)
        self.zfill.blockSignals(True); self.zfill.setChecked(d.get("zfill", True)); self.zfill.blockSignals(False)
        self.digits.blockSignals(True); self.digits.setValue(d.get("digits", 3)); self.digits.blockSignals(False)
        self.fsuffix.blockSignals(True); self.fsuffix.setText(d.get("fsuffix", "")); self.fsuffix.blockSignals(False)
        self.forcext.blockSignals(True); self.forcext.setText(d.get("forcext", "")); self.forcext.blockSignals(False)
        self._onzfill()

    def to_dict(self) -> dict:
        return {
            "prefix": self.prefix.text(),
            "start": self.start.value(), "end": self.end.value(),
            "zfill": self.zfill.isChecked(), "digits": self.digits.value(),
            "fsuffix": self.fsuffix.text(), "forcext": self.forcext.text(),
        }

    def _detect(self):
        path, _ = QFileDialog.getOpenFileName(self, "选一张示例照片（识别前缀和位数）", "",
                                              "图片文件 (*.jpg *.jpeg *.png *.cr2 *.nef *.arw *.dng *.raw *.tif *.tiff);;所有文件 (*)")
        if not path:
            return
        base = os.path.splitext(os.path.basename(path))[0]
        # 从右往左找连续数字
        i = len(base) - 1
        while i >= 0 and base[i].isdigit():
            i -= 1
        num_part = base[i+1:]
        prefix_part = base[:i+1]
        if not num_part:
            InfoBar.warning("识别失败", "文件名末尾没有数字，无法自动识别", self,
                            position=InfoBarPosition.TOP, duration=3000)
            return
        self.prefix.setText(prefix_part)
        self.digits.setValue(len(num_part))
        self.zfill.setChecked(True)
        try:
            self.start.setValue(int(num_part))
        except ValueError:
            pass
        InfoBar.success("识别完成",
                        f"前缀: {prefix_part}，位数: {len(num_part)}，起始号: {int(num_part)}",
                        self, position=InfoBarPosition.TOP, duration=3000)

    def apply_camera(self, cam):
        """按相机已有文件自动填好命名规则（接续相机最后一号）。"""
        self.prefix.setText(cam.prefix)
        self.zfill.setChecked(True)
        self.digits.setValue(cam.digits)
        self.start.setValue(min(cam.next_num, self.start.maximum()))
        self.end.setValue(0)
        self.forcext.setText(cam.ext)
        self._emit()
        self.refresh_preview(cam.ext)

    def _onzfill(self): self.digits.setEnabled(self.zfill.isChecked())
    def _emit(self, *a): self.ruleChanged.emit()

    def compute(self, index: int, ext: str) -> str:
        n = self.start.value() + index
        prefix = self.prefix.text().strip()
        num = str(n).zfill(self.digits.value()) if self.zfill.isChecked() else str(n)
        name = f"{prefix}{num}" if prefix else num
        fs = self.fsuffix.text().strip()
        if fs: name += fs
        fe = self.forcext.text().strip()
        if fe:
            if not fe.startswith("."): fe = "." + fe
            name += fe
        else:
            name += ext
        return name

    def refresh_preview(self, ext=".jpg"):
        self.preview.setText(f"示例：{self.compute(0, ext)}")


# ---------------------------------------------------------------------------
# 重命名：输出
# ---------------------------------------------------------------------------
class RenameOutputPage(CardWidget):
    cameraDetected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18); lay.setSpacing(10)
        lay.addWidget(StrongBodyLabel("输出位置", self))

        self.rb_copy = RadioButton("复制到新目录（推荐，原文件不动）", self)
        self.rb_copy.setChecked(True)
        lay.addWidget(self.rb_copy)
        rd = QHBoxLayout()
        self.dir = LineEdit(self); self.dir.setPlaceholderText("选择输出目录")
        self.browse = PushButton("浏览…", self, FIF.FOLDER)
        rd.addWidget(self.dir, 1); rd.addWidget(self.browse)
        lay.addLayout(rd)

        self.rb_in = RadioButton("原地重命名（直接改原文件名，不可撤销）", self)
        self.rb_in.setStyleSheet("color:#c42b1c;")
        lay.addWidget(self.rb_in)

        self.rb_cam = RadioButton("直接导入相机（自动接续相机里已有的编号）", self)
        lay.addWidget(self.rb_cam)
        camcard = CardWidget(self)
        cl = QHBoxLayout(camcard)
        cl.setContentsMargins(14, 10, 14, 10); cl.setSpacing(10)
        self.cam_label = CaptionLabel("正在查找相机…", camcard)
        self.cam_label.setWordWrap(True)
        self.cam_refresh = PushButton("重新检测", camcard, FIF.SYNC)
        cl.addWidget(self.cam_label, 1); cl.addWidget(self.cam_refresh)
        lay.addWidget(camcard)

        lay.addWidget(StrongBodyLabel("目标位置已存在同名文件时", self))
        self.conflict = ComboBox(self); self.conflict.addItems(["跳过", "覆盖", "中止并报错"])
        lay.addWidget(self.conflict)
        lay.addStretch(1)
        self.btn_run = PrimaryPushButton("执行重命名", self, FIF.ACCEPT)
        self.btn_run.setFixedHeight(40); self.btn_run.setMinimumWidth(200)
        lay.addWidget(self.btn_run, 0, Qt.AlignRight)

        self.browse.clicked.connect(self._pick)
        self.cam_refresh.clicked.connect(lambda: self.refresh_camera(autofill=True))
        for rb in (self.rb_copy, self.rb_in, self.rb_cam):
            rb.toggled.connect(self._onmode)
        self.load_defaults()

    def mode(self) -> str:
        if self.rb_cam.isChecked(): return "camera"
        if self.rb_in.isChecked(): return "inplace"
        return "copy"

    def load_defaults(self, d: dict = None):
        d = d or DEFAULT_SETTINGS["rename_out"]
        self.dir.setText(d.get("dir", ""))
        self.conflict.setCurrentIndex(d.get("conflict", 0))
        self.refresh_camera()
        m = d.get("mode", "copy")
        if m == "camera" and self.camera:
            self.rb_cam.setChecked(True)   # 触发 _onmode，自动接续编号
        elif m == "inplace":
            self.rb_in.setChecked(True)
        else:
            self.rb_copy.setChecked(True)
        self._onmode()

    def to_dict(self) -> dict:
        return {
            "mode": self.mode(),
            "dir": self.dir.text(),
            "conflict": self.conflict.currentIndex(),
        }

    def refresh_camera(self, autofill=False):
        """扫描相机。autofill=True 时把识别结果发给命名规则页。"""
        cams = scan_cameras()
        self.camera = cams[0] if cams else None
        if self.camera:
            c = self.camera
            tip = (f"{c.drive}  ·  DCIM\\{c.folder}  ·  已有 {c.count} 张，"
                   f"最后一张 {c.last_file}  →  下一张 {c.next_name}")
            if c.overflow:
                tip += "\n⚠ 编号将超出当前位数，建议调大位数或更换目录"
            self.cam_label.setText(tip)
            self.cam_label.setStyleSheet("color:#0067c0;")
            self.rb_cam.setEnabled(True)
            if autofill:
                self.cameraDetected.emit(c)
        else:
            self.cam_label.setText("未检测到相机：连接相机或插入存储卡后点「重新检测」")
            self.cam_label.setStyleSheet("color:#888888;")
            self.rb_cam.setEnabled(False)
            if self.rb_cam.isChecked():
                self.rb_copy.setChecked(True)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d: self.dir.setText(d)

    def _onmode(self, *a):
        m = self.mode()
        self.dir.setEnabled(m == "copy")
        self.browse.setEnabled(m == "copy")
        self.conflict.setEnabled(m != "inplace")
        self.btn_run.setText("导入到相机" if m == "camera" else "执行重命名")
        if m == "camera":
            self.refresh_camera(autofill=True)


# ---------------------------------------------------------------------------
# 替换页
# ---------------------------------------------------------------------------
class ReplacePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.old: list[FileItem] = []
        self.new: list[FileItem] = []
        self.ok = "name"; self.oasc = True
        self.nk = "name"; self.nasc = True
        self._build(); self.setAcceptDrops(True)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16); lay.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(10)
        # 左
        lc = QVBoxLayout()
        lc.addWidget(StrongBodyLabel("旧文件（保留文件名）", self))
        lb = QHBoxLayout()
        self.oa = PushButton("添加", self, FIF.FOLDER)
        self.od = PushButton("文件夹", self, FIF.IOT)
        self.oc = PushButton("清空", self, FIF.CANCEL)
        self.os = ComboBox(self)
        self.os.addItems(["名称↑", "名称↓", "时间↑", "时间↓", "大小↑", "大小↓"])
        for w in (self.oa, self.od, self.oc): lb.addWidget(w)
        lb.addStretch(1); lb.addWidget(CaptionLabel("排序：", self)); lb.addWidget(self.os)
        lc.addLayout(lb)
        self.ot = TableWidget(self); make_table(self.ot, ["#", "文件名", "大小"])
        lc.addWidget(self.ot, 1)
        top.addLayout(lc, 1)
        # 右
        rc = QVBoxLayout()
        rc.addWidget(StrongBodyLabel("新文件（提供内容）", self))
        rb = QHBoxLayout()
        self.na = PushButton("添加", self, FIF.FOLDER)
        self.nd = PushButton("文件夹", self, FIF.IOT)
        self.nc = PushButton("清空", self, FIF.CANCEL)
        self.ns = ComboBox(self)
        self.ns.addItems(["名称↑", "名称↓", "时间↑", "时间↓", "大小↑", "大小↓"])
        for w in (self.na, self.nd, self.nc): rb.addWidget(w)
        rb.addStretch(1); rb.addWidget(CaptionLabel("排序：", self)); rb.addWidget(self.ns)
        rc.addLayout(rb)
        self.nt = TableWidget(self); make_table(self.nt, ["#", "文件名", "大小"])
        rc.addWidget(self.nt, 1)
        top.addLayout(rc, 1)
        lay.addLayout(top, 2)

        lay.addWidget(StrongBodyLabel("对应关系", self))
        self.mt = TableWidget(self)
        make_table(self.mt, ["#", "旧文件（保留名）", "←", "新文件（内容来源）"])
        lay.addWidget(self.mt, 2)

        bot = QHBoxLayout()
        self.bak = CheckBox("替换前备份旧文件", self)
        self.bak.setChecked(False)
        bot.addWidget(self.bak)
        bot.addStretch(1)
        self.run = PrimaryPushButton("执行替换", self, FIF.ACCEPT)
        self.run.setFixedHeight(38); bot.addWidget(self.run)
        lay.addLayout(bot)

        # 备份目录行
        brow = QHBoxLayout()
        brow.addWidget(CaptionLabel("备份目录（留空=旧文件旁 _backup_时间戳）：", self))
        self.bakdir = LineEdit(self)
        self.bakdir.setPlaceholderText("留空则自动在旧文件旁边建备份目录")
        self.bakbrowse = PushButton("浏览…", self, FIF.FOLDER)
        brow.addWidget(self.bakdir, 1); brow.addWidget(self.bakbrowse)
        lay.addLayout(brow)
        self.bakbrowse.clicked.connect(self._pick_bakdir)
        self.bak.toggled.connect(lambda: self.bakdir.setEnabled(self.bak.isChecked()))
        self.bakdir.setEnabled(False)

        self.oa.clicked.connect(lambda: self._pick(self.old, "选择旧文件"))
        self.od.clicked.connect(lambda: self._pick_dir(self.old))
        self.oc.clicked.connect(lambda: self._clear(self.old))
        self.na.clicked.connect(lambda: self._pick(self.new, "选择新文件"))
        self.nd.clicked.connect(lambda: self._pick_dir(self.new))
        self.nc.clicked.connect(lambda: self._clear(self.new))
        self.os.currentIndexChanged.connect(lambda i: self._sort(i, "old"))
        self.ns.currentIndexChanged.connect(lambda i: self._sort(i, "new"))
        self.run.clicked.connect(self._exec)
        self.load_defaults()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        paths = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if not p: continue
            if os.path.isdir(p):
                for r, _, fs in os.walk(p):
                    for f in fs: paths.append(os.path.join(r, f))
            elif os.path.isfile(p):
                paths.append(p)
        if add_paths(self.old, paths):
            sort_items(self.old, self.ok, self.oasc); self._refresh()

    def _pick(self, items, title):
        fs, _ = QFileDialog.getOpenFileNames(self, title, "")
        if add_paths(items, fs): self._refresh()

    def _pick_dir(self, items):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not d: return
        paths = []
        for r, _, fs in os.walk(d):
            for f in fs: paths.append(os.path.join(r, f))
        if add_paths(items, paths): self._refresh()

    def _clear(self, items):
        items.clear(); self._refresh()

    def _sort(self, idx, side):
        km = [("name", True), ("name", False), ("mtime", True),
              ("mtime", False), ("size", True), ("size", False)]
        k, a = km[idx]
        if side == "old":
            self.ok, self.oasc = k, a; sort_items(self.old, k, a)
        else:
            self.nk, self.nasc = k, a; sort_items(self.new, k, a)
        self._refresh()

    def _fill(self, table: TableWidget, items: list[FileItem]):
        table.setRowCount(len(items))
        for i, it in enumerate(items):
            for c, v in enumerate([str(i + 1), it.name, size_str(it.size)]):
                item = QTableWidgetItem(v)
                if c == 0: item.setTextAlignment(Qt.AlignCenter)
                table.setItem(i, c, item)

    def _refresh(self):
        self._fill(self.ot, self.old)
        self._fill(self.nt, self.new)
        n = max(len(self.old), len(self.new))
        self.mt.setRowCount(n)
        for i in range(n):
            o = self.old[i].name if i < len(self.old) else "—"
            nw = self.new[i].name if i < len(self.new) else "—"
            arrow = "←" if (i < len(self.old) and i < len(self.new)) else ""
            for c, v in enumerate([str(i + 1), o, arrow, nw]):
                item = QTableWidgetItem(v)
                if c in (0, 2): item.setTextAlignment(Qt.AlignCenter)
                self.mt.setItem(i, c, item)

    def _exec(self):
        if not self.old:
            InfoBar.warning("空", "请先添加旧文件", self, position=InfoBarPosition.TOP, duration=2500); return
        if not self.new:
            InfoBar.warning("空", "请先添加新文件", self, position=InfoBarPosition.TOP, duration=2500); return
        pairs = min(len(self.old), len(self.new))
        eo = len(self.old) - pairs
        en = len(self.new) - pairs
        msg = f"将替换 {pairs} 个文件。"
        if eo > 0: msg += f"\n{eo} 个旧文件无对应新文件，将保留不动。"
        if en > 0: msg += f"\n{en} 个新文件无对应旧文件，将被忽略。"
        if not self.bak.isChecked(): msg += "\n\n⚠ 未开启备份，旧文件将被直接覆盖！"
        ret = QMessageBox.question(self, "确认替换", msg,
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes: return

        bdir = None
        if self.bak.isChecked():
            custom = self.bakdir.text().strip()
            if custom:
                bdir = custom
            else:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                bdir = os.path.join(os.path.dirname(self.old[0].path), f"_backup_{ts}")
            os.makedirs(bdir, exist_ok=True)

        ok = fail = 0
        for i in range(pairs):
            old = self.old[i].path; new = self.new[i].path
            try:
                if bdir:
                    shutil.copy2(old, os.path.join(bdir, os.path.basename(old)))
                shutil.copy2(new, old)
                ok += 1
            except OSError as e:
                fail += 1; print("replace failed:", e)
        InfoBar.success("完成",
                        f"替换成功 {ok} 个，失败 {fail} 个" +
                        (f"，备份在 {bdir}" if bdir else ""),
                        self, position=InfoBarPosition.TOP, duration=5000)

    def _pick_bakdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择备份目录")
        if d: self.bakdir.setText(d)

    def load_defaults(self, d: dict = None):
        d = d or DEFAULT_SETTINGS["replace"]
        self.bak.blockSignals(True); self.bak.setChecked(d.get("backup", False)); self.bak.blockSignals(False)
        self.bakdir.blockSignals(True); self.bakdir.setText(d.get("backup_dir", "")); self.bakdir.blockSignals(False)
        self.bakdir.setEnabled(self.bak.isChecked())

    def to_dict(self) -> dict:
        return {"backup": self.bak.isChecked(), "backup_dir": self.bakdir.text()}


# ---------------------------------------------------------------------------
# 设置 / 关于
# ---------------------------------------------------------------------------
class SettingsPage(QWidget):
    resetRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20); root.setSpacing(16)

        # —— 关于项目卡片 ——
        card1 = CardWidget(self)
        l1 = QVBoxLayout(card1)
        l1.setContentsMargins(20, 16, 20, 16); l1.setSpacing(8)
        l1.addWidget(StrongBodyLabel("关于项目", self))
        l1.addWidget(BodyLabel(f"{APP_TITLE} v1.5", self))
        l1.addWidget(CaptionLabel("相机照片批量重命名 + 批量替换内容工具", self))
        l1.addWidget(CaptionLabel("支持识别相机存储卡，自动接续编号并直接导入", self))
        l1.addWidget(CaptionLabel("字体：OPPO Sans（免费商用）", self))
        l1.addWidget(CaptionLabel("作者：yelina123", self))
        link = HyperlinkLabel("GitHub 仓库", self); link.setUrl(GITHUB_URL)
        l1.addWidget(link)
        root.addWidget(card1)

        # —— 数据管理卡片 ——
        card2 = CardWidget(self)
        l2 = QVBoxLayout(card2)
        l2.setContentsMargins(20, 16, 20, 16); l2.setSpacing(8)
        l2.addWidget(StrongBodyLabel("数据管理", self))
        l2.addWidget(BodyLabel("所有设置（前缀、后缀、起始号、输出目录、备份开关等）会自动保存在用户目录下，下次打开自动恢复。", self))
        self.btn_reset = PushButton("一键恢复默认设置", self)
        self.btn_reset.setStyleSheet("color:#c42b1c; padding:6px 16px;")
        self.btn_reset.setFixedWidth(180)
        self.btn_reset.clicked.connect(self._confirm_reset)
        l2.addWidget(self.btn_reset, 0, Qt.AlignLeft)
        root.addWidget(card2)

        root.addStretch(1)

    def _confirm_reset(self):
        ret = QMessageBox.question(self, "恢复默认",
                                  "将清空所有自定义设置（前缀、目录、备份开关等），恢复成首次启动状态。继续？",
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            self.resetRequested.emit()


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 750)

        self.home = HomePage(self)
        self.rf = RenameFilePage(self)
        self.rr = RenameRulePage(self)
        self.ro = RenameOutputPage(self)
        self.rp = ReplacePage(self)
        self.st = SettingsPage(self)
        for p, n in [(self.home, "home"), (self.rf, "rf"), (self.rr, "rr"),
                     (self.ro, "ro"), (self.rp, "rp"), (self.st, "st")]:
            p.setObjectName(n)

        self.addSubInterface(self.home, FIF.HOME, "主页")
        self.addSubInterface(self.rf, FIF.FOLDER, "重命名：文件")
        self.addSubInterface(self.rr, FIF.EDIT, "重命名：规则")
        self.addSubInterface(self.ro, FIF.SAVE, "重命名：输出")
        self.addSubInterface(self.rp, FIF.SYNC, "批量替换")
        self.addSubInterface(self.st, FIF.SETTING, "设置", position=NavigationItemPosition.BOTTOM)

        self.rf.itemsChanged.connect(self._rp)
        self.rr.ruleChanged.connect(self._rp)
        self.ro.btn_run.clicked.connect(self._run_rename)
        self.ro.cameraDetected.connect(self._apply_camera)
        self.home.goRename.connect(lambda: self.stackedWidget.setCurrentWidget(self.rf))
        self.home.goReplace.connect(lambda: self.stackedWidget.setCurrentWidget(self.rp))
        self.st.resetRequested.connect(self._reset_settings)

        # 加载上次设置
        s = load_settings()
        self.rr.load_defaults(s.get("rename", {}))
        self.ro.load_defaults(s.get("rename_out", {}))
        self.rp.load_defaults(s.get("replace", {}))
        self._rp()

    def _apply_camera(self, cam):
        self.rr.apply_camera(cam)
        self._rp()
        InfoBar.success(
            "已接续相机编号",
            f"前缀 {cam.prefix} · {cam.digits} 位 · 起始 {cam.next_num} · 扩展名 {cam.ext}",
            self, position=InfoBarPosition.TOP, duration=4000)

    def _reset_settings(self):
        import shutil as _sh
        defaults = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.rr.load_defaults(defaults["rename"])
        self.ro.load_defaults(defaults["rename_out"])
        self.rp.load_defaults(defaults["replace"])
        save_settings(defaults)
        self._rp()
        InfoBar.success("已恢复默认", "所有设置已重置", self,
                        position=InfoBarPosition.TOP, duration=2500)

    def closeEvent(self, e):
        try:
            save_settings({
                "rename": self.rr.to_dict(),
                "rename_out": self.ro.to_dict(),
                "replace": self.rp.to_dict(),
            })
        except Exception:
            pass
        super().closeEvent(e)

    def _rp(self):
        items = self.rf.items
        names = [self.rr.compute(i, it.ext) for i, it in enumerate(items)]
        self.rf.refresh(names)
        if items: self.rr.refresh_preview(items[0].ext)

    def _run_rename(self):
        items = self.rf.items
        if not items:
            InfoBar.warning("空", "请先添加照片", self, position=InfoBarPosition.TOP, duration=2500); return
        s = self.rr.start.value(); e = self.rr.end.value()
        if e > 0 and s > e:
            InfoBar.error("号段错误", "起始号不能大于终止号", self, position=InfoBarPosition.TOP, duration=3000); return
        if e > 0 and len(items) > (e - s + 1):
            InfoBar.error("号段不足", f"需要 {len(items)} 个编号，但 {s}~{e} 只有 {e-s+1} 个",
                          self, position=InfoBarPosition.TOP, duration=3500); return
        if self.ro.rb_copy.isChecked(): self._rename_copy(items)
        elif self.ro.rb_in.isChecked(): self._rename_inplace(items)
        else: self._rename_to_camera(items)

    def _rename_copy(self, items):
        d = self.ro.dir.text().strip()
        if not d:
            InfoBar.warning("未选目录", "请先选择输出目录", self, position=InfoBarPosition.TOP, duration=2500); return
        os.makedirs(d, exist_ok=True)
        mode = self.ro.conflict.currentIndex()
        ok = sk = fl = 0
        for i, it in enumerate(items):
            nn = self.rr.compute(i, it.ext)
            t = os.path.join(d, nn)
            if os.path.exists(t):
                if mode == 0: sk += 1; continue
                if mode == 2:
                    InfoBar.error("冲突中止", f"目标已存在：{t}", self, position=InfoBarPosition.TOP, duration=4000); return
            try: shutil.copy2(it.path, t); ok += 1
            except OSError: fl += 1
        InfoBar.success("完成", f"复制成功 {ok} 个，跳过 {sk} 个，失败 {fl} 个",
                        self, position=InfoBarPosition.TOP, duration=3500)

    def _rename_inplace(self, items):
        ret = QMessageBox.warning(self, "确认", "将直接修改原文件名，不可撤销。继续？",
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes: return
        for i, it in enumerate(items):
            nn = self.rr.compute(i, it.ext)
            t = os.path.join(os.path.dirname(it.path), nn)
            if os.path.exists(t) and os.path.abspath(t) != os.path.abspath(it.path):
                InfoBar.error("冲突", f"目标名 {nn} 已存在", self, position=InfoBarPosition.TOP, duration=4000); return
        tmp = []
        for i, it in enumerate(items):
            nn = self.rr.compute(i, it.ext)
            tp = os.path.join(os.path.dirname(it.path), f"__tmp_{i:05d}__{it.ext}")
            try:
                os.rename(it.path, tp)
                tmp.append((tp, os.path.join(os.path.dirname(it.path), nn)))
            except OSError as ex:
                InfoBar.error("失败", str(ex), self, position=InfoBarPosition.TOP, duration=4000); return
        ok = fl = 0
        for a, b in tmp:
            try: os.rename(a, b); ok += 1
            except OSError: fl += 1
        InfoBar.success("完成", f"原地重命名成功 {ok} 个，失败 {fl} 个",
                        self, position=InfoBarPosition.TOP, duration=3500)

    def _rename_to_camera(self, items):
        cam = self.ro.camera
        if not cam:
            InfoBar.error("未检测到相机", "请连接相机或插入存储卡后点「重新检测」",
                          self, position=InfoBarPosition.TOP, duration=3500); return

        names = [self.rr.compute(i, it.ext) for i, it in enumerate(items)]
        dup = len({n.lower() for n in names}) != len(names)
        cmode = self.ro.conflict.currentText()
        last_no = self.rr.start.value() + len(items) - 1
        over = self.rr.zfill.isChecked() and last_no >= 10 ** self.rr.digits.value()

        msg = (f"将把 {len(items)} 个文件导入相机：\n{cam.root}\n\n"
               f"首个：{names[0]}\n末个：{names[-1]}\n同名处理：{cmode}\n\n"
               "原文件不会被修改，只往相机里复制。")
        if over:
            msg += f"\n\n⚠ 末尾编号 {last_no} 超出 {self.rr.digits.value()} 位数的上限，相机可能不认。"
        if dup:
            msg += "\n\n⚠ 生成的文件名有重复，请检查位数/起始号设置！"
        ret = QMessageBox.question(self, "导入到相机", msg,
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes: return

        mode = self.ro.conflict.currentIndex()
        ok = sk = fl = 0
        for i, it in enumerate(items):
            t = os.path.join(cam.root, names[i])
            if os.path.exists(t):
                if mode == 0: sk += 1; continue
                if mode == 2:
                    InfoBar.error("冲突中止", f"相机里已存在：{names[i]}",
                                  self, position=InfoBarPosition.TOP, duration=5000); return
            try:
                shutil.copy2(it.path, t); ok += 1
            except OSError as e:
                fl += 1
                print("import to camera failed:", e)

        if ok:
            self.ro.refresh_camera()   # 刷新"最后一号"，方便连续导入
        InfoBar.success("导入完成",
                        f"成功 {ok} 个，跳过 {sk} 个，失败 {fl} 个 → {cam.folder}",
                        self, position=InfoBarPosition.TOP, duration=4500)


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    fp = resource_path(os.path.join("assets", "fonts", "OPPOSans-Regular.ttf"))
    fam = "Microsoft YaHei UI"
    if os.path.exists(fp):
        fid = QFontDatabase.addApplicationFont(fp)
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams: fam = fams[0]
    app.setFont(QFont(fam, 10))
    setTheme(Theme.LIGHT)
    win = MainWindow(); win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
