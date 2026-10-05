# -*- coding: utf-8 -*-
"""
逐层展示 PSD 图层并渲染成视频：
按照图层从底到顶的堆叠顺序，每一步多显示一层，用 psd-tools 的合成引擎渲染
（正确保留混合模式 / 剪贴蒙版 / 调整图层效果），最后写成 mp4。
"""
import os
import sys
sys.dont_write_bytecode = True  # 不生成 .pyc 缓存，避免沙箱写缓存被拦截导致进程报"失败"
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from psd_tools import PSDImage
from psd_tools.api.layers import Group, TypeLayer

# ================= 配置参数 =================
PSD_PATH = 'Faelight_教会你心生爱慕的，学会画画的是——.psd'   # 你的 PSD 文件路径
OUTPUT_VIDEO = 'Faelight_教会你心生爱慕的，学会画画的是——.mp4'  # 输出的视频文件名
FPS = 30                          # 视频帧率
HOLD_FRAMES = 90                  # 每层出现后停留的帧数（90帧 = 3秒）
FADE_FRAMES = 15                  # 层与层之间淡入淡出的帧数（15帧 = 0.5秒）
TEXT_FADE_FRAMES = 30             # 结尾图层名文字淡出的帧数（30帧 = 1秒）
ENDING_HOLD_FRAMES = 90           # 图层名消失后，完整成图定格的帧数（90帧 = 3秒）
BG_COLOR = (255, 255, 255)        # 透明区域的底色（画纸一般是白色）
MAX_SIDE = 2160                   # 视频最长边（原图 3236x5989，缩到 2160 = 4K 竖屏）
                                  # 想保留原始尺寸就改成 None，或在 GUI 里改
# ---- 图层名标注 ----
# 样式自动取自 PSD 中的示例文字层（TypeLayer）：字号、颜色、位置、对齐方式。
# 你在 Photoshop 里调整该文字层后保存，脚本会自动同步，无需改代码。
SHOW_LAYER_NAME = True            # 是否显示当前图层名
FONT_PATH = r'C:\Windows\Fonts\STZHONGS.TTF'  # 字体文件（华文宋体）
# 若 PSD 中没有示例文字层，则使用以下兜底参数：
DEFAULT_FONT_PT = 31              # 字号（点）
PSD_DPI = 300                     # PSD 分辨率
DEFAULT_TEXT_POS = (2530.25, 5861.43)  # 兜底位置（画布坐标）
TEXT_COLOR_FALLBACK = (255, 255, 255)   # 兜底颜色
# ---- 歌词 ----
# 在 PSD 中新建一个文字层，图层名包含"歌词"，写上示例歌词文本并调好字号/颜色/位置，
# 脚本会自动读取该层样式来渲染歌词。支持翻译：歌词文件里用 | 分隔原文和翻译，
# 某行没有 | 则该行不显示翻译。歌词文件格式（LRC 风格时间戳）：
#   [00:00.00] 第一句歌词 | First line translation
#   [00:03.50] 第二句歌词
LYRICS_FILE = None                # 歌词文件路径，None 表示不显示歌词
# ---- 背景音乐 ----
BG_MUSIC_PATH = None              # mp3 或 mp4 文件路径，None 表示不加背景音乐
BG_MUSIC_VOLUME = 0.8             # 背景音乐音量 0.0 ~ 1.0
# ---- 自动识别歌词 ----
# 识别引擎：'whisper'=本地（离线免费，支持日/俄/英/中等 99 种语言，推荐）
#           'baidu'  =在线（需百度短语音识别 key，仅支持中英粤川）
AUTO_LYRICS_ENGINE = 'whisper'
WHISPER_MODEL = 'small'           # whisper 模型：tiny/base/small/medium/large（越大越准越慢）
WHISPER_MODEL_PATH = r'G:\script\Models\faster-whisper-small'  # 本地模型目录（含 model.bin）；留空则按 WHISPER_MODEL 自动下载
AUTO_LYRICS_LANG = 'auto'         # 歌词语言：'auto'=自动检测，或 'ja'/'ru'/'en'/'zh' 等 ISO 代码
AUTO_LYRICS_TO = 'zh'             # 翻译目标语言
# 翻译始终走百度翻译（需 app_id + trans_key）：
BAIDU_APP_ID = ''                 # 百度翻译 APP ID
BAIDU_TRANS_KEY = ''              # 百度翻译密钥
# 仅 engine='baidu' 时需要（百度短语音识别）：
BAIDU_API_KEY = ''                # 语音识别 API Key
BAIDU_SECRET_KEY = ''             # 语音识别 Secret Key
AUTO_CHUNK_SEC = 50               # 百度识别时每段音频时长（秒，限 60 内）
# ============================================


def flatten_layers(psd):
    """
    把 PSD 的图层结构展开成叶子图层列表（组本身不算），
    按从底到顶的顺序排列（psd-tools 的迭代顺序本身就是从底到顶）。
    跳过 TypeLayer：PSD 顶部的文字层是标注样式的示例，不作为作品图层展示，
    图层名由脚本自己绘制。
    """
    flat_list = []

    def _traverse(layers, parent_visible=True):
        for layer in layers:  # 从底到顶
            visible = parent_visible and layer.is_visible()
            if isinstance(layer, Group):
                _traverse(layer, visible)
            elif visible and not isinstance(layer, TypeLayer):
                flat_list.append(layer)

    _traverse(psd)
    return flat_list


def composite_upto(psd, target_set):
    """
    只合成 target_set 里的叶子图层（组作为容器放行，否则组内图层不会被渲染），
    返回 PIL RGBA 图像。混合模式、调整图层、剪贴蒙版都由合成引擎正确处理。
    """
    def layer_filter(l):
        if isinstance(l, Group):
            return l.is_visible()
        return l in target_set

    return psd.composite(layer_filter=layer_filter)


def find_type_layer(psd):
    """递归查找 PSD 中第一个可见的 TypeLayer（示例文字层）。"""
    def _walk(layers, parent_visible=True):
        for layer in layers:
            visible = parent_visible and layer.is_visible()
            if isinstance(layer, TypeLayer) and visible:
                return layer
            if isinstance(layer, Group):
                found = _walk(layer, visible)
                if found:
                    return found
        return None
    return _walk(psd)


def extract_text_style(type_layer):
    """
    从示例文字层提取字号(画布像素)、颜色(RGB)、右边缘x、基线y（画布坐标）。
    字号取 StyleRun 里的 FontSize（psd-tools 已转成画布像素）。
    颜色取 FillColor 的 Values。
    位置取 bbox 的右边缘和下边缘（右对齐 + 基线）。
    """
    font_px = DEFAULT_FONT_PT * PSD_DPI / 72
    color = TEXT_COLOR_FALLBACK
    right_x, bottom_y = DEFAULT_TEXT_POS

    bbox = type_layer.bbox
    if bbox and bbox[2] and bbox[3]:
        right_x = bbox[2]
        bottom_y = bbox[3]

    try:
        ed = type_layer.engine_dict
        runs = ed.get('StyleRun', {}).get('RunArray', [])
        if runs:
            ssd = runs[0].get('StyleSheet', {}).get('StyleSheetData', {})
            fs = ssd.get('FontSize')
            if fs:
                font_px = fs
            fc = ssd.get('FillColor', {}).get('Values')
            if fc and len(fc) >= 4:
                color = (int(fc[1] * 255), int(fc[2] * 255), int(fc[3] * 255))
    except Exception as e:
        print(f"  提取文字层样式失败，使用默认值: {e}")

    return font_px, color, right_x, bottom_y


def find_type_layer_by_name(psd, keyword):
    """递归查找 PSD 中名字包含 keyword 的可见 TypeLayer（用于区分图层名层/歌词层）。"""
    def _walk(layers, parent_visible=True):
        for layer in layers:
            visible = parent_visible and layer.is_visible()
            if isinstance(layer, TypeLayer) and visible and keyword in layer.name:
                return layer
            if isinstance(layer, Group):
                found = _walk(layer, visible)
                if found:
                    return found
        return None
    return _walk(psd)


# 兼容旧调用：find_type_layer 返回第一个非歌词的 TypeLayer（图层名示例层）
def find_type_layer(psd):
    def _walk(layers, parent_visible=True):
        for layer in layers:
            visible = parent_visible and layer.is_visible()
            if isinstance(layer, TypeLayer) and visible and '歌词' not in layer.name:
                return layer
            if isinstance(layer, Group):
                found = _walk(layer, visible)
                if found:
                    return found
        return None
    return _walk(psd)


def find_lyric_layers(psd):
    """返回 (歌词原文层, 歌词翻译层)。名字含"歌词"且不含"翻译"为原文，含"翻译"为翻译层。"""
    lyric_layer = None
    trans_layer = None
    for l in psd.descendants():
        if isinstance(l, TypeLayer) and l.is_visible() and '歌词' in l.name:
            if '翻译' in l.name:
                if trans_layer is None:
                    trans_layer = l
            else:
                if lyric_layer is None:
                    lyric_layer = l
    return lyric_layer, trans_layer


def _lyric_style(type_layer, sx, sy):
    """从歌词层提取 (字体, 颜色, 左对齐基线坐标)。歌词层是左对齐，锚点用 bbox 左边缘 + 下边缘基线。"""
    font_px, color, right_x, bottom_y = extract_text_style(type_layer)
    bbox = type_layer.bbox
    left_x = bbox[0] if bbox else 0
    baseline_y = bbox[3] if bbox else 0
    font_video_px = max(1, round(font_px * sy))
    font = ImageFont.truetype(FONT_PATH, font_video_px)
    return font, color, (left_x * sx, baseline_y * sy)


import re

_LRC_TIME_RE = re.compile(r'^\[(\d+):(\d+(?:\.\d+)?)\]')


def parse_lyrics(filepath):
    """
    解析 LRC 风格歌词文件，返回 [(start_sec, text, translation), ...] 按时间升序。
    每行格式：[mm:ss.xx] 原文 | 翻译
    没有 | 时 translation 为 None（该行不显示翻译）。
    """
    if not filepath or not os.path.exists(filepath):
        return []
    lines = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for raw in f:
            raw = raw.rstrip('\n').rstrip('\r')
            m = _LRC_TIME_RE.match(raw)
            if not m:
                continue
            minutes = int(m.group(1))
            seconds = float(m.group(2))
            start = minutes * 60 + seconds
            content = raw[m.end():].strip()
            if '|' in content:
                text, trans = content.split('|', 1)
                text = text.strip()
                trans = trans.strip()
            else:
                text = content
                trans = None
            if text:
                lines.append((start, text, trans))
    lines.sort(key=lambda x: x[0])
    return lines


def get_lyric_at(lyrics, t):
    """返回时间 t 处正在显示的 (text, translation)，没有则 (None, None)。"""
    cur = (None, None)
    for start, text, trans in lyrics:
        if start <= t:
            cur = (text, trans)
        else:
            break
    return cur


def draw_text_with_alpha(rgb, xy, text, font, color, alpha=255, anchor='rs'):
    """在 rgb 图上以指定透明度画文字（alpha<255 时走透明图层合成）。"""
    if not text or alpha <= 0:
        return
    if alpha >= 255:
        ImageDraw.Draw(rgb).text(xy, text, font=font, fill=color, anchor=anchor)
    else:
        overlay = Image.new('RGBA', rgb.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).text(xy, text, font=font,
                                     fill=(color[0], color[1], color[2], alpha),
                                     anchor=anchor)
        rgb.paste(Image.alpha_composite(rgb.convert('RGBA'), overlay).convert('RGB'), (0, 0))


def to_video_frame(img, size, text=None, font=None, text_xy=None,
                   color=TEXT_COLOR_FALLBACK, text_alpha=255,
                   lyric_text=None, lyric_trans=None,
                   lyric_font=None, trans_font=None, lyric_xy=None, trans_xy=None,
                   lyric_color=(255, 255, 255), lyric_alpha=255):
    """PIL 图像 -> 铺底色 -> 缩放 -> 画图层名 + 歌词 -> BGR numpy"""
    img = img.convert('RGBA')
    bg = Image.new('RGBA', img.size, BG_COLOR + (255,))
    rgb = Image.alpha_composite(bg, img).convert('RGB')
    if rgb.size != size:
        rgb = rgb.resize(size, Image.LANCZOS)
    # 图层名
    if text and font and text_alpha > 0:
        draw_text_with_alpha(rgb, text_xy, text, font, color, text_alpha, anchor='rs')
    # 歌词原文
    if lyric_text and lyric_font and lyric_alpha > 0:
        draw_text_with_alpha(rgb, lyric_xy, lyric_text, lyric_font, lyric_color, lyric_alpha, anchor='ls')
    # 歌词翻译（有则显示）
    if lyric_trans and trans_font and lyric_alpha > 0:
        draw_text_with_alpha(rgb, trans_xy, lyric_trans, trans_font, lyric_color, lyric_alpha, anchor='ls')
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


def cleanup_temp_files(directory):
    """清理渲染/识别过程中可能残留的临时文件（用于中途退出后的磁盘清理）。"""
    for name in ('_output_tmp.mp4', '_lyrics_tmp.pcm', '_lyrics_tmp.wav'):
        p = os.path.join(directory, name)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def render(psd_path=PSD_PATH, output_video=OUTPUT_VIDEO, fps=FPS,
           hold_frames=HOLD_FRAMES, fade_frames=FADE_FRAMES,
           text_fade_frames=TEXT_FADE_FRAMES, ending_hold_frames=ENDING_HOLD_FRAMES,
           max_side=MAX_SIDE, show_layer_name=SHOW_LAYER_NAME,
           lyrics_file=LYRICS_FILE, bg_music_path=BG_MUSIC_PATH,
           bg_music_volume=BG_MUSIC_VOLUME, progress_cb=None):
    """
    渲染主函数。GUI 和命令行都可以调用。
    progress_cb(message, current, total) 可选，用于更新进度。
    """
    def log(msg, cur=None, tot=None):
        print(msg)
        if progress_cb:
            progress_cb(msg, cur, tot)

    log(f"正在打开 PSD 文件: {psd_path}")
    psd = PSDImage.open(psd_path)

    layers = flatten_layers(psd)
    log(f"找到 {len(layers)} 个可见图层（从底到顶）:")
    for i, l in enumerate(layers):
        log(f"  第{i+1:2d}步: {l.name}")
    if not layers:
        log("没有找到可渲染的可见图层。")
        return False

    # 计算视频尺寸（等比缩放到最长边 max_side）
    width, height = psd.size
    log(f"画布尺寸: {width} x {height}")
    if max_side and max(width, height) > max_side:
        scale = max_side / max(width, height)
        width = round(width * scale / 2) * 2  # 保证是偶数，编码器要求
        height = round(height * scale / 2) * 2
    log(f"视频尺寸: {width} x {height}")

    sx = width / psd.size[0]
    sy = height / psd.size[1]

    # 准备图层名字体：自动从 PSD 示例文字层读取字号/颜色/位置
    font, text_xy, text_color = None, None, TEXT_COLOR_FALLBACK
    if show_layer_name:
        sample = find_type_layer(psd)
        if sample:
            font_px, text_color, right_x, bottom_y = extract_text_style(sample)
            log(f"图层名示例层: {sample.name!r}")
        else:
            log("未找到图层名示例文字层，使用默认样式")
            font_px = DEFAULT_FONT_PT * PSD_DPI / 72
            right_x, bottom_y = DEFAULT_TEXT_POS
        font_video_px = max(1, round(font_px * sy))
        font = ImageFont.truetype(FONT_PATH, font_video_px)
        text_xy = (right_x * sx, bottom_y * sy)
        log(f"图层名标注: 字号 {font_video_px}px, 颜色 {text_color}, 位置 ({text_xy[0]:.0f}, {text_xy[1]:.0f})")

    # 准备歌词：解析文件 + 从 PSD 歌词层（原文/翻译）分别读取样式
    if lyrics_file:
        log("正在读取歌词文件...")
    lyrics = parse_lyrics(lyrics_file)
    if lyrics_file:
        log(f"歌词文件读取完成，共 {len(lyrics)} 行。")
    lyric_font, trans_font = None, None
    lyric_xy, trans_xy = None, None
    lyric_color = (255, 255, 255)
    if lyrics:
        lyric_layer, trans_layer = find_lyric_layers(psd)
        if lyric_layer:
            lyric_font, lyric_color, lyric_xy = _lyric_style(lyric_layer, sx, sy)
            log(f"歌词原文层: {lyric_layer.name!r}")
        if trans_layer:
            trans_font, _, trans_xy = _lyric_style(trans_layer, sx, sy)
            log(f"歌词翻译层: {trans_layer.name!r}")
        if not lyric_layer:
            log("未找到歌词示例层（名字含'歌词'），歌词将不可见")

    # OpenCV 在 Windows 下写中文路径会静默失败，先写临时英文名，完成后改名
    out_dir = os.path.dirname(os.path.abspath(output_video)) or '.'
    cleanup_temp_files(out_dir)  # 清理上次中途退出可能残留的临时文件
    tmp_video = os.path.join(out_dir, '_output_tmp.mp4')
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(tmp_video, fourcc, fps, (width, height))
    if not writer.isOpened():
        log("视频写入器初始化失败。")
        return False

    log("开始逐层合成...")
    target_set = set()
    prev_frame = None
    last_img = None
    last_name = None
    frame_idx = 0  # 已写入帧数，用于计算歌词时间轴

    def write_with_lyrics(frame_img, layer_name=None, layer_alpha=255):
        nonlocal frame_idx
        t = frame_idx / fps
        lt, ltr = get_lyric_at(lyrics, t) if lyrics else (None, None)
        out = to_video_frame(
            frame_img, (width, height),
            text=layer_name, font=font, text_xy=text_xy, color=text_color, text_alpha=layer_alpha,
            lyric_text=lt, lyric_trans=ltr,
            lyric_font=lyric_font, trans_font=trans_font,
            lyric_xy=lyric_xy, trans_xy=trans_xy,
            lyric_color=lyric_color, lyric_alpha=255)
        writer.write(out)
        frame_idx += 1

    for i, layer in enumerate(layers):
        target_set.add(layer)
        try:
            img = composite_upto(psd, target_set)
        except Exception as e:
            log(f"  第{i+1}步 [{layer.name}] 合成失败，已跳过: {e}")
            continue
        if img is None:
            continue

        # 当前层目标帧（完整图层名 + 歌词）
        frame = to_video_frame(
            img, (width, height),
            text=layer.name, font=font, text_xy=text_xy, color=text_color, text_alpha=255,
            lyric_text=None, lyric_font=None, lyric_xy=None, lyric_color=lyric_color)

        # 淡入淡出：从上一帧逐渐过渡到当前帧（新图层淡入），同时叠加歌词
        if prev_frame is not None:
            for t in range(1, fade_frames + 1):
                alpha = t / (fade_frames + 1)
                blend = cv2.addWeighted(prev_frame, 1 - alpha, frame, alpha, 0)
                # blend 已含图层名与底图，只需在其上叠加当前时间的歌词
                tt = frame_idx / fps
                lt, ltr = get_lyric_at(lyrics, tt) if lyrics else (None, None)
                if lt and lyric_font:
                    pil = Image.fromarray(cv2.cvtColor(blend, cv2.COLOR_BGR2RGB))
                    draw_text_with_alpha(pil, lyric_xy, lt, lyric_font, lyric_color, 255, anchor='ls')
                    if ltr and trans_font:
                        draw_text_with_alpha(pil, trans_xy, ltr, trans_font, lyric_color, 255, anchor='ls')
                    blend = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
                writer.write(blend)
                frame_idx += 1

        # 当前层停留
        for _ in range(hold_frames):
            write_with_lyrics(img, layer.name, 255)

        prev_frame = frame
        last_img = img
        last_name = layer.name
        log(f"  第{i+1}/{len(layers)}步 [{layer.name}] 完成")
        if progress_cb:
            progress_cb(f"正在渲染 第{i+1}/{len(layers)}步 [{layer.name}]", i + 1, len(layers))

    # 结尾：图层名文字逐渐淡出（画面保持完整作品不变，歌词继续）
    if show_layer_name and font and last_img is not None and text_fade_frames > 0:
        log(f"  结尾图层名淡出（{text_fade_frames} 帧）...")
        for t in range(1, text_fade_frames + 1):
            alpha = int(255 * (1 - t / (text_fade_frames + 1)))
            write_with_lyrics(last_img, last_name, alpha)

    # 结尾成图定格（无图层名，歌词继续）
    if last_img is not None and ending_hold_frames > 0:
        log(f"  结尾成图定格（{ending_hold_frames} 帧）...")
        for _ in range(ending_hold_frames):
            write_with_lyrics(last_img, None, 0)

    writer.release()

    # 背景音乐合成
    try:
        if bg_music_path and os.path.exists(bg_music_path):
            log(f"正在合成背景音乐: {bg_music_path}")
            if not mux_background_music(tmp_video, bg_music_path, output_video, bg_music_volume, fps):
                log("背景音乐合成失败，保存无声视频。")
                os.replace(tmp_video, output_video)
        else:
            if bg_music_path:
                log(f"背景音乐文件不存在，跳过: {bg_music_path}")
            os.replace(tmp_video, output_video)
    finally:
        # 无论成败，清理临时视频（成功后 tmp_video 已被 replace 移走，这里兜底删除残留）
        if os.path.exists(tmp_video):
            try:
                os.remove(tmp_video)
            except OSError:
                pass

    seconds = frame_idx / fps
    log(f"完成！视频已保存到: {output_video}（时长约 {seconds:.0f} 秒，共 {frame_idx} 帧）")
    if progress_cb:
        progress_cb("渲染完成", len(layers), len(layers))
    return True


def mux_background_music(video_path, audio_path, output_path, volume, fps):
    """用 ffmpeg 把背景音乐混入视频。支持 mp3 音频或从 mp4 提取音频。
    音频短于视频则循环，长于则裁剪，并加淡入淡出。"""
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        print(f"  缺少 ffmpeg（imageio-ffmpeg），无法合成音乐: {e}")
        return False

    import subprocess
    ext = os.path.splitext(audio_path)[1].lower()
    # 输入音频：mp4 走 -i 取音频流；mp3 直接用
    # 使用 -stream_loop -1 循环音频，-shortest 使其匹配视频时长
    # 音量与淡入淡出：0.5s 淡入，结尾 1s 淡出
    fade_out_dur = 1.0
    cmd = [
        ffmpeg, '-y',
        '-i', video_path,
        '-stream_loop', '-1', '-i', audio_path,
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        '-filter:a', f'volume={volume},afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, (cv2.VideoCapture(video_path).get(cv2.CAP_PROP_FRAME_COUNT)/fps) - fade_out_dur):.2f}:d={fade_out_dur}',
        '-shortest',
        '-map', '0:v:0', '-map', '1:a:0',
        output_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  ffmpeg 错误: {r.stderr[-500:]}")
            return False
        return True
    except Exception as e:
        print(f"  背景音乐合成异常: {e}")
        return False


def main():
    render()


# ================= 自动识别歌词（百度智能云）=================

def _get_ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return 'ffmpeg'


def get_baidu_token(api_key, secret_key):
    """获取百度语音识别的 access_token。"""
    import requests
    url = 'https://openapi.baidu.com/oauth/2.0/token'
    params = {
        'grant_type': 'client_credentials',
        'client_id': api_key,
        'client_secret': secret_key,
    }
    r = requests.post(url, params=params, timeout=30)
    data = r.json()
    if 'access_token' not in data:
        raise RuntimeError(f"获取百度 token 失败：{data}")
    return data['access_token']


def baidu_asr_short(pcm_bytes, token, dev_pid=1737):
    """百度短语音识别（60 秒以内），返回识别出的文本。dev_pid：1737=英文，1537=普通话。"""
    import requests
    import base64
    url = 'https://vop.baidu.com/server_api'
    payload = {
        'format': 'pcm',
        'rate': 16000,
        'channel': 1,
        'cuid': 'psd_lyrics_tool',
        'len': len(pcm_bytes),
        'speech': base64.b64encode(pcm_bytes).decode('utf-8'),
        'token': token,
        'dev_pid': dev_pid,
    }
    r = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=90)
    data = r.json()
    if data.get('err_no') != 0:
        raise RuntimeError(f"百度语音识别失败：{data}")
    return ''.join(data.get('result', []))


def baidu_translate(text, app_id, trans_key, from_lang='en', to_lang='zh', retries=3):
    """百度通用文本翻译，返回译文。带重试，应对网络抖动和 QPS 限流。"""
    import requests
    import hashlib
    import random
    import time
    url = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
    last_err = None
    for attempt in range(retries):
        salt = str(random.randint(32768, 65536))
        sign = hashlib.md5((app_id + text + salt + trans_key).encode('utf-8')).hexdigest()
        params = {
            'q': text, 'from': from_lang, 'to': to_lang,
            'appid': app_id, 'salt': salt, 'sign': sign,
        }
        try:
            r = requests.get(url, params=params, timeout=30)
            data = r.json()
            if 'trans_result' in data:
                return ''.join(item['dst'] for item in data['trans_result'])
            last_err = RuntimeError(f"百度翻译失败：{data}")
        except requests.exceptions.RequestException as e:
            last_err = RuntimeError(f"翻译网络错误：{e}")
        if attempt < retries - 1:
            time.sleep(0.8 * (attempt + 1))  # 递增等待，避开限流/网络抖动
    raise last_err


def _split_sentences(text):
    """按标点把识别文本切成句子。"""
    parts = re.split(r'(?<=[.!?。！？])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def auto_recognize_lyrics(music_path, api_key, secret_key, app_id, trans_key,
                          from_lang='en', to_lang='zh', chunk_sec=50, progress_cb=None):
    """
    从音乐文件自动识别歌词并翻译，返回 [(start_sec, text, translation), ...]。
    时间戳为每段音频内的均匀分布近似（短语音识别不返回句级时间戳）。
    """
    def log(msg, cur=None, tot=None):
        print(msg)
        if progress_cb:
            progress_cb(msg, cur, tot)

    if not (api_key and secret_key and app_id and trans_key):
        log("百度凭证不完整，无法自动识别歌词（需同时配置识别和翻译的 key）。")
        return []

    import subprocess
    import time
    ffmpeg = _get_ffmpeg_exe()
    out_dir = os.path.dirname(os.path.abspath(music_path)) or '.'
    pcm_path = os.path.join(out_dir, '_lyrics_tmp.pcm')

    log("提取音频为 pcm（16k/单声道）...")
    r = subprocess.run(
        [ffmpeg, '-y', '-i', music_path, '-ac', '1', '-ar', '16000', '-f', 's16le', pcm_path],
        capture_output=True, text=True)
    if not os.path.exists(pcm_path) or os.path.getsize(pcm_path) == 0:
        log("音频提取失败。")
        return []

    bytes_per_sec = 16000 * 2  # 16k 采样率 × 16bit(2字节)
    total_sec = os.path.getsize(pcm_path) / bytes_per_sec
    log(f"音频时长约 {total_sec:.0f} 秒")

    log("获取百度 access_token...")
    token = get_baidu_token(api_key, secret_key)

    dev_pid = 1737 if from_lang == 'en' else 1537
    chunk_bytes = int(chunk_sec * bytes_per_sec)
    lyrics = []
    with open(pcm_path, 'rb') as f:
        idx = 0
        while True:
            chunk = f.read(chunk_bytes)
            if len(chunk) < bytes_per_sec * 2:  # 不足 2 秒的尾巴丢弃
                break
            start = idx * chunk_sec
            log(f"  识别第 {idx+1} 段（{start}~{start+chunk_sec}s）...")
            try:
                text = baidu_asr_short(chunk, token, dev_pid)
            except Exception as e:
                log(f"  第 {idx+1} 段识别失败：{e}")
                text = ''
            if text:
                sentences = _split_sentences(text) or [text]
                seg_dur = chunk_sec / len(sentences)
                for j, s in enumerate(sentences):
                    tr = None
                    try:
                        tr = baidu_translate(s, app_id, trans_key, from_lang, to_lang)
                    except Exception as e:
                        log(f"    翻译失败：{e}")
                    time.sleep(0.5)  # 限速，避免触发百度翻译 QPS 限制
                    lyrics.append((round(start + seg_dur * j, 2), s, tr))
            idx += 1

    try:
        os.remove(pcm_path)
    except OSError:
        pass

    lyrics.sort(key=lambda x: x[0])
    log(f"自动识别完成，共 {len(lyrics)} 句。")
    return lyrics


# whisper 语言代码（ISO 639-1）→ 百度翻译 from 代码
WHISPER_TO_BAIDU_LANG = {
    'ja': 'jp', 'ru': 'ru', 'en': 'en', 'zh': 'zh', 'ko': 'kor',
    'fr': 'fra', 'es': 'spa', 'de': 'de', 'it': 'it', 'pt': 'pt',
    'ar': 'ara', 'th': 'th', 'vi': 'vie', 'nl': 'nl', 'pl': 'pl',
}


def _load_audio_as_numpy(music_path):
    """用 ffmpeg 转成 16k 单声道 wav，再用 numpy 读成 float32 数组。
    绕过 faster-whisper 用 av 解码时与新版 av 不兼容（metadata_errors 参数）的问题。"""
    import subprocess
    import wave
    ffmpeg = _get_ffmpeg_exe()
    out_dir = os.path.dirname(os.path.abspath(music_path)) or '.'
    tmp_wav = os.path.join(out_dir, '_lyrics_tmp.wav')
    subprocess.run(
        [ffmpeg, '-y', '-i', music_path, '-ac', '1', '-ar', '16000', tmp_wav],
        capture_output=True)
    with wave.open(tmp_wav, 'rb') as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    try:
        os.remove(tmp_wav)
    except OSError:
        pass
    return audio.astype(np.float32) / 32768.0


def whisper_recognize_lyrics(music_path, app_id, trans_key, to_lang='zh',
                             model_size='small', model_path='', language='auto',
                             progress_cb=None):
    """
    用本地 faster-whisper 识别歌词并翻译，返回 [(start_sec, text, translation), ...]。
    句级时间戳精确。language='auto' 自动检测，或指定 'ja'/'ru'/'en' 等 ISO 代码。
    model_path 指定本地模型目录（含 model.bin），留空则按 model_size 自动下载。
    """
    def log(msg, cur=None, tot=None):
        print(msg)
        if progress_cb:
            progress_cb(msg, cur, tot)

    import time
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log("未安装 faster-whisper，请先在系统终端运行：pip install faster-whisper")
        return []

    model_ref = model_path if model_path else model_size
    log(f"加载 Whisper 模型：{model_ref}")
    try:
        model = WhisperModel(model_ref, device="cpu", compute_type="int8")
    except Exception as e:
        log(f"模型加载失败（请检查路径是否正确）：{e}")
        return []

    lang = None if language in ('auto', '') else language
    log("正在解码音频...")
    audio = _load_audio_as_numpy(music_path)
    duration = len(audio) / 16000
    est_min = (duration * 0.4 + duration / 3 * 0.7) / 60  # 识别约 0.4x 实时，翻译约 0.7s/句
    log(f"音频时长约 {duration:.0f} 秒，预计需要约 {est_min:.1f} 分钟")

    log("正在提取歌词（语音转文字）...")
    # 注意：不开启 vad_filter，否则在部分环境会把整首歌误判为纯音乐而过滤掉
    segments, info = model.transcribe(audio, language=lang, beam_size=5)
    detected = info.language
    from_lang = WHISPER_TO_BAIDU_LANG.get(detected, detected)
    log(f"检测到语言：{detected}，翻译方向：{from_lang} -> {to_lang}")

    lyrics = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            tr = None
            if app_id and trans_key:
                try:
                    tr = baidu_translate(text, app_id, trans_key, from_lang, to_lang)
                except Exception as e:
                    log(f"  翻译失败：{e}")
                time.sleep(0.5)  # 限速，避免触发百度翻译 QPS 限制
            lyrics.append((round(seg.start, 2), text, tr))
        # 进度：识别到音频的 seg.end 位置，翻译同步推进（仅更新浮动标签，不刷日志）
        if duration and progress_cb:
            pct = min(seg.end / duration, 1.0) * 100
            progress_cb(f"正在提取并翻译歌词 {len(lyrics)} 句（{pct:.0f}%）", seg.end, duration)

    lyrics.sort(key=lambda x: x[0])
    log(f"歌词提取并翻译完成，共 {len(lyrics)} 句。")
    if progress_cb:
        progress_cb(f"歌词提取并翻译完成，共 {len(lyrics)} 句", duration, duration)
    return lyrics


def recognize_lyrics(music_path, engine='whisper', language='auto', to_lang='zh',
                     model_size='small', model_path='', api_key='', secret_key='',
                     app_id='', trans_key='', chunk_sec=50, progress_cb=None):
    """统一歌词识别入口，按引擎分发到 whisper（本地）或 baidu（在线）。"""
    if engine == 'whisper':
        return whisper_recognize_lyrics(music_path, app_id, trans_key, to_lang,
                                        model_size, model_path, language, progress_cb)
    from_lang = 'en'
    if language not in ('auto', ''):
        from_lang = WHISPER_TO_BAIDU_LANG.get(language, language)
    return auto_recognize_lyrics(music_path, api_key, secret_key, app_id, trans_key,
                                 from_lang, to_lang, chunk_sec, progress_cb)


def render_lyric_preview(psd_path, lyric_text, lyric_trans=None, max_side=520):
    """合成完整作品画面并叠加一句歌词，返回 PIL RGB 图（用于歌词画面预览）。"""
    psd = PSDImage.open(psd_path)
    img = psd.composite().convert('RGBA')
    bg = Image.new('RGBA', img.size, BG_COLOR + (255,))
    rgb = Image.alpha_composite(bg, img).convert('RGB')
    if max_side and max(rgb.size) > max_side:
        scale = max_side / max(rgb.size)
        rgb = rgb.resize((round(rgb.width * scale), round(rgb.height * scale)), Image.LANCZOS)
    sx = rgb.width / psd.size[0]
    sy = rgb.height / psd.size[1]
    lyric_layer, trans_layer = find_lyric_layers(psd)
    if lyric_layer and lyric_text:
        font, color, xy = _lyric_style(lyric_layer, sx, sy)
        draw_text_with_alpha(rgb, xy, lyric_text, font, color, 255, anchor='ls')
        if lyric_trans and trans_layer:
            tfont, tcolor, txy = _lyric_style(trans_layer, sx, sy)
            draw_text_with_alpha(rgb, txy, lyric_trans, tfont, tcolor, 255, anchor='ls')
    return rgb


if __name__ == "__main__":
    main()
