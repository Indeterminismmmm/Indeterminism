# -*- coding: utf-8 -*-
"""双击本文件即可无终端窗口启动 GUI（用 pythonw.exe 运行）。"""
import os
import sys

# 确保工作目录在本脚本所在位置，方便找到 renderer.py
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import gui

if __name__ == "__main__":
    gui.main()
