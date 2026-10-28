# 相机照片批量重命名工具

一个 Windows 10 / 11 下的 GUI 批量重命名工具，专为导入相机图片到相机卡时的命名规则设计（前缀 + 递增数字）。

## 功能

- 拖入一堆照片，或选择一个文件夹批量处理
- 排序方式：按名称 / 修改时间 / 大小，升序降序
- 命名规则：自定义前缀、分隔符、起始号、终止号、数字位数（001 / 1 两种风格都支持）
- 输出模式：
  - **复制到新目录**（默认，原文件不动）
  - 原地重命名（两阶段改名防冲突，需二次确认）
- 目标目录冲突策略：跳过 / 覆盖 / 中止
- OPPO Sans 字体内嵌，高 DPI 自动缩放
- 实时预览新文件名

## 运行

```bash
pip install PySide6 PySide6-Fluent-Widgets
python main.py
```

## 打包 exe

```bash
pip install pyinstaller
pyinstaller -w -F --add-data "assets/fonts;assets/fonts" main.py
```

## 字体

[OPPO Sans 4.0](https://open.oppomobile.com/wiki/new-doc/detail.json?doc_id=13223) 免费商用，版权归 OPPO 广东移动通信有限公司所有。
