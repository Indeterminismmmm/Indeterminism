# PSD Layer Reveal Video Generator

Turns a layered Photoshop (PSD) artwork into a video that reveals layers one by one from bottom to top, with cross-fades, layer-name captions, lyric subtitles, and background music.

## Features

- **Layer-by-layer reveal**: Walks the layer stack from bottom to top, revealing one more layer at each step until the complete artwork is shown.
- **Faithful compositing**: Renders with the `psd-tools` compositing engine, preserving blend modes, clipping masks, and adjustment-layer effects.
- **Layer-name captions**: Font size, color, position, and alignment are read automatically from a sample text layer in the PSD — no code changes needed.
- **Cross-fades**: Smooth transitions between layers; the final caption can fade out and the finished artwork can hold on screen.
- **Lyric subtitles**: Supports LRC-style lyric files (original + translation); styling is likewise taken from lyric text layers in the PSD.
- **Speech-to-lyrics**: Offline recognition via a local `faster-whisper` model (99 languages), or online Baidu short-speech recognition — both with automatic translation.
- **Background music**: Muxes mp3/mp4 audio through ffmpeg, with volume control, fade in/out, and loop/trim to match the video length.
- **GUI**: Dark-themed interface with lyric preview and editing, a progress bar, and a log pane.

## Project Structure

```
g:\script
├── README.md
├── .gitignore                     # Ignores keys / caches / model weights
├── download_model.py              # Downloads the local Whisper model weights
├── Models
│   └── faster-whisper-small        # Local Whisper model (offline speech recognition)
│       ├── model.bin               # Downloaded by download_model.py; too large to track
│       ├── config.json
│       ├── tokenizer.json
│       └── vocabulary.txt
└── mp4
    ├── renderer.py                # Core rendering and lyric recognition logic
    ├── gui.py                     # Graphical interface
    ├── main.pyw                   # Double-click to launch the GUI without a console (pythonw)
    ├── baidu_keys.json            # Baidu recognition/translation keys (saved by the GUI, not tracked)
    └── ...                        # Sample PSD / mp3 / lrc files (large assets, not tracked)
```

## Requirements

Requires Python 3.8+ and the following packages:

```bash
pip install opencv-python numpy Pillow psd-tools requests faster-whisper imageio-ffmpeg huggingface-hub
```

> `tkinter` ships with Python. `imageio-ffmpeg` provides the ffmpeg executable used for muxing background music, `faster-whisper` powers local speech recognition (Baidu online recognition can be used instead), and `huggingface-hub` is used by `download_model.py` to fetch the local Whisper model weights.

## Quick Start

### Option 1: GUI (recommended)

Double-click [main.pyw](file:///g:/script/mp4/main.pyw), or run:

```bash
python mp4/gui.py
```

1. Choose a PSD file — the output video name is filled in automatically.
2. Adjust the frame rate, per-layer hold time, fade duration, maximum video side, and other options as needed.
3. Optional: pick background music and a lyric file, or click "语音识别歌词" (Recognize lyrics) to generate the lyrics automatically.
4. Click "开始渲染" (Start rendering) and wait for it to finish.

### Option 2: Command line

Edit the configuration constants at the top of [renderer.py](file:///g:/script/mp4/renderer.py) (`PSD_PATH`, `OUTPUT_VIDEO`, etc.), then run:

```bash
python mp4/renderer.py
```

## Configuration

The main parameters live in the configuration block at the top of [renderer.py](file:///g:/script/mp4/renderer.py):

| Parameter | Description |
| --- | --- |
| `PSD_PATH` / `OUTPUT_VIDEO` | Input PSD path and output video path |
| `FPS` | Video frame rate |
| `HOLD_FRAMES` | Frames each layer stays on screen |
| `FADE_FRAMES` | Frames used for the cross-fade between layers |
| `TEXT_FADE_FRAMES` | Frames used to fade out the layer-name caption at the end |
| `ENDING_HOLD_FRAMES` | Frames the finished artwork holds at the end |
| `BG_COLOR` | Background color for transparent areas (white by default) |
| `MAX_SIDE` | Longest side of the video in pixels (default 2160; `None` keeps the original size) |
| `SHOW_LAYER_NAME` | Whether to show the current layer name |
| `FONT_PATH` | Font file used for layer names and lyrics |
| `LYRICS_FILE` | Path to the lyric file; `None` disables lyrics |
| `BG_MUSIC_PATH` / `BG_MUSIC_VOLUME` | Background music path and volume (0–1) |
| `AUTO_LYRICS_ENGINE` | `whisper` (local) or `baidu` (online) |
| `WHISPER_MODEL` / `WHISPER_MODEL_PATH` | Local model size / model directory |

## Lyrics

### LRC lyric file format

Each line follows `[mm:ss.xx] original | translation`; a line without `|` shows no translation:

```
[00:00.00] さよならは今だ | 再见是现在
[00:05.00] あなたの記憶は
```

Lyric styling is read from the PSD text layer whose name contains "歌词" (lyrics); a layer whose name also contains "翻译" (translation) is used for the translated line.

### Automatic lyric recognition

- **Local (recommended)**: `AUTO_LYRICS_ENGINE='whisper'` uses `Models/faster-whisper-small` for offline recognition with accurate sentence-level timestamps.
- **Online**: `AUTO_LYRICS_ENGINE='baidu'` requires Baidu speech-recognition and translation credentials, configured through "设置语音识别 Key" (Set recognition key) in the GUI and stored in `baidu_keys.json`.

## Troubleshooting

- **Writing to Chinese paths fails**: The script writes to a temporary ASCII filename first and renames it afterwards, working around OpenCV's problems with non-ASCII paths on Windows.
- **Background music is not muxed**: Make sure `imageio-ffmpeg` is installed (it provides the ffmpeg executable).
- **Lyrics are invisible**: Make sure the PSD contains a visible text layer whose name contains "歌词", and that the lyric file uses valid timestamps.
- **No recognition results**: `whisper` needs the local model to be present or downloadable; `baidu` needs complete credentials.
