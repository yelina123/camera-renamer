# -*- coding: utf-8 -*-
"""
相机照片批量重命名工具
- PySide6 + qfluentwidgets
- OPPO Sans 字体（免费商用）
- 支持拖拽、文件夹选择、排序、前缀+编号命名、复制到新目录/原地重命名
"""
import os
import sys
import shutil
import webbrowser
from dataclasses import dataclass
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase, QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
    QTableWidgetItem, QHeaderView, QMessageBox, QSpinBox, QLabel,
)
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, setTheme, Theme,
    PushButton, ComboBox, CheckBox, LineEdit, BodyLabel,
    CaptionLabel, CardWidget, StrongBodyLabel, InfoBar, InfoBarPosition,
    FluentIcon as FIF, RadioButton, PrimaryPushButton, HyperlinkLabel,
)

APP_TITLE = "相机照片批量重命名"
GITHUB_URL = "https://github.com/yelina123/camera-renamer"


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class FileItem:
    path: str
    new_name: str = ""

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def ext(self) -> str:
        return os.path.splitext(self.path)[1]

    @property
    def size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    @property
    def mtime(self) -> float:
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return 0.0


# ---------------------------------------------------------------------------
# 页面一：文件列表
# ---------------------------------------------------------------------------
class FileListPage(QWidget):
    itemsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[FileItem] = []
        self.sort_key = "name"
        self.sort_asc = True
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        bar = QHBoxLayout()
        self.btn_add_files = PushButton("添加文件", self, FIF.FOLDER)
        self.btn_add_dir = PushButton("添加文件夹", self, FIF.IOT)
        self.btn_remove = PushButton("移除选中", self, FIF.DELETE)
        self.btn_clear = PushButton("清空", self, FIF.CANCEL)
        self.sort_combo = ComboBox(self)
        self.sort_combo.addItems([
            "按名称 ↑", "按名称 ↓",
            "按修改时间 ↑", "按修改时间 ↓",
            "按大小 ↑", "按大小 ↓",
        ])
        self.sort_combo.setCurrentIndex(1)
        bar.addWidget(self.btn_add_files)
        bar.addWidget(self.btn_add_dir)
        bar.addWidget(self.btn_remove)
        bar.addWidget(self.btn_clear)
        bar.addStretch(1)
        bar.addWidget(CaptionLabel("排序方式：", self))
        bar.addWidget(self.sort_combo)
        lay.addLayout(bar)

        from qfluentwidgets import TableWidget
        self.table = TableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "原文件名", "新文件名（预览）", "大小"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(TableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(TableWidget.SelectRows)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        lay.addWidget(self.table, 1)

        self.hint = CaptionLabel("提示：可直接把文件或文件夹拖到本窗口", self)
        self.hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.hint)

        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_dir.clicked.connect(self._pick_dir)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self._clear)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        paths = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if not p:
                continue
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        paths.append(os.path.join(root, f))
            elif os.path.isfile(p):
                paths.append(p)
        self._add_paths(paths)

    def _pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择照片", "")
        self._add_paths(files)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not d:
            return
        paths = []
        for root, _, files in os.walk(d):
            for f in files:
                paths.append(os.path.join(root, f))
        self._add_paths(paths)

    def _add_paths(self, paths):
        existing = {it.path for it in self.items}
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            if p in existing:
                continue
            if os.path.isfile(p):
                self.items.append(FileItem(p))
                existing.add(p)
                added += 1
        if added:
            self._apply_sort()
            self.refresh_table()
            self.itemsChanged.emit()

    def _remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.items):
                self.items.pop(r)
        self.refresh_table()
        self.itemsChanged.emit()

    def _clear(self):
        self.items.clear()
        self.refresh_table()
        self.itemsChanged.emit()

    def _on_sort_changed(self, idx):
        key_map = [
            ("name", True), ("name", False),
            ("mtime", True), ("mtime", False),
            ("size", True), ("size", False),
        ]
        self.sort_key, self.sort_asc = key_map[idx]
        self._apply_sort()
        self.refresh_table()
        self.itemsChanged.emit()

    def _apply_sort(self):
        key_func = {
            "name": lambda it: it.name.lower(),
            "mtime": lambda it: it.mtime,
            "size": lambda it: it.size,
        }[self.sort_key]
        self.items.sort(key=key_func, reverse=not self.sort_asc)

    def refresh_table(self, new_names=None):
        self.table.setRowCount(len(self.items))
        for i, it in enumerate(self.items):
            size_kb = it.size / 1024
            size_txt = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
            nn = new_names[i] if new_names else it.new_name
            vals = [str(i + 1), it.name, nn, size_txt]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, c, item)


# ---------------------------------------------------------------------------
# 页面二：命名规则
# ---------------------------------------------------------------------------
class NamingRulePage(CardWidget):
    ruleChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lay.addWidget(StrongBodyLabel("命名格式", self))

        # 前缀行
        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel("前缀：", self))
        self.prefix = LineEdit(self)
        self.prefix.setPlaceholderText("例如 DSC（可留空）")
        row1.addWidget(self.prefix, 1)
        row1.addWidget(BodyLabel("分隔符：", self))
        self.sep = ComboBox(self)
        self.sep.addItems(["无", "_", "-"])
        row1.addWidget(self.sep)
        lay.addLayout(row1)

        # 编号行（原生 QSpinBox，箭头在右边）
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel("起始号：", self))
        self.start = QSpinBox(self)
        self.start.setRange(1, 999999)
        self.start.setValue(1)
        self.start.setFixedWidth(110)
        row2.addWidget(self.start)

        row2.addWidget(BodyLabel("终止号：", self))
        self.end = QSpinBox(self)
        self.end.setRange(0, 999999)
        self.end.setValue(0)
        self.end.setSpecialValueText("自动")
        self.end.setFixedWidth(110)
        row2.addWidget(self.end)

        self.zfill_cb = CheckBox("补零到", self)
        self.zfill_cb.setChecked(True)
        row2.addWidget(self.zfill_cb)

        self.digits = QSpinBox(self)
        self.digits.setRange(1, 10)
        self.digits.setValue(3)
        self.digits.setFixedWidth(70)
        row2.addWidget(self.digits)
        row2.addWidget(BodyLabel("位", self))
        row2.addStretch(1)
        lay.addLayout(row2)

        # 后缀行
        row3 = QHBoxLayout()
        row3.addWidget(BodyLabel("固定后缀：", self))
        self.fixed_suffix = LineEdit(self)
        self.fixed_suffix.setPlaceholderText("例如 _v2（可留空）")
        self.fixed_suffix.setMaximumWidth(200)
        row3.addWidget(self.fixed_suffix)

        row3.addWidget(BodyLabel("扩展名：", self))
        self.force_ext = LineEdit(self)
        self.force_ext.setPlaceholderText("留空=保留原扩展名，填 .jpg 则强制改")
        self.force_ext.setMaximumWidth(240)
        row3.addWidget(self.force_ext, 1)
        lay.addLayout(row3)

        lay.addWidget(StrongBodyLabel("实时预览", self))
        self.preview = BodyLabel("示例：DSC001.jpg", self)
        self.preview.setStyleSheet("color:#0067c0; font-size:14px;")
        lay.addWidget(self.preview)

        lay.addStretch(1)

        # 信号
        self.prefix.textChanged.connect(self._emit)
        self.sep.currentIndexChanged.connect(self._emit)
        self.start.valueChanged.connect(self._emit)
        self.end.valueChanged.connect(self._emit)
        self.digits.valueChanged.connect(self._emit)
        self.zfill_cb.stateChanged.connect(self._on_zfill_changed)
        self.fixed_suffix.textChanged.connect(self._emit)
        self.force_ext.textChanged.connect(self._emit)
        self._on_zfill_changed()

    def _on_zfill_changed(self):
        self.digits.setEnabled(self.zfill_cb.isChecked())

    def _emit(self, *args):
        self.ruleChanged.emit()

    def compute_new_name(self, index: int, ext: str) -> str:
        n = self.start.value() + index
        prefix = self.prefix.text().strip()
        sep_map = {0: "", 1: "_", 2: "-"}
        sep = sep_map[self.sep.currentIndex()]
        if self.zfill_cb.isChecked():
            num = str(n).zfill(self.digits.value())
        else:
            num = str(n)
        name = f"{prefix}{sep}{num}" if prefix else num
        fs = self.fixed_suffix.text().strip()
        if fs:
            name += fs
        # 扩展名：强制扩展名优先
        fe = self.force_ext.text().strip()
        if fe:
            if not fe.startswith("."):
                fe = "." + fe
            name += fe
        else:
            name += ext
        return name

    def refresh_preview(self, example_ext=".jpg"):
        self.preview.setText(f"示例：{self.compute_new_name(0, example_ext)}")


# ---------------------------------------------------------------------------
# 页面三：输出设置
# ---------------------------------------------------------------------------
class OutputPage(CardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lay.addWidget(StrongBodyLabel("输出位置", self))

        self.rb_copy = RadioButton("复制到新目录（推荐，原文件不动）", self)
        self.rb_copy.setChecked(True)
        lay.addWidget(self.rb_copy)

        row_dir = QHBoxLayout()
        self.dir_edit = LineEdit(self)
        self.dir_edit.setPlaceholderText("选择一个空目录或新目录，重命名后的文件会复制到这里")
        self.btn_browse = PushButton("浏览…", self, FIF.FOLDER)
        row_dir.addWidget(self.dir_edit, 1)
        row_dir.addWidget(self.btn_browse)
        lay.addLayout(row_dir)

        self.rb_inplace = RadioButton("原地重命名（直接修改原文件名，不可撤销）", self)
        self.rb_inplace.setStyleSheet("color:#c42b1c;")
        lay.addWidget(self.rb_inplace)

        lay.addWidget(StrongBodyLabel("目标目录已存在同名文件时", self))
        self.conflict = ComboBox(self)
        self.conflict.addItems(["跳过", "覆盖", "中止并报错"])
        lay.addWidget(self.conflict)

        lay.addStretch(1)

        self.btn_run = PrimaryPushButton("执行重命名", self, FIF.ACCEPT)
        self.btn_run.setFixedHeight(40)
        self.btn_run.setMinimumWidth(200)
        lay.addWidget(self.btn_run, 0, Qt.AlignRight)

        self.btn_browse.clicked.connect(self._pick_dir)
        self.rb_copy.toggled.connect(self._on_mode_changed)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.dir_edit.setText(d)

    def _on_mode_changed(self):
        is_copy = self.rb_copy.isChecked()
        self.dir_edit.setEnabled(is_copy)
        self.btn_browse.setEnabled(is_copy)
        self.conflict.setEnabled(is_copy)


# ---------------------------------------------------------------------------
# 页面四：关于
# ---------------------------------------------------------------------------
class AboutPage(CardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        lay.addWidget(StrongBodyLabel("关于", self))
        lay.addWidget(BodyLabel(APP_TITLE, self))
        lay.addWidget(CaptionLabel("版本 1.0  |  字体：OPPO Sans（免费商用）", self))

        link = HyperlinkLabel("GitHub 仓库", self)
        link.setUrl(GITHUB_URL)
        lay.addWidget(link)

        lay.addStretch(1)


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1000, 700)

        self.file_page = FileListPage(self)
        self.rule_page = NamingRulePage(self)
        self.output_page = OutputPage(self)
        self.about_page = AboutPage(self)
        self.file_page.setObjectName("filePage")
        self.rule_page.setObjectName("rulePage")
        self.output_page.setObjectName("outputPage")
        self.about_page.setObjectName("aboutPage")

        self.addSubInterface(self.file_page, FIF.FOLDER, "文件列表")
        self.addSubInterface(self.rule_page, FIF.EDIT, "命名规则")
        self.addSubInterface(self.output_page, FIF.SAVE, "输出设置")
        self.addSubInterface(self.about_page, FIF.INFO, "关于",
                            position=NavigationItemPosition.BOTTOM)

        self.file_page.itemsChanged.connect(self._refresh_preview)
        self.rule_page.ruleChanged.connect(self._refresh_preview)
        self.output_page.btn_run.clicked.connect(self._run)

        self._refresh_preview()

    def _refresh_preview(self):
        items = self.file_page.items
        names = [self.rule_page.compute_new_name(i, it.ext) for i, it in enumerate(items)]
        for it, n in zip(items, names):
            it.new_name = n
        self.file_page.refresh_table(names)
        if items:
            self.rule_page.refresh_preview(items[0].ext)

    def _run(self):
        items = self.file_page.items
        if not items:
            InfoBar.warning("空列表", "请先添加照片", self,
                            position=InfoBarPosition.TOP, duration=2500)
            return

        start = self.rule_page.start.value()
        end = self.rule_page.end.value()
        if end > 0 and start > end:
            InfoBar.error("号段错误", "起始号不能大于终止号", self,
                          position=InfoBarPosition.TOP, duration=3000)
            return
        if end > 0 and len(items) > (end - start + 1):
            InfoBar.error("号段不足",
                          f"需要 {len(items)} 个编号，但 {start}~{end} 只有 {end - start + 1} 个",
                          self, position=InfoBarPosition.TOP, duration=3500)
            return

        if self.output_page.rb_copy.isChecked():
            self._run_copy()
        else:
            self._run_inplace()

    def _run_copy(self):
        out_dir = self.output_page.dir_edit.text().strip()
        if not out_dir:
            InfoBar.warning("未选目录", "请先选择输出目录", self,
                            position=InfoBarPosition.TOP, duration=2500)
            return
        os.makedirs(out_dir, exist_ok=True)

        mode = self.output_page.conflict.currentIndex()
        ok = skip = fail = 0
        for it in self.file_page.items:
            target = os.path.join(out_dir, it.new_name)
            if os.path.exists(target):
                if mode == 0:
                    skip += 1
                    continue
                elif mode == 2:
                    InfoBar.error("冲突中止", f"目标已存在：{target}",
                                  self, position=InfoBarPosition.TOP, duration=4000)
                    return
            try:
                shutil.copy2(it.path, target)
                ok += 1
            except OSError as e:
                fail += 1
                print("copy failed:", e)

        InfoBar.success("完成", f"复制成功 {ok} 个，跳过 {skip} 个，失败 {fail} 个",
                        self, position=InfoBarPosition.TOP, duration=3500)

    def _run_inplace(self):
        ret = QMessageBox.warning(
            self, "原地重命名确认",
            "即将直接修改原文件名，不可撤销。建议先备份。\n确定继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        for it in self.file_page.items:
            target = os.path.join(os.path.dirname(it.path), it.new_name)
            if not os.path.exists(target):
                continue
            if os.path.abspath(target) == os.path.abspath(it.path):
                continue
            InfoBar.error("冲突", f"目标名 {it.new_name} 与目录中已有文件冲突",
                          self, position=InfoBarPosition.TOP, duration=4000)
            return

        tmp_map = []
        for i, it in enumerate(self.file_page.items):
            tmp_path = os.path.join(os.path.dirname(it.path),
                                    f"__tmp_rename_{i:05d}__{it.ext}")
            try:
                os.rename(it.path, tmp_path)
                tmp_map.append((tmp_path,
                                os.path.join(os.path.dirname(it.path), it.new_name)))
            except OSError as e:
                for old, _ in tmp_map:
                    try:
                        os.rename(old, old.rsplit("__", 2)[0] + it.ext)
                    except OSError:
                        pass
                InfoBar.error("失败", f"第一阶段改名失败：{e}",
                              self, position=InfoBarPosition.TOP, duration=4000)
                return

        ok = fail = 0
        for tmp_path, final_path in tmp_map:
            try:
                os.rename(tmp_path, final_path)
                ok += 1
            except OSError as e:
                fail += 1
                print("rename failed:", e)

        InfoBar.success("完成", f"原地重命名成功 {ok} 个，失败 {fail} 个",
                        self, position=InfoBarPosition.TOP, duration=3500)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)

    font_path = resource_path(os.path.join("assets", "fonts", "OPPOSans-Regular.ttf"))
    font_family = "Microsoft YaHei UI"
    if os.path.exists(font_path):
        fid = QFontDatabase.addApplicationFont(font_path)
        families = QFontDatabase.applicationFontFamilies(fid)
        if families:
            font_family = families[0]
    app.setFont(QFont(font_family, 10))

    setTheme(Theme.LIGHT)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
