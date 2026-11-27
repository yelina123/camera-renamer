# -*- coding: utf-8 -*-
"""端到端测试：假相机 + 自动接续编号 + 真实写文件 + 自然排序。"""
import os
import sys
import tempfile
import time
import importlib.util

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_HOME = tempfile.mkdtemp()
os.environ["HOME"] = _HOME                      # 避免污染真实设置文件

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from PySide6.QtWidgets import QApplication, QMessageBox

spec = importlib.util.spec_from_file_location("renamer_main", os.path.join(REPO, "main.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["renamer_main"] = m
spec.loader.exec_module(m)

app = QApplication(sys.argv)


def build_dirs(base):
    cam = os.path.join(base, "CAM", "DCIM", "100MEDIA")
    os.makedirs(cam)
    for i in [7, 20, 21, 28]:
        open(os.path.join(cam, f"100_{i:04d}.jpeg"), "w").close()
    photos = os.path.join(base, "photos")
    os.makedirs(photos)
    names = ["幻灯片 10.jpg", "幻灯片 1.jpg", "幻灯片 11.jpg", "幻灯片 2.jpg", "幻灯片 3.jpg"]
    for n in names:
        with open(os.path.join(photos, n), "w", encoding="utf-8") as f:
            f.write("content:" + n)
    return cam, photos, names


def test_import_to_camera():
    base = tempfile.mkdtemp()
    cam, photos, names = build_dirs(base)
    os.environ["CAMERA_TEST_ROOT"] = os.path.join(base, "CAM") + os.sep

    w = m.MainWindow()
    w.resize(1100, 750)
    w.show()
    app.processEvents()

    # 1) 加入文件，检查自然排序
    w.rf._add([os.path.join(photos, n) for n in names])
    assert [i.name for i in w.rf.items] == [
        "幻灯片 1.jpg", "幻灯片 2.jpg", "幻灯片 3.jpg", "幻灯片 10.jpg", "幻灯片 11.jpg"
    ], [i.name for i in w.rf.items]
    print("  [OK] 文件列表按自然排序")

    # 2) 切到相机模式，应自动接续编号
    w.ro.rb_cam.setChecked(True)
    app.processEvents()
    assert w.ro.camera is not None
    assert w.rr.prefix.text() == "100_", w.rr.prefix.text()
    assert w.rr.digits.value() == 4
    assert w.rr.start.value() == 29
    assert w.rr.forcext.text() == ".jpeg"
    print("  [OK] 自动填好 100_ / 4 位 / 起始 29 / .jpeg")

    # 3) 预览名正确
    preview = [w.rr.compute(i, it.ext) for i, it in enumerate(w.rf.items)]
    assert preview[0] == "100_0029.jpeg", preview[0]
    assert preview[-1] == "100_0033.jpeg", preview[-1]
    assert len(set(preview)) == len(preview), "重名"
    print(f"  [OK] 预览 {preview[0]} … {preview[-1]}")

    # 4) 绕过确认框，真正执行导入
    orig = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        w._run_rename()
    finally:
        QMessageBox.question = orig

    for i, name in enumerate(preview):
        p = os.path.join(cam, name)
        assert os.path.isfile(p), f"未生成 {name}"
        src = os.path.basename(w.rf.items[i].path)
        with open(p, encoding="utf-8") as f:
            assert f.read() == "content:" + src, f"{name} 内容应来自 {src}"
    print("  [OK] 5 个文件已按序号写入相机，内容与源文件一一对应")

    # 5) 原文件未被改动
    for n in names:
        assert os.path.isfile(os.path.join(photos, n))
    print("  [OK] 源文件保持原样")

    # 6) 相机里原有文件还在，且最后一号已刷新
    assert os.path.isfile(os.path.join(cam, "100_0028.jpeg"))
    assert w.ro.camera.last_num == 33, w.ro.camera.last_num
    print(f"  [OK] 刷新后最后一号 = {w.ro.camera.last_num}，下一张 {w.ro.camera.next_name}")

    # 7) 再导入一次，默认“跳过”不应覆盖
    assert w.ro.conflict.currentIndex() == 0
    print("  [OK] 冲突策略默认跳过")

    w.close()


if __name__ == "__main__":
    print("端到端：相机导入")
    test_import_to_camera()
    print("\n全部通过")
