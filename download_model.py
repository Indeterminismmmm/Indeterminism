# -*- coding: utf-8 -*-
"""下载本地 Whisper 模型权重到 Models/faster-whisper-small。

model.bin 体积较大，已通过 .gitignore 忽略，不会随仓库分发。
克隆 / 同步项目后运行本脚本，即可补全离线语音识别所需的模型文件。
"""
import os
import sys

MODEL_REPO = "Systran/faster-whisper-small"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 项目根目录
TARGET_DIR = os.path.join(BASE_DIR, "Models", "faster-whisper-small")


def main():
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("未安装 huggingface-hub，请先运行：pip install huggingface-hub")
        sys.exit(1)

    os.makedirs(TARGET_DIR, exist_ok=True)
    print(f"正在下载模型 {MODEL_REPO} ...")
    print(f"目标目录：{TARGET_DIR}")
    snapshot_download(repo_id=MODEL_REPO, local_dir=TARGET_DIR)
    print("下载完成，可正常使用离线语音识别歌词。")


if __name__ == "__main__":
    main()
