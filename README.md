# PSD 图层展示视频生成器

把一张 Photoshop（PSD）分层作品，逐层从底到顶依次展示，渲染成一段带淡入淡出、图层名标注、歌词字幕与背景音乐的视频。

## 功能特性

- **逐层展示**：按图层从底到顶的堆叠顺序，每一步多显示一层，直到完整作品呈现。
- **正确合成**：使用 `psd-tools` 的合成引擎渲染，完整保留混合模式、剪贴蒙版、调整图层效果。
- **图层名标注**：字号、颜色、位置、对齐方式自动取自 PSD 中的示例文字层，无需改代码。
- **淡入淡出**：层与层之间平滑过渡，结尾图层名可淡出、成图可定格。
- **歌词字幕**：支持 LRC 风格歌词文件（原文 + 翻译），样式同样自动取自 PSD 中的歌词文字层。
- **语音识别歌词**：本地 `faster-whisper` 离线识别（99 种语言）或百度短语音在线识别，并自动翻译。
- **背景音乐**：通过 ffmpeg 混入 mp3/mp4 音频，支持音量调节、淡入淡出、循环/裁剪对齐。
- **图形界面**：深色主题 GUI，含歌词预览与编辑、进度条与日志。

## 目录结构

```
g:\script
├── README.md
├── .gitignore                     # 忽略密钥 / 缓存 / 模型权重等
├── download_model.py              # 下载本地 Whisper 模型权重
├── Models
│   └── faster-whisper-small        # 本地 Whisper 模型（离线语音识别）
│       ├── model.bin               # 由 download_model.py 下载，体积大不入库
│       ├── config.json
│       ├── tokenizer.json
│       └── vocabulary.txt
└── mp4
    ├── renderer.py                # 核心渲染与歌词识别逻辑
    ├── gui.py                     # 图形界面
    ├── main.pyw                   # 双击无终端启动 GUI（pythonw）
    ├── baidu_keys.json            # 百度识别/翻译 Key（由 GUI 保存，不入库）
    └── ...                        # 示例 PSD / mp3 / lrc 文件（大素材不入库）
```

## 环境依赖

需要 Python 3.8+，并安装以下包：

```bash
pip install opencv-python numpy Pillow psd-tools requests faster-whisper imageio-ffmpeg
```

> `tkinter` 为 Python 自带；`imageio-ffmpeg` 用于混入背景音乐，`faster-whisper` 用于本地语音识别（可选用百度在线识别替代）。

## 快速开始

### 方式一：图形界面（推荐）

双击 [main.pyw](file:///g:/script/mp4/main.pyw)，或运行：

```bash
python mp4/gui.py
```

1. 选择 PSD 文件，输出视频名会自动生成。
2. 按需设置帧率、每层停留时长、淡入淡出、视频最长边等参数。
3. 可选：选择背景音乐、歌词文件，或点击「语音识别歌词」自动生成歌词。
4. 点击「开始渲染」，等待完成。

### 方式二：命令行

直接编辑 [renderer.py](file:///g:/script/mp4/renderer.py) 顶部的配置参数（`PSD_PATH`、`OUTPUT_VIDEO` 等），然后运行：

```bash
python mp4/renderer.py
```

## 配置说明

核心参数位于 [renderer.py](file:///g:/script/mp4/renderer.py) 顶部的「配置参数」区块：

| 参数 | 说明 |
| --- | --- |
| `PSD_PATH` / `OUTPUT_VIDEO` | 输入 PSD 与输出视频路径 |
| `FPS` | 视频帧率 |
| `HOLD_FRAMES` | 每层出现后停留帧数 |
| `FADE_FRAMES` | 层间淡入淡出帧数 |
| `TEXT_FADE_FRAMES` | 结尾图层名淡出帧数 |
| `ENDING_HOLD_FRAMES` | 结尾成图定格帧数 |
| `BG_COLOR` | 透明区域底色（默认白色） |
| `MAX_SIDE` | 视频最长边像素（默认 2160，`None` 保留原尺寸） |
| `SHOW_LAYER_NAME` | 是否显示当前图层名 |
| `FONT_PATH` | 图层名/歌词字体文件 |
| `LYRICS_FILE` | 歌词文件路径，`None` 不显示 |
| `BG_MUSIC_PATH` / `BG_MUSIC_VOLUME` | 背景音乐与音量（0~1） |
| `AUTO_LYRICS_ENGINE` | `whisper`（本地）或 `baidu`（在线） |
| `WHISPER_MODEL` / `WHISPER_MODEL_PATH` | 本地模型尺寸 / 模型目录 |

## 歌词

### LRC 歌词文件格式

每行 `[mm:ss.xx] 原文 | 翻译`，无 `|` 则不显示翻译：

```
[00:00.00] さよならは今だ | 再见是现在
[00:05.00] あなたの記憶は
```

歌词样式自动取自 PSD 中名称包含「歌词」的文字层（含「翻译」的为翻译层）。

### 自动识别歌词

- **本地（推荐）**：`AUTO_LYRICS_ENGINE='whisper'`，使用 `Models/faster-whisper-small` 离线识别，句级时间戳精确（首次使用前请先运行 `python download_model.py` 下载模型）。
- **在线**：`AUTO_LYRICS_ENGINE='baidu'`，需在 GUI「设置翻译 Key」中配置百度语音识别与翻译凭证（保存于 `baidu_keys.json`）。

## 常见问题

- **中文路径写入失败**：脚本会自动先写临时英文文件名再改名，规避 OpenCV 在 Windows 下的中文路径问题。
- **背景音乐未合成**：请确认已安装 `imageio-ffmpeg`（提供 ffmpeg 可执行文件）。
- **歌词不可见**：请确认 PSD 中存在名称含「歌词」的可见文字层，且歌词文件时间戳格式正确。
- **自动识别无结果**：`whisper` 需本地模型存在或可下载；`baidu` 需凭证完整。
