# -*- coding: utf-8 -*-
"""不依赖 GUI 的逻辑自测：自然排序 + 相机识别。"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 直接导入 main.py 会拉起 Qt，这里复制最小实现做校验，
# 同时再导入真实模块的函数做一致性检查。
import importlib.util

spec = importlib.util.spec_from_file_location(
    "renamer_main", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["renamer_main"] = mod
spec.loader.exec_module(mod)


def test_natural_key():
    names = ["幻灯片 10.jpg", "幻灯片 1.jpg", "幻灯片 11.jpg", "幻灯片 2.jpg", "幻灯片 3.jpg"]
    got = sorted(names, key=mod.natural_key)
    want = ["幻灯片 1.jpg", "幻灯片 2.jpg", "幻灯片 3.jpg", "幻灯片 10.jpg", "幻灯片 11.jpg"]
    assert got == want, f"自然排序错误: {got}"
    print("  [OK] 幻灯片 1/2/3/10/11 顺序正确")

    got2 = sorted(["DSC_0123.JPG", "DSC_99.JPG", "DSC_100.JPG"], key=mod.natural_key)
    assert got2 == ["DSC_99.JPG", "DSC_100.JPG", "DSC_0123.JPG"], got2
    print("  [OK] DSC_99 < DSC_100 < DSC_0123")

    got3 = sorted(["a10b10.jpg", "a10b2.jpg"], key=mod.natural_key)
    assert got3 == ["a10b2.jpg", "a10b10.jpg"], got3
    print("  [OK] 多段数字 a10b2 < a10b10")


def test_sort_items():
    with tempfile.TemporaryDirectory() as d:
        for n in ["幻灯片 10.jpg", "幻灯片 1.jpg", "幻灯片 2.jpg"]:
            open(os.path.join(d, n), "w").close()
        items = [mod.FileItem(os.path.join(d, n)) for n in
                 ["幻灯片 10.jpg", "幻灯片 1.jpg", "幻灯片 2.jpg"]]
        mod.sort_items(items, "name", True)
        assert [i.name for i in items] == ["幻灯片 1.jpg", "幻灯片 2.jpg", "幻灯片 10.jpg"], \
            [i.name for i in items]
        print("  [OK] sort_items 名称升序走自然排序")


def test_camera_scan():
    with tempfile.TemporaryDirectory() as root:
        dcim = os.path.join(root, "DCIM")
        old = os.path.join(dcim, "101MEDIA")
        cur = os.path.join(dcim, "100MEDIA")
        os.makedirs(old); os.makedirs(cur)

        # 较老的目录：101MEDIA
        for i in range(1, 4):
            p = os.path.join(old, f"101_{i:04d}.jpeg")
            open(p, "w").close()
            os.utime(p, (time.time() - 86400, time.time() - 86400))
        os.utime(old, (time.time() - 86400, time.time() - 86400))

        # 当前目录：100MEDIA，最大编号 128
        for i in [120, 121, 128]:
            open(os.path.join(cur, f"100_{i:04d}.jpeg"), "w").close()
        open(os.path.join(cur, "说明.txt"), "w").close()   # 非图片应被忽略

        found = mod.scan_cameras([root + os.sep])
        assert len(found) == 1, found
        c = found[0]
        assert c.folder == "100MEDIA", c.folder
        assert c.prefix == "100_", c.prefix
        assert c.digits == 4, c.digits
        assert c.last_num == 128, c.last_num
        assert c.count == 3, c.count
        assert c.next_name == "100_0129.jpeg", c.next_name
        assert not c.overflow
        print(f"  [OK] 识别 {c.folder}: 前缀={c.prefix} 位数={c.digits} "
              f"最后一号={c.last_num} 下一张={c.next_name}")

        # 无 DCIM 的盘符应返回空
        assert mod.scan_cameras([os.path.join(root, "nope") + os.sep]) == []
        print("  [OK] 无 DCIM 目录时返回空")


def test_overflow():
    with tempfile.TemporaryDirectory() as root:
        d = os.path.join(root, "DCIM", "100MEDIA")
        os.makedirs(d)
        open(os.path.join(d, "100_9999.jpeg"), "w").close()
        c = mod.scan_cameras([root + os.sep])[0]
        assert c.overflow, "9999 下一号应提示溢出"
        assert c.next_num == 10000
        print("  [OK] 编号溢出检测正常")


if __name__ == "__main__":
    print("自然排序："); test_natural_key()
    print("列表排序："); test_sort_items()
    print("相机识别："); test_camera_scan()
    print("溢出检测："); test_overflow()
    print("\n全部通过")
