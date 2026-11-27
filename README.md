# 相机照片批量重命名工具

Windows 10 / 11 下的 GUI 批量重命名工具，专为「往相机里导图片」设计：识别相机存储卡、自动接续编号、一键导入。

## 下载

直接下打包好的 Windows 版：[Releases](https://github.com/yelina123/camera-renamer/releases/latest)
（`camera-renamer-windows-x64.zip`，解压后双击 `camera-renamer/camera-renamer.exe`，不用装 Python）

## 功能

- 拖入照片，或选择一个文件夹批量处理
- 排序：按名称（自然排序，`幻灯片 2` 排在 `幻灯片 10` 前）/ 修改时间 / 大小，升降序
- 命名规则：前缀（分隔符直接写在前缀里，如 `DSC_`）、起始号、终止号、数字位数（`001` / `1` 两种风格）
- **从示例文件识别**：选一张现有照片，自动解析前缀与位数
- **识别相机**：插入存储卡后自动识别 `X:\DCIM\100MEDIA\100_0123.jpeg` 结构，
  读出相机里最后一号，自动填好前缀 / 位数 / 起始号 / 扩展名
- 输出模式：
  - **复制到新目录**（默认，原文件不动）
  - **直接导入相机**（接续编号后写回相机存储卡）
  - 原地重命名（两阶段改名防冲突，需二次确认）
- 目标已存在同名文件：跳过 / 覆盖 / 中止
- 批量替换内容：保留旧文件名，只换内容，左右两栏各自排序后一一对应
- 设置自动保存（前缀、目录、备份开关等），一键恢复默认
- OPPO Sans 字体内嵌，高 DPI 自动缩放

## 运行

```bash
pip install PySide6 PySide6-Fluent-Widgets
python main.py
```

## 打包 exe

```bash
pip install pyinstaller
python -m PyInstaller -w -n camera-renamer --noconfirm --add-data "assets/fonts;assets/fonts" main.py
```

产物在 `dist/camera-renamer/`，整个目录复制到任意 Windows 电脑即可运行。
也可以直接推送到 GitHub，由 `.github/workflows/build-windows.yml` 自动构建。

## 测试

```bash
python tests/test_logic.py   # 自然排序 + 相机目录识别
python tests/test_gui.py     # 端到端：识别相机→自动编号→真实写文件
```

## 字体

[OPPO Sans 4.0](https://open.oppomobile.com/wiki/new-doc/detail.json?doc_id=13223) 免费商用，版权归 OPPO 广东移动通信有限公司所有。
