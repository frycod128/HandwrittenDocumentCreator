# A3 随机手写字体文档生成器

读取长文本、手写字体选择列表和每栏行数，输出 A3 横向双栏文档。每个非空白字符从所选字体中随机取一种，独立旋转 `-10°` 到 `+10°`，并在横向和纵向各随机移动最多 `5%` 字高。

## 已支持的素材

- `字体素材/*.gfont`：奎享单线字库，共 80 个文件。
- `A3空白文档.docx`：版式依据为 A3 横向、四边 12.7 mm 页边距、双栏、栏间距 7.5 mm。
- `.gfont` 使用文件末尾内嵌 ZIP 中的逐字矢量笔画，不依赖系统安装同名字体。

## 启动

```powershell
.\.venv-gui\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-gui\Scripts\python.exe main.py
```

也可以双击 `run_gui.bat`。

图形界面需要带 Tcl/Tk 的 Python。项目当前机器上使用：

```powershell
C:\Users\Admin\AppData\Local\Programs\Python\Python310\python.exe -m venv .venv-gui
.\.venv-gui\Scripts\python.exe -m pip install -r requirements.txt
```

命令行生成也继续支持现有 `.venv`。

界面中可粘贴长文本、搜索和多选字体、设置每栏行数、随机种子与输出位置。默认同时生成：

- A3 横向 PDF：矢量笔画，逐字变换完全准确。
- A3 横向 DOCX：每页以高清图片嵌入，版式与 PDF 一致。Word 对“数万个独立旋转字符”的原生支持不稳定，因此 Word 版采用页面图。

## 命令行

```powershell
.\.venv\Scripts\python.exe main.py `
  --input .\examples\示例输入.txt `
  --fonts "常用_kvenjoy_美文.gfont" "超连笔快写-3500字_kvenjoy_gantry.gfont" "楷体_kvenjoy_大孔龙.gfont" `
  --lines 52 `
  --output .\output\示例手写文档.pdf `
  --docx `
  --seed 20261112
```

查看字体及字符覆盖：

```powershell
.\.venv\Scripts\python.exe main.py --list-fonts
```

## 排版规则

- 每页固定两栏，左右栏都按输入的“每栏行数”划分。默认 52 行，建议实际使用范围 46–58 行。
- 文本按左栏自上而下、右栏自上而下、再进入下一页的顺序流动。
- 字号由页面可用高度和每栏行数计算，并根据 10° 旋转与 5% 位移预留安全空间。
- 中文按接近全角宽度排版，英文、数字与标点按实际笔画宽度排版。
- 明示换行会保留；自动换行只发生在字符之间。
- 所选字体都不包含某个字符时，使用系统楷体/黑体回退，并在生成结果中报告数量。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
