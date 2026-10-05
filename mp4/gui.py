# -*- coding: utf-8 -*-
"""
PSD 图层展示视频生成器 —— 图形界面
功能：选择 PSD 文件，设置帧率 / 每层停留时长 / 淡入淡出时长 / 输出文件名，渲染成视频。
图层名样式自动取自 PSD 中的示例文字层。
"""
import os
import sys
sys.dont_write_bytecode = True
# pythonw.exe 运行（.pyw 无终端）时 stdout/stderr 为 None，重定向避免 print 报错
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# 高 DPI 显示器上让 tkinter 界面清晰：声明 DPI 感知，避免 Windows 把窗口缩放导致模糊
if sys.platform == 'win32':
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 系统 DPI 感知
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import renderer  # 复用渲染逻辑

# ---- 界面配色 ----
BG_COLOR_UI = '#351852'      # 主背景（深紫）
FIELD_COLOR = '#24103a'      # 输入框 / 日志框底色（更深，形成层次）
FG_COLOR = '#ffffff'         # 前景文字
ACCENT = '#5b2d8f'           # 按钮底色
ACCENT_ACTIVE = '#6b3da0'    # 按钮悬停


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("PSD 图层展示视频生成器")
        self.root.geometry("1240x820")
        self.root.minsize(1000, 700)
        self.root.resizable(True, True)
        self.root.configure(bg=BG_COLOR_UI)
        self._apply_theme()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.psd_var = tk.StringVar(value=renderer.PSD_PATH)
        self.out_var = tk.StringVar(value=renderer.OUTPUT_VIDEO)
        self.fps_var = tk.IntVar(value=renderer.FPS)
        self.hold_var = tk.DoubleVar(value=round(renderer.HOLD_FRAMES / renderer.FPS, 1))  # 秒
        self.fade_var = tk.DoubleVar(value=round(renderer.FADE_FRAMES / renderer.FPS, 1))  # 秒
        self.maxside_var = tk.IntVar(value=renderer.MAX_SIDE)
        self.showname_var = tk.BooleanVar(value=renderer.SHOW_LAYER_NAME)
        self.textfade_var = tk.DoubleVar(value=round(renderer.TEXT_FADE_FRAMES / renderer.FPS, 1))  # 秒
        self.endinghold_var = tk.DoubleVar(value=round(renderer.ENDING_HOLD_FRAMES / renderer.FPS, 1))  # 秒
        self.lyrics_var = tk.StringVar(value=renderer.LYRICS_FILE or '')
        self.music_var = tk.StringVar(value=renderer.BG_MUSIC_PATH or '')
        self.volume_var = tk.DoubleVar(value=renderer.BG_MUSIC_VOLUME)
        self.lang_var = tk.StringVar(value=renderer.AUTO_LYRICS_LANG)

        # 歌词编辑状态
        self.lyrics_data = []       # 当前歌词列表 [(start, text, trans), ...]
        self.current_music = ''     # 当前识别歌词对应的音乐文件
        self.preview_photo = None   # 预览图 PhotoImage 引用（防止被回收）

        # 百度识别/翻译 key（自动识别歌词用），持久化到同目录 baidu_keys.json
        self.keys_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baidu_keys.json')
        self.baidu_keys = self._load_baidu_keys()

        # 启动时清理上次中途退出可能残留的临时文件
        renderer.cleanup_temp_files(os.path.dirname(os.path.abspath(__file__)))

        # 线程安全：worker 线程把消息放进队列，主线程轮询处理
        self.msg_queue = queue.Queue()

        self._build_ui()
        self.running = False
        self._drain_queue()  # 启动队列轮询

    def _apply_theme(self):
        """用 clam 主题自定义深紫配色（默认主题无法改背景色）。"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('.', background=BG_COLOR_UI, foreground=FG_COLOR)
        style.configure('TFrame', background=BG_COLOR_UI)
        style.configure('TLabel', background=BG_COLOR_UI, foreground=FG_COLOR)
        style.configure('TLabelframe', background=BG_COLOR_UI, foreground=FG_COLOR)
        style.configure('TLabelframe.Label', background=BG_COLOR_UI, foreground=FG_COLOR)
        style.configure('TEntry', fieldbackground=FIELD_COLOR, foreground=FG_COLOR,
                        insertcolor=FG_COLOR)
        style.configure('TButton', background=ACCENT, foreground=FG_COLOR,
                        borderwidth=0, focusthickness=0)
        style.map('TButton',
                  background=[('active', ACCENT_ACTIVE), ('disabled', FIELD_COLOR)],
                  foreground=[('disabled', '#9a8aaa')])
        style.configure('Horizontal.TProgressbar', background=ACCENT,
                        troughcolor=FIELD_COLOR, bordercolor=FIELD_COLOR,
                        lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure('Treeview', background=FIELD_COLOR, foreground=FG_COLOR,
                        fieldbackground=FIELD_COLOR, bordercolor=FIELD_COLOR,
                        rowheight=26)
        style.configure('Treeview.Heading', background=ACCENT, foreground=FG_COLOR,
                        relief='flat')
        style.map('Treeview',
                  background=[('selected', ACCENT)],
                  foreground=[('selected', FG_COLOR)])

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self.root)
        frm.pack(fill="both", expand=True, padx=12, pady=12)

        # 左侧表单
        left = ttk.Frame(frm)
        left.pack(side="left", fill="both", expand=True)

        def add_field(parent, label, var, width=8):
            r = ttk.Frame(parent)
            r.pack(fill="x", padx=8, pady=3)
            ttk.Label(r, text=label, width=16).pack(side="left")
            ttk.Entry(r, textvariable=var, width=width).pack(side="left")

        def add_file_row(parent, label, var, browse_cmd):
            r = ttk.Frame(parent)
            r.pack(fill="x", padx=8, pady=3)
            ttk.Label(r, text=label, width=16).pack(side="left")
            ttk.Entry(r, textvariable=var).pack(side="left", fill="x", expand=True)
            ttk.Button(r, text="浏览…", command=browse_cmd).pack(side="left", padx=6)

        # ① 文件
        fbox = ttk.LabelFrame(left, text="① 文件")
        fbox.pack(fill="x", **pad)
        add_file_row(fbox, "PSD 文件：", self.psd_var, self._pick_psd)
        add_file_row(fbox, "输出视频：", self.out_var, self._pick_output)

        # ② 渲染参数
        pbox = ttk.LabelFrame(left, text="② 渲染参数")
        pbox.pack(fill="x", **pad)
        add_field(pbox, "帧率 (FPS)", self.fps_var)
        add_field(pbox, "每层停留 (秒)", self.hold_var)
        add_field(pbox, "淡入淡出 (秒)", self.fade_var)
        add_field(pbox, "视频最长边 (px)", self.maxside_var)

        r = ttk.Frame(pbox)
        r.pack(fill="x", padx=8, pady=3)
        # 自定义勾选按钮：用文字符号表示状态，避免 checkbox 在深色主题下勾选标记渲染异常
        self.show_name_btn = tk.Button(
            r, command=self._toggle_show_name,
            bg=BG_COLOR_UI, fg=FG_COLOR,
            activebackground=BG_COLOR_UI, activeforeground=FG_COLOR,
            relief="flat", bd=0, highlightthickness=0,
            anchor="w", padx=0)
        self.show_name_btn.pack(side="left")
        self._refresh_show_name_btn()

        add_field(pbox, "结尾文字淡出 (秒)", self.textfade_var)
        add_field(pbox, "结尾成图定格 (秒)", self.endinghold_var)

        # ③ 背景音乐（可选）
        mbox = ttk.LabelFrame(left, text="③ 背景音乐（可选）")
        mbox.pack(fill="x", **pad)
        add_file_row(mbox, "音乐文件：", self.music_var, self._pick_music)
        add_field(mbox, "音乐音量 (0~1)", self.volume_var)

        # ④ 歌词（可选）
        lbox = ttk.LabelFrame(left, text="④ 歌词（可选）")
        lbox.pack(fill="x", **pad)
        r = ttk.Frame(lbox)
        r.pack(fill="x", padx=8, pady=3)
        ttk.Label(r, text="歌词文件：", width=16).pack(side="left")
        ttk.Entry(r, textvariable=self.lyrics_var).pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="浏览…", command=self._pick_lyrics).pack(side="left", padx=6)

        r = ttk.Frame(lbox)
        r.pack(fill="x", padx=8, pady=3)
        ttk.Label(r, text="歌词语言：", width=16).pack(side="left")
        self.lang_box = ttk.Combobox(
            r, textvariable=self.lang_var, width=10, state="readonly",
            values=['auto', 'ja', 'ru', 'en', 'zh', 'ko', 'fr', 'de', 'es'])
        self.lang_box.pack(side="left")
        ttk.Button(r, text="语音识别歌词", command=self._auto_lyrics).pack(side="left", padx=8)
        ttk.Button(r, text="设置语音识别/翻译 Key", command=self._open_key_dialog).pack(side="left", padx=4)

        # ⑤ 开始渲染
        self.start_btn = ttk.Button(left, text="开始渲染", command=self._start)
        self.start_btn.pack(pady=6)

        # 进度条
        self.status_label = ttk.Label(left, text="", anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=(4, 0))
        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", **pad)

        # 日志
        ttk.Label(left, text="运行日志：").pack(anchor="w", padx=10)
        self.log_text = tk.Text(left, height=8, state="disabled", wrap="word",
                                bg=FIELD_COLOR, fg=FG_COLOR, insertbackground=FG_COLOR,
                                relief="flat", bd=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 右侧歌词预览面板
        right = ttk.LabelFrame(frm, text="歌词预览与编辑")
        right.pack(side="right", fill="both", padx=(12, 0))
        self._build_lyric_panel(right)

    # ---- 事件处理 ----
    def _on_close(self):
        renderer.cleanup_temp_files(os.path.dirname(os.path.abspath(__file__)))
        self.root.destroy()

    # ---- 歌词预览面板 ----
    def _build_lyric_panel(self, parent):
        self.preview_canvas = tk.Canvas(parent, bg=FIELD_COLOR, highlightthickness=0)
        self.preview_canvas.pack(fill='both', expand=True, padx=8, pady=8)
        self.preview_canvas.create_text(200, 200, text="选中歌词行\n预览画面效果",
                                        fill=FG_COLOR, font=('', 12))
        self.preview_photo = None

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill='both', expand=True, padx=8, pady=(0, 4))
        self.lyric_tree = ttk.Treeview(tree_frame, columns=('time', 'text', 'trans'),
                                       show='headings', height=12)
        self.lyric_tree.heading('time', text='时间')
        self.lyric_tree.heading('text', text='歌词原文')
        self.lyric_tree.heading('trans', text='翻译')
        self.lyric_tree.column('time', width=70, anchor='center', stretch=False)
        self.lyric_tree.column('text', width=220)
        self.lyric_tree.column('trans', width=220)
        self.lyric_tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(tree_frame, orient='vertical', command=self.lyric_tree.yview)
        self.lyric_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')

        self.lyric_tree.bind('<Double-1>', lambda e: self._edit_lyric_item())
        self.lyric_tree.bind('<<TreeviewSelect>>', self._on_lyric_select)

        bar = ttk.Frame(parent)
        bar.pack(fill='x', padx=8, pady=8)
        ttk.Button(bar, text="添加", command=self._add_lyric_item).pack(side='left', padx=3)
        ttk.Button(bar, text="删除选中", command=self._delete_lyric_items).pack(side='left', padx=3)
        ttk.Button(bar, text="保存歌词", command=self._save_lyrics).pack(side='right', padx=3)

        self._refresh_lyric_tree()

    def _fmt_time(self, sec):
        sec = float(sec)
        return f"{int(sec // 60):02d}:{sec % 60:05.2f}"

    def _parse_time(self, s):
        import re
        s = s.strip()
        m = re.match(r'^(\d+):(\d+(?:\.\d+)?)$', s)
        if m:
            return int(m.group(1)) * 60 + float(m.group(2))
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _refresh_lyric_tree(self):
        self.lyric_tree.delete(*self.lyric_tree.get_children())
        for i, (start, text, trans) in enumerate(self.lyrics_data):
            self.lyric_tree.insert('', 'end', iid=str(i),
                                   values=(self._fmt_time(start), text, trans or ''))

    def _on_lyric_select(self, event):
        sel = self.lyric_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        start, text, trans = self.lyrics_data[idx]
        psd_path = self.psd_var.get().strip()
        if not psd_path or not os.path.exists(psd_path):
            self.preview_canvas.delete('all')
            self.preview_canvas.create_text(200, 100, text="请先选择 PSD 文件", fill=FG_COLOR)
            return

        def worker():
            try:
                img = renderer.render_lyric_preview(psd_path, text, trans, max_side=420)
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(img)
                def show():
                    self.preview_canvas.delete('all')
                    cw = self.preview_canvas.winfo_width()
                    ch = self.preview_canvas.winfo_height()
                    if cw > 10 and ch > 10:
                        self.preview_canvas.create_image(cw // 2, ch // 2, image=photo, anchor='center')
                    else:
                        self.preview_canvas.create_image(5, 5, image=photo, anchor='nw')
                    self.preview_photo = photo
                self.root.after(0, show)
            except Exception as e:
                def err():
                    self.preview_canvas.delete('all')
                    self.preview_canvas.create_text(200, 100, text=f"预览失败：{e}", fill=FG_COLOR, width=380)
                self.root.after(0, err)

        threading.Thread(target=worker, daemon=True).start()

    def _edit_lyric_item(self):
        sel = self.lyric_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        start, text, trans = self.lyrics_data[idx]
        ed = tk.Toplevel(self.root)
        ed.title("编辑歌词")
        ed.configure(bg=BG_COLOR_UI)
        ed.resizable(False, False)
        ed.transient(self.root)
        ed.grab_set()
        labels = ['时间 (mm:ss.xx)', '歌词原文', '翻译']
        values = [self._fmt_time(start), text, trans or '']
        entries = {}
        for i, (lab, val) in enumerate(zip(labels, values)):
            ttk.Label(ed, text=lab + '：', width=14, anchor='e').grid(
                row=i, column=0, padx=10, pady=6, sticky='e')
            e = ttk.Entry(ed, width=44)
            e.insert(0, val)
            e.grid(row=i, column=1, padx=10, pady=6, sticky='we')
            entries[lab] = e
        ed.columnconfigure(1, weight=1)

        def ok():
            ns = self._parse_time(entries['时间 (mm:ss.xx)'].get())
            nt = entries['歌词原文'].get().strip()
            ntr = entries['翻译'].get().strip()
            self.lyrics_data[idx] = [ns, nt, ntr]
            self._refresh_lyric_tree()
            ed.destroy()

        btns = ttk.Frame(ed)
        btns.grid(row=3, column=0, columnspan=2, pady=12)
        ttk.Button(btns, text="确定", command=ok).pack(side='left', padx=8)
        ttk.Button(btns, text="取消", command=ed.destroy).pack(side='left', padx=8)

    def _add_lyric_item(self):
        self.lyrics_data.append([0.0, '', ''])
        self._refresh_lyric_tree()
        last = str(len(self.lyrics_data) - 1)
        self.lyric_tree.selection_set(last)
        self.lyric_tree.see(last)
        self._edit_lyric_item()

    def _delete_lyric_items(self):
        sel = self.lyric_tree.selection()
        if not sel:
            return
        idxs = sorted([int(i) for i in sel], reverse=True)
        for idx in idxs:
            del self.lyrics_data[idx]
        self._refresh_lyric_tree()

    def _save_lyrics(self):
        data = [d for d in self.lyrics_data if d[1].strip()]
        if not data:
            messagebox.showwarning("提示", "没有有效歌词，请添加或修改。")
            return
        music = self.current_music or self.music_var.get().strip()
        if not music or not os.path.exists(music):
            messagebox.showwarning("提示", "请先选择背景音乐，以便确定歌词文件保存位置。")
            return
        data.sort(key=lambda x: x[0])
        lrc_path = os.path.splitext(music)[0] + '.lrc'
        with open(lrc_path, 'w', encoding='utf-8') as f:
            for start, text, trans in data:
                line = f"[{int(start // 60):02d}:{start % 60:05.2f}] {text.strip()}"
                if trans.strip():
                    line += f" | {trans.strip()}"
                f.write(line + "\n")
        self.lyrics_var.set(lrc_path)
        self._log(f"歌词已保存：{lrc_path}")
        messagebox.showinfo("完成", f"歌词已保存到：\n{lrc_path}")

    def _refresh_show_name_btn(self):
        mark = '[√]' if self.showname_var.get() else '[　]'
        self.show_name_btn.config(text=f"{mark} 显示当前图层名（样式取自 PSD 示例文字层）")

    def _toggle_show_name(self):
        self.showname_var.set(not self.showname_var.get())
        self._refresh_show_name_btn()

    def _load_baidu_keys(self):
        import json
        keys = {'api_key': '', 'secret_key': '', 'app_id': '', 'trans_key': ''}
        try:
            if os.path.exists(self.keys_path):
                with open(self.keys_path, 'r', encoding='utf-8') as f:
                    keys.update(json.load(f))
        except Exception:
            pass
        return keys

    def _save_baidu_keys(self):
        import json
        try:
            with open(self.keys_path, 'w', encoding='utf-8') as f:
                json.dump(self.baidu_keys, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            messagebox.showerror("错误", f"保存 key 失败：{e}")
            return False

    def _open_key_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("设置语音识别/翻译 Key")
        dlg.configure(bg=BG_COLOR_UI)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        fields = [
            ('语音识别 API Key', 'api_key'),
            ('语音识别 Secret Key', 'secret_key'),
            ('翻译 APP ID', 'app_id'),
            ('翻译密钥', 'trans_key'),
        ]
        entries = {}
        for i, (label, key) in enumerate(fields):
            ttk.Label(dlg, text=label + '：', width=20, anchor='e').grid(
                row=i, column=0, padx=10, pady=6, sticky='e')
            e = ttk.Entry(dlg, width=44)
            e.insert(0, self.baidu_keys.get(key, ''))
            e.grid(row=i, column=1, padx=10, pady=6, sticky='we')
            entries[key] = e

        dlg.columnconfigure(1, weight=1)

        def save():
            for key, e in entries.items():
                self.baidu_keys[key] = e.get().strip()
            if self._save_baidu_keys():
                dlg.destroy()
                messagebox.showinfo("已保存", "语音识别/翻译 Key 已保存。")

        btns = ttk.Frame(dlg)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=12)
        ttk.Button(btns, text="保存", command=save).pack(side='left', padx=8)
        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side='left', padx=8)

    def _auto_lyrics(self):
        music = self.music_var.get().strip()
        if not music or not os.path.exists(music):
            messagebox.showerror("错误", "请先选择背景音乐（mp3 或 mp4）。")
            return
        keys = self.baidu_keys
        if not (keys.get('app_id') and keys.get('trans_key')):
            messagebox.showwarning("提示", "自动翻译需要文字翻译 Key（APP ID + 密钥）。")
            self._open_key_dialog()
            return
        lang = self.lang_var.get().strip() or 'auto'

        # 立即在主线程写日志，让用户明确知道已开始提取歌词
        self._log("=" * 40)
        self._log("正在提取并翻译歌词...")
        self._log("正在加载语音识别模型，请稍候...")
        # 进度条重置为确定模式
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress["value"] = 0
        self.status_label.config(text="正在提取并翻译歌词...")

        def worker():
            try:
                lyrics = renderer.recognize_lyrics(
                    music, engine=renderer.AUTO_LYRICS_ENGINE,
                    language=lang, to_lang=renderer.AUTO_LYRICS_TO,
                    model_size=renderer.WHISPER_MODEL,
                    model_path=renderer.WHISPER_MODEL_PATH,
                    api_key=keys.get('api_key', ''), secret_key=keys.get('secret_key', ''),
                    app_id=keys['app_id'], trans_key=keys['trans_key'],
                    chunk_sec=renderer.AUTO_CHUNK_SEC, progress_cb=self._on_progress)
                if not lyrics:
                    self.msg_queue.put(("log", "未识别到歌词。", None, None))
                    return
                self.msg_queue.put(("log", f"提取并翻译歌词完成，共 {len(lyrics)} 句，请在右侧面板检查修改。", None, None))
                def load_lyrics():
                    self.current_music = music
                    self.lyrics_data = [[round(s, 2), t, tr or ''] for s, t, tr in lyrics]
                    self._refresh_lyric_tree()
                    if self.lyrics_data:
                        self.lyric_tree.selection_set('0')
                        self.lyric_tree.see('0')
                self.root.after(0, load_lyrics)
            except Exception as e:
                self.msg_queue.put(("error", f"自动识别失败：{e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _pick_psd(self):
        path = filedialog.askopenfilename(
            title="选择 PSD 文件",
            filetypes=[("PSD 文件", "*.psd"), ("所有文件", "*.*")])
        if path:
            self.psd_var.set(path)
            # 自动生成输出文件名（同目录、同名 .mp4）
            base = os.path.splitext(path)[0]
            self.out_var.set(base + ".mp4")

    def _pick_output(self):
        path = filedialog.asksaveasfilename(
            title="保存视频",
            defaultextension=".mp4",
            filetypes=[("MP4 视频", "*.mp4")])
        if path:
            self.out_var.set(path)

    def _pick_lyrics(self):
        path = filedialog.askopenfilename(
            title="选择歌词文件",
            filetypes=[("歌词文件", "*.lrc *.txt"), ("所有文件", "*.*")])
        if path:
            self.lyrics_var.set(path)

    def _pick_music(self):
        path = filedialog.askopenfilename(
            title="选择背景音乐（mp3 或 mp4）",
            filetypes=[("音频/视频", "*.mp3 *.mp4"), ("所有文件", "*.*")])
        if path:
            self.music_var.set(path)

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_progress(self, msg, cur, tot):
        # worker 线程调用：只入队，不碰 tk
        self.msg_queue.put(("log", msg, cur, tot))

    def _drain_queue(self):
        # 主线程轮询：处理日志、进度、完成通知
        try:
            while True:
                kind, *args = self.msg_queue.get_nowait()
                if kind == "log":
                    msg, cur, tot = args
                    if cur is not None and tot:
                        # 进度更新：浮动标签 + 进度条
                        self.status_label.config(text=msg)
                        if self.progress.cget("mode") != "determinate":
                            self.progress.stop()
                            self.progress.configure(mode="determinate")
                        self.progress["value"] = cur / tot * 100
                    else:
                        # 关键节点：写日志
                        self._log(msg)
                elif kind == "done":
                    ok, = args
                    self.running = False
                    self.start_btn.configure(state="normal", text="开始渲染")
                    if ok:
                        messagebox.showinfo("完成", "视频渲染完成！")
                    else:
                        messagebox.showwarning("提示", "渲染未能正常完成，请查看日志。")
                elif kind == "error":
                    err, = args
                    self.running = False
                    self.start_btn.configure(state="normal", text="开始渲染")
                    self._log(f"发生错误: {err}")
                    messagebox.showerror("错误", str(err))
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    def _start(self):
        if self.running:
            return
        psd_path = self.psd_var.get().strip()
        out_path = self.out_var.get().strip()
        if not psd_path or not os.path.exists(psd_path):
            messagebox.showerror("错误", "请选择有效的 PSD 文件。")
            return
        if not out_path:
            messagebox.showerror("错误", "请输入输出视频文件名。")
            return
        try:
            fps = int(self.fps_var.get())
            hold_sec = float(self.hold_var.get())
            fade_sec = float(self.fade_var.get())
            textfade_sec = float(self.textfade_var.get())
            endinghold_sec = float(self.endinghold_var.get())
            max_side = int(self.maxside_var.get()) if self.maxside_var.get() else None
            volume = float(self.volume_var.get())
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数值参数。")
            return
        if fps <= 0 or hold_sec < 0 or fade_sec < 0 or textfade_sec < 0 or endinghold_sec < 0:
            messagebox.showerror("错误", "帧率必须 > 0，时长不能为负。")
            return
        if not (0 <= volume <= 1):
            messagebox.showerror("错误", "音乐音量必须在 0~1 之间。")
            return

        self.running = True
        self.start_btn.configure(state="disabled", text="渲染中…")
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress["value"] = 0
        self._log("=" * 50)

        hold_frames = max(1, round(hold_sec * fps))
        fade_frames = max(0, round(fade_sec * fps))
        text_fade_frames = max(0, round(textfade_sec * fps))
        ending_hold_frames = max(0, round(endinghold_sec * fps))
        show_name = self.showname_var.get()  # 主线程读取，避免跨线程访问 tk 变量
        lyrics_file = self.lyrics_var.get().strip() or None
        music_file = self.music_var.get().strip() or None

        def worker():
            try:
                ok = renderer.render(
                    psd_path=psd_path,
                    output_video=out_path,
                    fps=fps,
                    hold_frames=hold_frames,
                    fade_frames=fade_frames,
                    text_fade_frames=text_fade_frames,
                    ending_hold_frames=ending_hold_frames,
                    max_side=max_side,
                    show_layer_name=show_name,
                    lyrics_file=lyrics_file,
                    bg_music_path=music_file,
                    bg_music_volume=volume,
                    progress_cb=self._on_progress,
                )
                self.msg_queue.put(("done", ok))
            except Exception as e:
                self.msg_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
