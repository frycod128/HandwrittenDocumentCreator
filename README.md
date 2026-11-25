# A3 随机手写字体文档生成器

读取长文本、手写字体选择列表和每栏行数，输出 A3 横向双栏文档。每个非空白字符从所选字体中随机取一种，独立旋转 `-10°` 到 `+10°`，并在横向和纵向各随机移动最多 `5%` 字高。

## 已支持的素材

- `字体素材/*.gfont`：奎享单线字库，共 80 个文件。
- `A3空白文档.docx`：版式依据为 A3 横向、四边 12.7 mm 页边距、双栏、栏间距 7.5 mm。
- `.gfont` 使用文件末尾内嵌 ZIP 中的逐字矢量笔画，不依赖系统安装同名字体。

## 启动

Windows 下双击 `run_gui.bat`。首次运行会自动在项目内准备环境，无需预先安装任何东西（需要联网）：

1. 依次查找项目内 `.python`、项目内 `.venv`、`py -3`、PATH 上的 `python`；
2. 都找不到时，把官方独立构建的 Python 3.13 下载到项目内 `.python`（约 47 MB），并按固定 SHA-256 校验；
3. 用找到的 Python 在项目内创建 `.venv` 并安装 `requirements.txt`。

之后每次启动只做一次快速自检，环境完好就直接打开界面。整个过程只写项目目录（`.venv`、`.python`、`.cache`）：不安装全局包、不修改 PATH、不写注册表，也不影响其他用户。

其他平台或需要手动控制时：

```powershell
python tools/bootstrap.py --launch-gui   # 图形界面
python tools/bootstrap.py --check        # 只检查环境，不改动文件
python tools/bootstrap.py --rebuild      # 强制重建 .venv
python tools/bootstrap.py --python D:\Python311\python.exe   # 指定基础解释器
```

界面中可粘贴长文本、搜索字体并通过复选框多选、设置每栏行数、随机种子与输出位置。字体列表会动态扫描 `字体素材`，显示复选框、字符数和完整文件名；单字正方形预览始终使用最后勾选的字体。默认同时生成：

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
- 所有 `.gfont` 单线笔画在纸面上固定为 `0.5 mm` 外层宽度，不随字号或每栏行数缩放；边缘以低透明度收窄叠层模拟圆珠笔轻微沁润，中心保持实黑。
- 明示换行会保留；自动换行只发生在字符之间。
- 所选字体都不包含某个字符时，使用系统楷体/黑体回退，并在生成结果中报告数量。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
