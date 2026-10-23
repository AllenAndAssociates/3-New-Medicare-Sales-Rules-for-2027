"""9:16 USAFacts-style composite for "3 New Medicare Sales Rules for 2027".

Pipes keyed green-screen footage through a PIL graphics layer and into ffmpeg.
Usage: python3 render.py [--start S] [--end E] [--still T ...] [--out FILE]
"""
import argparse
import json
import math
import os
import subprocess
import sys
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1080, 1920, 30
TAIL = 0.7  # hold on last frame so the final chord rings out

# ---------------------------------------------------------------- timeline
C1 = "Man_speaking_about_Medicare_rules_20261023175043.mp4"
C2 = "Man_speaking_to_camera_720p_20261023174212.mp4"
C3 = "Presenter_explaining_Medicare_ed…_720p_20261023174558.mp4"
C4 = "Presenter_explaining_waiting_rul…_720p_20261023174322.mp4"
C5 = "Presenter_giving_Medicare_guidance_720p_20261023174956.mp4"
C6 = "Presenter_speaking_about_Medicar…_720p_20261023175136.mp4"
C7 = "Presenter_speaking_about_Medicar…_720p_20261023175346.mp4"
C8 = "Presenter_speaking_against_green…_720p_20261023174859.mp4"
C9 = "Presenter_speaking_to_camera_720p_20261023174650.mp4"
C10 = "Presenter_speaking_to_camera_720p_20261023174737.mp4"

# "First: the 48-hour waiting rule is gone" isn't in any clip; it plays as VO
# over a full-screen Rule #1 card (speaker hidden, so no lip-sync mismatch).
VO_FIRST = "audio/vo_first.wav"
VO_LEAD, VO_LEN, VO_GONE = 0.15, 2.42, 2.16   # lead-in, line length, "gone" onset
TK_DUR = VO_LEAD + VO_LEN + 0.22

# (scene, clip, in, out, X fraction, scale, slide frames, opts)
# Trimmed to the spoken line; silent holds removed. opts: dur (retime hidden
# filler), mute, fade (clip-time voice fade-out window).
SEGMENTS = [
    (1, C1, 0.90, 8.72, 0.50, 1.05, 0, {}),                        # hook
    (2, C2, 1.20, 3.72, 0.50, 1.18, 0, {}),                        # intro (silent smile cut)
    ("tk", C2, 3.72, 6.00, 0.50, 1.18, 0, {"dur": TK_DUR, "mute": True}),  # Rule #1 takeover (hidden)
    (3, C4, 0.80, 5.72, 0.38, 0.95, 10, {}),                       # rule 1a
    (4, C6, 0.56, 5.15, 0.38, 1.10, 0, {}),                        # rule 1b ... "Part D drug plans."
    (4, C6, 5.62, 8.60, 0.38, 1.00, 0, {}),                        # jump cut -> "Now, you can meet..."
    (5, C3, 0.00, 5.15, 0.38, 0.95, 0, {}),                        # rule 2a
    (6, C9, 0.05, 7.70, 0.38, 1.10, 0, {}),                        # rule 2b
    (7, C10, 0.12, 7.75, 0.62, 0.95, 12, {}),                      # rule 3
    (8, C8, 0.55, 5.80, 0.62, 1.12, 0, {}),                        # nuance
    (9, C7, 0.00, 9.55, 0.50, 0.90, 10, {"fade": (9.30, 9.40)}),   # takeaway (natural end on "told")
    (10, C5, 0.20, 8.00, 0.50, 1.05, 0, {}),                       # CTA
]


def seg_len(seg):
    return seg[7].get("dur", seg[3] - seg[2])


STARTS = [0.0]
for _seg in SEGMENTS:
    STARTS.append(STARTS[-1] + seg_len(_seg))
SPEECH_END = STARTS[-1]
DURATION = SPEECH_END + TAIL


def S(n):
    """Start time of scene n (first segment carrying that scene id)."""
    return next(STARTS[i] for i, sg in enumerate(SEGMENTS) if sg[0] == n)


def Wd(n, clip_t):
    """Timeline time of a word spoken at clip_t inside scene n's source clip."""
    segs = [(i, sg) for i, sg in enumerate(SEGMENTS) if sg[0] == n]
    for i, sg in segs:
        if clip_t <= sg[3]:
            return STARTS[i] + max(0.0, clip_t - sg[2])
    i, sg = segs[-1]
    return STARTS[i] + clip_t - sg[2]


# Key moments (all synced to transcript word timings)
T = dict(
    header=0.20,
    tab1=Wd(1, 2.16), tab2=Wd(1, 2.16) + 0.18, tab3=Wd(1, 2.16) + 0.36,
    qping=Wd(1, 7.96),
    name=S(2) + 0.12,
    tk=S("tk"), vo=S("tk") + VO_LEAD, gone=S("tk") + VO_LEAD + VO_GONE,
    card1=S("tk"), red1=Wd(3, 2.30) - 0.20, watch=Wd(3, 2.30),
    pill_ma=Wd(4, 2.78), pill_pd=Wd(4, 3.76),
    strike1=Wd(4, 5.85), green1=Wd(4, 6.86), chime1=Wd(4, 7.90),
    dock1=S(5), card2=S(5) + 0.28, flow2=Wd(5, 3.02),
    old2=S(6) + 0.15, wait12=Wd(6, 3.96), buzz2=Wd(6, 4.32),
    new2=Wd(6, 6.26), click2=Wd(6, 7.04),
    dock2=S(7), card3=S(7) + 0.12, tv=S(7) + 0.75, music_back=Wd(7, 3.34),
    best=Wd(7, 4.86), most=Wd(7, 5.30),
    false3=Wd(8, 1.66), warn3=Wd(8, 3.78),
    dock3=S(9), stack=S(9) + 0.30, footer=S(9) + 1.30, swipe=Wd(9, 8.00),
    out=S(10), cta=S(10) + 0.22, phone=Wd(10, 3.42), phone_end=Wd(10, 5.40),
    web=Wd(10, 5.82), webclick=Wd(10, 6.32),
)

# ---------------------------------------------------------------- style
BG = (244, 244, 240)
# Default navy canvas (white cards, glow behind speaker); THEME=light for the off-white variant
NAVY_THEME = os.environ.get("THEME", "navy") == "navy"
NAVY_BG = (12, 31, 60)
NAVY_LIFT = (24, 54, 96)          # header / CTA fill on the navy canvas
NAVY = (11, 37, 69)
INK = (28, 31, 36)
MUTED = (96, 102, 112)
LINE = (217, 217, 210)
WHITE = (255, 255, 255)
RED = (205, 52, 48)
RED_BG = (252, 230, 228)
GREEN = (28, 135, 84)
GREEN_BG = (222, 243, 231)
AMBER = (232, 160, 20)
AMBER_BG = (255, 243, 214)
GOLD = (201, 162, 39)
GOLD_LT = (240, 210, 110)
HILITE = (255, 214, 64)

FONT_DIR = "/usr/share/fonts/opentype/inter"


@lru_cache(None)
def font(weight, size):
    name = {"xb": "Inter-ExtraBold", "b": "Inter-Bold", "sb": "Inter-SemiBold",
            "m": "Inter-Medium", "black": "Inter-Black"}[weight]
    return ImageFont.truetype(f"{FONT_DIR}/{name}.otf", size)


# Layout (px)
MX = 54                      # 90% width card => 972 px
CW = W - 2 * MX
HEADER = (MX, 150, W - MX, 240)
TAB_Y0, TAB_Y1 = 262, 340
TAB_GAP = 18
TAB_W = (CW - 2 * TAB_GAP) / 3
CARD = (MX, 366, W - MX, 1010)


def tab_rect(i):
    x0 = MX + i * (TAB_W + TAB_GAP)
    return (x0, TAB_Y0, x0 + TAB_W, TAB_Y1)


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, t0, dur):
    return clamp((t - t0) / dur) if dur > 0 else float(t >= t0)


def ease_out(x):
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_back(x, s=1.70158):
    x = clamp(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def pop_scale(t, t0, dur=0.32):
    """0 -> overshoot -> 1."""
    return ease_back(prog(t, t0, dur), 2.2)


def lerp(a, b, x):
    return a + (b - a) * x


def lerp_rect(r0, r1, x):
    return tuple(lerp(a, b, x) for a, b in zip(r0, r1))


# ---------------------------------------------------------------- drawing helpers
def rrect(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle([round(v) for v in box], radius=r, fill=fill, outline=outline, width=width)


def text_size(txt, f):
    l, t, r, b = f.getbbox(txt)
    return r - l, b - t, l, t


def draw_text(d, xy, txt, f, fill, anchor="la"):
    d.text(xy, txt, font=f, fill=fill, anchor=anchor)


def fit_font(txt, weight, size, maxw):
    while size > 20 and text_size(txt, font(weight, size))[0] > maxw:
        size -= 2
    return font(weight, size)


def wrap(txt, f, maxw):
    words, lines, cur = txt.split(), [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if text_size(trial, f)[0] <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    lines.append(cur)
    return lines


def paste(layer, img, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    """Paste RGBA img centred at (cx, cy) with scale/alpha."""
    if scale <= 0.01 or alpha <= 0.005:
        return
    if rot:
        img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    if abs(scale - 1) > 1e-3:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.BICUBIC)
    if alpha < 0.999:
        a = img.getchannel("A").point(lambda v: int(v * alpha))
        img = img.copy()
        img.putalpha(a)
    layer.alpha_composite(img, (round(cx - img.width / 2), round(cy - img.height / 2)))


def blank(w, h):
    return Image.new("RGBA", (int(round(w)), int(round(h))), (0, 0, 0, 0))


# ---------------------------------------------------------------- icons
def icon_check(size, color=GREEN):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, size - 1, size - 1], fill=color)
    s = size
    d.line([(s * .27, s * .52), (s * .44, s * .69), (s * .74, s * .34)], fill=WHITE, width=max(3, int(s * .11)), joint="curve")
    return im


def icon_x(size, color=RED):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, size - 1, size - 1], fill=color)
    s, w_ = size, max(3, int(size * .11))
    d.line([(s * .32, s * .32), (s * .68, s * .68)], fill=WHITE, width=w_)
    d.line([(s * .68, s * .32), (s * .32, s * .68)], fill=WHITE, width=w_)
    return im


def icon_warn(size, color=AMBER):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    s = size
    d.polygon([(s * .5, s * .04), (s * .97, s * .92), (s * .03, s * .92)], fill=color)
    d.rounded_rectangle([s * .45, s * .32, s * .55, s * .64], radius=int(s * .04), fill=WHITE)
    d.ellipse([s * .44, s * .71, s * .56, s * .83], fill=WHITE)
    return im


def icon_clock(size, t_rot=0.0, color=RED):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    s = size
    lw = max(3, int(s * .09))
    d.ellipse([lw / 2, lw / 2, s - lw / 2, s - lw / 2], outline=color, width=lw, fill=WHITE)
    c = s / 2
    d.line([(c, c), (c, c - s * .26)], fill=color, width=lw)
    a = t_rot * 2 * math.pi
    d.line([(c, c), (c + math.sin(a) * s * .3, c - math.cos(a) * s * .3)], fill=INK, width=max(2, lw - 2))
    d.ellipse([c - lw, c - lw, c + lw, c + lw], fill=color)
    return im


def icon_phone(size, color=GOLD):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    s = size
    d.ellipse([0, 0, s - 1, s - 1], fill=color)
    # simple handset
    hs = blank(s, s)
    hd = ImageDraw.Draw(hs)
    hd.rounded_rectangle([s * .42, s * .2, s * .58, s * .8], radius=int(s * .08), fill=NAVY)
    hd.rounded_rectangle([s * .3, s * .17, s * .58, s * .33], radius=int(s * .07), fill=NAVY)
    hd.rounded_rectangle([s * .3, s * .67, s * .58, s * .83], radius=int(s * .07), fill=NAVY)
    hs = hs.rotate(-35, resample=Image.BICUBIC, center=(s / 2, s / 2))
    im.alpha_composite(hs)
    return im


def icon_globe(size, color=GOLD):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    s = size
    d.ellipse([0, 0, s - 1, s - 1], fill=color)
    lw = max(2, int(s * .06))
    p = s * .2
    d.ellipse([p, p, s - p, s - p], outline=NAVY, width=lw)
    d.ellipse([s * .38, p, s * .62, s - p], outline=NAVY, width=lw)
    d.line([(p, s / 2), (s - p, s / 2)], fill=NAVY, width=lw)
    return im


def icon_tv(w_, h_):
    im = blank(w_, h_ + 70)
    d = ImageDraw.Draw(im)
    # antenna
    d.line([(w_ * .5, 46), (w_ * .36, 4)], fill=NAVY, width=7)
    d.line([(w_ * .5, 46), (w_ * .64, 4)], fill=NAVY, width=7)
    d.ellipse([w_ * .5 - 10, 36, w_ * .5 + 10, 56], fill=NAVY)
    d.rounded_rectangle([0, 50, w_, h_ + 20], radius=28, fill=NAVY)
    d.rounded_rectangle([22, 72, w_ - 22, h_ - 2], radius=16, fill=(32, 70, 120))
    # stand
    d.rounded_rectangle([w_ * .32, h_ + 26, w_ * .68, h_ + 40], radius=7, fill=NAVY)
    d.rectangle([w_ * .47, h_ + 16, w_ * .53, h_ + 30], fill=NAVY)
    # screen shine + "AD" label
    d.polygon([(40, 86), (w_ * .42, 86), (w_ * .25, h_ - 16), (40, h_ - 16)], fill=(42, 84, 140))
    f = font("xb", int(h_ * .2))
    d.text((w_ / 2, (72 + h_) / 2), "TV AD", font=f, fill=(150, 185, 225), anchor="mm")
    return im


def icon_easel(size):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    s = size
    d.line([(s * .5, s * .7), (s * .3, s * .98)], fill=NAVY, width=7)
    d.line([(s * .5, s * .7), (s * .7, s * .98)], fill=NAVY, width=7)
    d.rounded_rectangle([s * .08, s * .08, s * .92, s * .72], radius=10, fill=WHITE, outline=NAVY, width=7)
    for i, hgt in enumerate([.22, .34, .16]):
        x = s * (.28 + i * .18)
        d.rectangle([x, s * (.62 - hgt), x + s * .11, s * .62], fill=[NAVY, GOLD, (90, 140, 200)][i])
    return im


def icon_sales(size):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    s = size
    d.ellipse([s * .04, s * .04, s * .96, s * .96], fill=GREEN_BG, outline=GREEN, width=7)
    f = font("black", int(s * .5))
    d.text((s / 2, s / 2 + 2), "$", font=f, fill=GREEN, anchor="mm")
    return im


def icon_cursor(size):
    im = blank(size, size)
    d = ImageDraw.Draw(im)
    s = size
    pts = [(s * .1, s * .05), (s * .1, s * .8), (s * .3, s * .62), (s * .45, s * .95), (s * .58, s * .89),
           (s * .43, s * .57), (s * .7, s * .57)]
    d.polygon(pts, fill=WHITE, outline=INK)
    d.line(pts + [pts[0]], fill=INK, width=3)
    return im


LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "allen-associates-logo.png")


@lru_cache(None)
def official_logo(width):
    """Official Allen & Associates logo (white background), scaled to width."""
    im = Image.open(LOGO).convert("RGBA")
    return im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)


# ---------------------------------------------------------------- reusable components
def shadowed_card(w_, h_, fill=WHITE, radius=24, accent=None, accent_h=12, outline=None):
    pad = 30
    im = blank(w_ + 2 * pad, h_ + 2 * pad)
    sh = blank(w_ + 2 * pad, h_ + 2 * pad)
    ImageDraw.Draw(sh).rounded_rectangle([pad, pad + 8, pad + w_, pad + h_ + 8], radius=radius, fill=(10, 30, 60, 46))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    im.alpha_composite(sh)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([pad, pad, pad + w_, pad + h_], radius=radius, fill=fill, outline=outline, width=2 if outline else 0)
    if accent:
        mask = blank(w_ + 2 * pad, h_ + 2 * pad)
        ImageDraw.Draw(mask).rounded_rectangle([pad, pad, pad + w_, pad + h_], radius=radius, fill=WHITE)
        bar = blank(w_ + 2 * pad, h_ + 2 * pad)
        ImageDraw.Draw(bar).rectangle([pad, pad, pad + w_, pad + accent_h], fill=accent)
        bar.putalpha(Image.fromarray(np.minimum(np.array(bar.getchannel("A")), np.array(mask.getchannel("A")))))
        im.alpha_composite(bar)
    return im, pad


def draw_card_frame(layer, rect, accent, alpha=1.0, fill=WHITE):
    x0, y0, x1, y1 = rect
    w_, h_ = x1 - x0, y1 - y0
    if w_ < 4 or h_ < 4:
        return
    im, pad = _card_cached(int(w_), int(h_), accent, fill)
    paste(layer, im, (x0 + x1) / 2, (y0 + y1) / 2, 1.0, alpha)


@lru_cache(64)
def _card_cached(w_, h_, accent, fill):
    r = min(24, h_ // 2)
    return shadowed_card(w_, h_, fill=fill, radius=r, accent=accent, accent_h=12 if h_ > 200 else 0)


@lru_cache(None)
def callout_box(kind, label, body, width, height=150):
    """Red OLD / green 2027 rule box."""
    col, bg, ic = {"old": (RED, RED_BG, "clock"), "new": (GREEN, GREEN_BG, "check")}[kind]
    im = blank(width, height)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, width - 1, height - 1], radius=18, fill=bg)
    d.rounded_rectangle([0, 0, 12, height - 1], radius=6, fill=col)
    draw_text(d, (128, 26), label, font("xb", 28), col)
    f = fit_font(body, "b", 42, width - 160)
    draw_text(d, (128, 66), body, f, INK)
    return im


def tv_bubble(text, color):
    f = font("black", 46)
    tw, th, l, t = text_size(text, f)
    w_, h_ = tw + 56, th + 46
    im = blank(w_, h_ + 26)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w_ - 1, h_ - 1], radius=22, fill=color, outline=NAVY, width=5)
    d.polygon([(w_ * .3, h_ - 4), (w_ * .44, h_ - 4), (w_ * .26, h_ + 24)], fill=color, outline=None)
    d.line([(w_ * .3, h_ - 3), (w_ * .26, h_ + 24), (w_ * .44, h_ - 3)], fill=NAVY, width=5)
    d.text((w_ / 2, h_ / 2), text, font=f, fill=NAVY, anchor="mm")
    return im


@lru_cache(None)
def badge(kind, text, width):
    col, bg, icon = {"x": (RED, RED_BG, icon_x), "warn": ((176, 112, 0), AMBER_BG, icon_warn)}[kind]
    h_ = 96
    im = blank(width, h_)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, width - 1, h_ - 1], radius=20, fill=bg, outline=col, width=3)
    ic = icon(58, RED if kind == "x" else AMBER)
    im.alpha_composite(ic, (24, (h_ - 58) // 2))
    f = fit_font(text, "xb", 40, width - 120)
    d.text((104, h_ / 2), text, font=f, fill=INK, anchor="lm")
    return im


@lru_cache(None)
def pill(text, fill, fg, size=32, pad=26, h_=60, outline=None):
    f = font("b", size)
    tw = text_size(text, f)[0]
    im = blank(tw + 2 * pad, h_)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, tw + 2 * pad - 1, h_ - 1], radius=h_ // 2, fill=fill, outline=outline, width=3 if outline else 0)
    d.text(((tw + 2 * pad) / 2, h_ / 2), text, font=f, fill=fg, anchor="mm")
    return im


# ---------------------------------------------------------------- graphics layer
TAB_LABELS = ["1", "2", "3 ?"]
TAB_DONE = ["1: No 48-Hr Wait", "2: Seminar Sales", "3: Ad Wording"]


def tab_state(i, t):
    """Return (label, fill, fg, outline, check)."""
    done_at = [T["dock1"], T["dock2"], T["dock3"]][i]
    active_from = [T["card1"], T["card2"], T["card3"]][i]
    if t >= done_at:
        return TAB_DONE[i], WHITE, NAVY, GREEN, True
    if t >= active_from:
        if i == 2:
            return "3: Ad Wording", AMBER, NAVY, None, False
        if NAVY_THEME:
            return TAB_DONE[i], (40, 84, 142), WHITE, GOLD, False
        return TAB_DONE[i], NAVY, WHITE, None, False
    if i == 2 and t >= T["qping"]:
        return "3 ?", AMBER_BG, (150, 95, 0), AMBER, False
    return TAB_LABELS[i], WHITE, NAVY, LINE, False


@lru_cache(None)
def tab_img(label, fill, fg, outline, check):
    w_, h_ = int(TAB_W), TAB_Y1 - TAB_Y0
    im = blank(w_ + 20, h_ + 20)
    sh = blank(w_ + 20, h_ + 20)
    ImageDraw.Draw(sh).rounded_rectangle([10, 14, 10 + w_, 10 + h_ + 4], radius=h_ // 2, fill=(10, 30, 60, 30))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 10, 10 + w_, 10 + h_], radius=h_ // 2, fill=fill, outline=outline, width=3 if outline else 0)
    big = len(label) <= 3
    f = font("xb", 40) if big else fit_font(label, "b", 31, w_ - (64 if check else 30))
    cx = 10 + w_ / 2 + (16 if check else 0)
    d.text((cx, 10 + h_ / 2), label, font=f, fill=fg, anchor="mm")
    if check:
        tw = text_size(label, f)[0]
        im.alpha_composite(icon_check(34), (int(cx - tw / 2 - 44), int(10 + h_ / 2 - 17)))
    return im


@lru_cache(None)
def header_img():
    x0, y0, x1, y1 = HEADER
    im, pad = shadowed_card(x1 - x0, y1 - y0, fill=NAVY_LIFT if NAVY_THEME else NAVY, radius=16)
    d = ImageDraw.Draw(im)
    f = font("xb", 42)
    d.text((pad + (x1 - x0) / 2, pad + (y1 - y0) / 2), "2027 MEDICARE MARKETING RULES", font=f, fill=WHITE, anchor="mm")
    d.rectangle([pad + 24, pad + (y1 - y0) - 8, pad + (x1 - x0) - 24, pad + (y1 - y0) - 5], fill=GOLD)
    return im


def card_title(layer, rect, title, alpha, color=NAVY, y_off=56):
    x0, y0, x1, y1 = rect
    f = font("xb", 54)
    lines = wrap(title, f, (x1 - x0) - 96)
    im = blank(x1 - x0, 70 * len(lines) + 10)
    d = ImageDraw.Draw(im)
    for k, ln in enumerate(lines):
        d.text((48, 4 + 68 * k), ln, font=f, fill=color)
    paste(layer, im, (x0 + x1) / 2, y0 + y_off + im.height / 2, 1.0, alpha)
    return y0 + y_off + im.height


def card_rect_for(t, idx, t_open, t_dock):
    """Interpolate between tab and card rect for open (t_open) and dock (t_dock)."""
    tr = tab_rect(idx)
    if t < t_open:
        return None, 0
    po = ease_out(prog(t, t_open, 0.38))
    if t_dock is not None and t >= t_dock:
        pd = ease_in_out(prog(t, t_dock, 0.28))
        if pd >= 1:
            return None, 0
        return lerp_rect(CARD, tr, pd), 1 - pd
    return lerp_rect(tr, CARD, po), po


def strike(d, x0, y, x1, p, color=RED, width=8):
    if p <= 0:
        return
    d.line([(x0, y), (lerp(x0, x1, p), y)], fill=color, width=width)


TKR = (-40, -40, W + 40, H + 40)   # full-screen Rule #1 takeover card (corners bleed off-frame)


@lru_cache(None)
def takeover1_img():
    im = blank(CW, 1300)
    d = ImageDraw.Draw(im)
    lab = pill("RULE #1", NAVY, WHITE, size=44, pad=34, h_=82)
    im.alpha_composite(lab, ((CW - lab.width) // 2, 40))
    f = font("black", 100)
    for k, ln in enumerate(["48-Hour", "Waiting Rule", "Is Gone"]):
        d.text((CW / 2, 840 + k * 118), ln, font=f, fill=NAVY if k < 2 else RED, anchor="mm")
    d.rectangle([CW / 2 - 110, 1200, CW / 2 + 110, 1210], fill=GOLD)
    return im


def draw_takeover1(layer, rect, t, a):
    x0, y0, x1, y1 = rect
    cy = (y0 + y1) / 2
    paste(layer, takeover1_img(), (x0 + x1) / 2, cy, 1, a)
    clock_y = cy - 650 + 470
    spin = prog(t, T["vo"], VO_LEN) * 1.5
    paste(layer, icon_clock(320, spin), (x0 + x1) / 2, clock_y, 1, a)
    if t >= T["gone"]:
        ps = prog(t, T["gone"], 0.18)
        paste(layer, stamp_img("GONE"), (x0 + x1) / 2 + 150, clock_y + 110,
              lerp(2.6, 1.6, ease_out(ps)), ease_out(ps) * a, rot=12)


def draw_card1(layer, t):
    if t < T["tk"] or t >= T["dock1"] + 0.28:
        return
    tr = tab_rect(0)
    ta = ca = 0.0
    if t >= T["dock1"]:
        pd = ease_in_out(prog(t, T["dock1"], 0.28))
        rect, ca = lerp_rect(CARD, tr, pd), 1 - pd
    elif t >= S(3):
        q = ease_in_out(prog(t, S(3), 0.4))
        rect = lerp_rect(TKR, CARD, q)
        ta, ca = 1 - clamp(q / 0.4), clamp((q - 0.6) / 0.4)
    else:
        p = ease_out(prog(t, T["tk"], 0.3))
        rect, ta = lerp_rect(tr, TKR, p), clamp((p - 0.6) / 0.4)
    draw_card_frame(layer, rect, NAVY)
    if ta > 0:
        draw_takeover1(layer, rect, t, ta)
    if ca <= 0:
        return
    x0, y0, x1, y1 = rect
    ty = card_title(layer, rect, "#1: 48-Hour Waiting Rule Is Gone", ca)
    bw = int(CW - 96)
    bx = x0 + 48
    # OLD box
    if t >= T["red1"]:
        a = ca * ease_out(prog(t, T["red1"], 0.3))
        sp = 0.85 + 0.15 * ease_back(prog(t, T["red1"], 0.3))
        box = callout_box("old", "OLD RULE", "Sign Form  →  Wait 48 Hours", bw).copy()
        bd = ImageDraw.Draw(box)
        spin = prog(t, T["watch"], 1.5) * 2.5
        box.alpha_composite(icon_clock(80, spin), (30, 35))
        fade = 1.0
        if t >= T["strike1"]:
            sp_ = ease_out(prog(t, T["strike1"], 0.22))
            f = fit_font("Sign Form  →  Wait 48 Hours", "b", 42, bw - 160)
            tw = text_size("Sign Form  →  Wait 48 Hours", f)[0]
            strike(bd, 120, 92, 136 + tw, sp_, RED, 9)
            fade = 1 - 0.4 * sp_
        oy = ty + 30
        paste(layer, box, bx + bw / 2, oy + 75, sp, a * fade)
        # stamp "GONE" on the cross-out
        if t >= T["strike1"]:
            ps = prog(t, T["strike1"], 0.18)
            st = stamp_img("GONE")
            paste(layer, st, bx + bw - 130, oy + 70, lerp(1.8, 1.0, ease_out(ps)), ease_out(ps) * ca, rot=12)
        # program pills
        py = oy + 150 + 50
        if t >= T["pill_ma"]:
            pi = pill("Medicare Advantage", WHITE, NAVY, outline=NAVY)
            paste(layer, pi, bx + 30 + pi.width / 2, py, pop_scale(t, T["pill_ma"]), ca)
            if t >= T["pill_pd"]:
                pj = pill("Part D", WHITE, NAVY, outline=NAVY)
                paste(layer, pj, bx + 30 + pi.width + 20 + pj.width / 2, py, pop_scale(t, T["pill_pd"]), ca)
        # NEW box
        if t >= T["green1"]:
            pg = ease_out(prog(t, T["green1"], 0.35))
            gbox = callout_box("new", "2027 RULE", "Sign Form  →  Meet Right Away", bw).copy()
            gbox.alpha_composite(icon_check(80), (30, 35))
            gy = py + 60 + 75
            paste(layer, gbox, bx + bw / 2, gy + 40 * (1 - pg), 1.0, ca * pg)
            if t >= T["chime1"]:
                glow = 1 - prog(t, T["chime1"], 0.6)
                if glow > 0:
                    ring = blank(bw + 40, 190)
                    ImageDraw.Draw(ring).rounded_rectangle([4, 4, bw + 36, 186], radius=24, outline=GREEN, width=6)
                    paste(layer, ring, bx + bw / 2, gy, 1 + 0.04 * (1 - glow), glow * ca)
                ck = icon_check(70)
                paste(layer, ck, bx + bw - 60, gy, pop_scale(t, T["chime1"], 0.35), ca)


@lru_cache(None)
def stamp_img(word, color=RED):
    f = font("black", 52)
    tw = text_size(word, f)[0]
    im = blank(tw + 50, 92)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([3, 3, tw + 46, 88], radius=12, outline=color, width=6)
    d.text(((tw + 50) / 2, 46), word, font=f, fill=color, anchor="mm")
    return im


def draw_card2(layer, t):
    rect, p = card_rect_for(t, 1, T["card2"], T["dock2"])
    if rect is None:
        return
    draw_card_frame(layer, rect, NAVY)
    ca = clamp((p - 0.6) / 0.4)
    if ca <= 0:
        return
    x0, y0, x1, y1 = rect
    ty = card_title(layer, rect, "#2: Educational Seminars → Sales", ca)
    bw = int(CW - 96)
    bx = x0 + 48
    # flow illustration (scene 5), fades as comparison rows arrive (scene 6)
    if t >= T["flow2"]:
        pf = ease_out(prog(t, T["flow2"], 0.45))
        fo = 1 - ease_out(prog(t, T["old2"] - 0.1, 0.3))
        a = ca * pf * fo
        if a > 0:
            cy = ty + 200
            slide = 120 * (1 - pf)
            ea = icon_easel(200)
            paste(layer, ea, bx + 150 - slide, cy, 1, a)
            lab = blank(300, 60)
            ImageDraw.Draw(lab).text((150, 30), "Seminar", font=font("b", 38), fill=NAVY, anchor="mm")
            paste(layer, lab, bx + 150 - slide, cy + 140, 1, a)
            ar = blank(240, 60)
            ad = ImageDraw.Draw(ar)
            ad.line([(10, 30), (200, 30)], fill=GOLD, width=12)
            ad.polygon([(190, 6), (236, 30), (190, 54)], fill=GOLD)
            paste(layer, ar, bx + bw / 2, cy, 1, a)
            sa = icon_sales(190)
            paste(layer, sa, bx + bw - 150 + slide, cy, 1, a)
            lab2 = blank(300, 60)
            ImageDraw.Draw(lab2).text((150, 30), "Sales Pitch", font=font("b", 38), fill=GREEN, anchor="mm")
            paste(layer, lab2, bx + bw - 150 + slide, cy + 140, 1, a)
    # comparison rows (scene 6)
    if t >= T["old2"]:
        po = ease_out(prog(t, T["old2"], 0.35))
        row = compare_row("old", bw).copy()
        rd = ImageDraw.Draw(row)
        if t >= T["wait12"]:
            hp = ease_out(prog(t, T["wait12"], 0.25))
            hx0, hx1 = row_seg_x("old")
            hl = blank(row.width, row.height)
            ImageDraw.Draw(hl).rounded_rectangle([hx0 - 10, 40, lerp(hx0 - 10, hx1 + 10, hp), 112], radius=10, fill=(255, 205, 200))
            hl.alpha_composite(row)
            row = hl
            rd = ImageDraw.Draw(row)
        fade = 1.0
        if t >= T["buzz2"]:
            sp_ = ease_out(prog(t, T["buzz2"], 0.2))
            hx0, hx1 = row_seg_x("old")
            strike(rd, hx0 - 6, 78, hx1 + 6, sp_, RED, 9)
            fade = 1 - 0.3 * sp_
        oy = ty + 60
        paste(layer, row, bx + bw / 2, oy + 75 - 30 * (1 - po), 1, ca * po * fade)
        if t >= T["buzz2"]:
            paste(layer, icon_x(76), bx + bw - 70, oy + 75, pop_scale(t, T["buzz2"]), ca)
        if t >= T["new2"]:
            pn = ease_out(prog(t, T["new2"], 0.35))
            nrow = compare_row("new", bw)
            ny = oy + 75 + 190
            paste(layer, nrow, bx + bw / 2 + 80 * (1 - pn), ny, 1, ca * pn)
            if t >= T["click2"]:
                pc = prog(t, T["click2"], 0.5)
                hx0, hx1 = row_seg_x("new")
                ring = blank(hx1 - hx0 + 60, 110)
                ImageDraw.Draw(ring).rounded_rectangle([3, 3, hx1 - hx0 + 57, 107], radius=20, outline=GREEN, width=6)
                if pc < 1:
                    paste(layer, ring, bx + (hx0 + hx1) / 2, ny, 1 + 0.15 * pc, (1 - pc) * ca)
                paste(layer, icon_check(76), bx + bw - 70, ny, pop_scale(t, T["click2"]), ca)


ROW_TXT = {"old": ("OLD", "Seminar  →  ", "12-Hr Wait"), "new": ("2027", "Seminar  →  ", "Immediate Sales")}


@lru_cache(None)
def compare_row(kind, width):
    col, bg = (RED, RED_BG) if kind == "old" else (GREEN, GREEN_BG)
    lab, a, b = ROW_TXT[kind]
    im = blank(width, 150)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, width - 1, 149], radius=20, fill=bg)
    d.rounded_rectangle([0, 0, 12, 149], radius=6, fill=col)
    lp = pill(lab, col, WHITE, size=28, pad=18, h_=52)
    im.alpha_composite(lp, (32, 50))
    f = row_font(kind, width)
    x = 32 + lp.width + 22
    d.text((x, 76), a, font=f, fill=INK, anchor="lm")
    x += text_size(a, f)[0] + f.getbbox(a)[0]
    d.text((x, 76), b, font=f, fill=col, anchor="lm")
    return im


@lru_cache(None)
def row_font(kind, width):
    lab, a, b = ROW_TXT[kind]
    lpw = pill(lab, RED, WHITE, size=28, pad=18, h_=52).width
    return fit_font(a + b, "xb", 46, width - (32 + lpw + 22) - 130)


def row_seg_x(kind):
    bw = int(CW - 96)
    lab, a, b = ROW_TXT[kind]
    lpw = pill(lab, RED, WHITE, size=28, pad=18, h_=52).width
    f = row_font(kind, bw)
    x = 32 + lpw + 22 + text_size(a, f)[0] + f.getbbox(a)[0]
    return x, x + text_size(b, f)[0]


def draw_card3(layer, t):
    t0 = T["card3"]
    rect, p = card_rect_for(t, 2, t0, T["dock3"])
    if rect is None:
        return
    # 3D board flip: squash vertically while opening
    fp = prog(t, t0, 0.5)
    flip = abs(math.cos(fp * math.pi)) if fp < 1 else 1.0
    if fp < 1:
        x0, y0, x1, y1 = rect
        cy = (y0 + y1) / 2
        hh = (y1 - y0) / 2 * max(0.04, flip)
        rect = (x0, cy - hh, x1, cy + hh)
    draw_card_frame(layer, rect, AMBER, fill=WHITE if fp >= 0.5 or fp == 0 else AMBER_BG)
    ca = clamp((p - 0.6) / 0.4) * (1.0 if fp >= 1 else 0.0)
    if ca <= 0:
        return
    x0, y0, x1, y1 = rect
    ty = card_title(layer, rect, "#3: Looser Ad Wording Rules", ca, color=NAVY)
    bw = int(CW - 96)
    bx = x0 + 48
    # TV graphic, shrinks up once badges arrive
    if t >= T["tv"]:
        pt = ease_back(prog(t, T["tv"], 0.4), 1.4)
        shrink = ease_in_out(prog(t, T["false3"] - 0.15, 0.35))
        tv = tv_icon_cached()
        s_ = lerp(1.0, 0.62, shrink) * pt
        cy = lerp(ty + 210, ty + 125, shrink)
        paste(layer, tv, x0 + (x1 - x0) / 2, cy, s_, ca)
        for key, word, dx, dy, col in (("best", "THE BEST!", -250, -95, HILITE), ("most", "THE MOST!", 250, -40, (255, 236, 160))):
            if t >= T[key]:
                b = tv_bubble_cached(word, col)
                bs = pop_scale(t, T[key], 0.3) * lerp(1.0, 0.72, shrink)
                paste(layer, b, x0 + (x1 - x0) / 2 + dx * lerp(1, 0.8, shrink), cy + dy * lerp(1, 0.7, shrink), bs, ca,
                      rot=(6 if key == "best" else -6))
    by = ty + 290
    if t >= T["false3"]:
        b1 = badge("x", "False Claims Still Illegal", bw)
        pb = ease_out(prog(t, T["false3"], 0.18))
        paste(layer, b1, bx + bw / 2, by, lerp(1.25, 1.0, pb), ca * pb)
    if t >= T["warn3"]:
        b2 = badge("warn", "No Upfront Proof Required", bw)
        pb = ease_out(prog(t, T["warn3"], 0.3))
        paste(layer, b2, bx + bw / 2 + 60 * (1 - pb), by + 116, 1, ca * pb)


@lru_cache(None)
def tv_icon_cached():
    return icon_tv(380, 250)


@lru_cache(None)
def tv_bubble_cached(word, col):
    return tv_bubble(word, col)


SUMMARY = [
    "No 48-Hr Appointment Wait",
    "Seminars Can Pitch Immediately",
    "“Best/Most” Allowed Without Pre-Proof",
]


@lru_cache(None)
def summary_row(i, width):
    im = blank(width, 118)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, width - 1, 117], radius=20, fill=WHITE, outline=LINE, width=3)
    c = [NAVY, NAVY, AMBER][i]
    d.ellipse([22, 24, 92, 94], fill=c)
    d.text((57, 59), str(i + 1), font=font("black", 40), fill=WHITE if i < 2 else NAVY, anchor="mm")
    f = fit_font(SUMMARY[i], "xb", 40, width - 140)
    d.text((116, 59), SUMMARY[i], font=f, fill=INK, anchor="lm")
    return im


def draw_summary(layer, t, yoff=0.0):
    if t < T["dock3"] + 0.15:
        return
    p = ease_out(prog(t, T["dock3"] + 0.15, 0.35))
    rect = lerp_rect((MX + 40, CARD[1] + 40, W - MX - 40, CARD[3] - 40), CARD, p)
    rect = (rect[0], rect[1] + yoff, rect[2], rect[3] + yoff)
    draw_card_frame(layer, rect, NAVY, alpha=p)
    if p < 0.5:
        return
    x0, y0, x1, y1 = rect
    lab = blank(CW, 70)
    ImageDraw.Draw(lab).text((48, 8), "THE TAKEAWAY", font=font("xb", 34), fill=MUTED)
    paste(layer, lab, (x0 + x1) / 2, y0 + 70, 1, p)
    bw = int(CW - 96)
    for i in range(3):
        ts = T["stack"] + i * 0.2
        if t < ts:
            continue
        pr = ease_out(prog(t, ts, 0.35))
        target = (x0 + 48, y0 + 120 + i * 136, x0 + 48 + bw, y0 + 120 + i * 136 + 118)
        tr = tab_rect(i)
        tr = (tr[0], tr[1] + yoff, tr[2], tr[3] + yoff)
        r = lerp_rect(tr, target, pr)
        row = summary_row(i, bw)
        sx = (r[2] - r[0]) / bw
        paste(layer, row, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, sx, pr)
    # gold footer
    if t >= T["footer"]:
        pf = ease_out(prog(t, T["footer"], 0.35))
        fy = y0 + 120 + 3 * 136 + 50
        fw = bw
        foot = blank(fw, 96)
        fd = ImageDraw.Draw(foot)
        fd.rounded_rectangle([0, 0, fw - 1, 95], radius=18, fill=(250, 240, 205), outline=GOLD, width=3)
        f = font("black", 46)
        txt = "Know the Facts Before You Sign"
        tw = text_size(txt, f)[0]
        if t >= T["swipe"]:
            ps = ease_in_out(prog(t, T["swipe"], 0.45))
            fd.rounded_rectangle([(fw - tw) / 2 - 14, 22, lerp((fw - tw) / 2 - 14, (fw + tw) / 2 + 14, ps), 78],
                                 radius=8, fill=HILITE)
        fd.text((fw / 2, 49), txt, font=f, fill=NAVY, anchor="mm")
        paste(layer, foot, (x0 + x1) / 2, fy + 40 * (1 - pf), 1, pf)


def draw_cta(layer, t):
    if t < T["cta"]:
        return
    p = ease_out(prog(t, T["cta"], 0.5))
    rect = (MX, 170, W - MX, 1010)
    oy = 700 * (1 - p)
    x0, y0, x1, y1 = rect[0], rect[1] + oy, rect[2], rect[3] + oy
    draw_card_frame(layer, (x0, y0, x1, y1), GOLD, fill=NAVY_LIFT if NAVY_THEME else NAVY)
    cx = W / 2
    # gold inner border
    bd = blank(x1 - x0 - 36, y1 - y0 - 36)
    ImageDraw.Draw(bd).rounded_rectangle([0, 0, bd.width - 1, bd.height - 1], radius=18, outline=(201, 162, 39, 150), width=3)
    paste(layer, bd, cx, (y0 + y1) / 2 + 6, 1, p)
    paste(layer, cta_logo_panel(), cx, y0 + 205, 1, p)
    since = blank(CW, 60)
    ImageDraw.Draw(since).text((CW / 2, 30), "SINCE 1994", font=font("xb", 36), fill=GOLD_LT, anchor="mm")
    paste(layer, since, cx, y0 + 385, 1, p)
    dv = blank(560, 6)
    ImageDraw.Draw(dv).rectangle([0, 0, 560, 6], fill=GOLD)
    paste(layer, dv, cx, y0 + 420, 1, p)
    # phone: full number shown with the card; digits light up gold as it's spoken
    num = "800-324-9986"
    n = 0
    if t >= T["phone"]:
        n = int(round(len(num) * prog(t, T["phone"], T["phone_end"] - T["phone"])))
    ph = blank(CW - 60, 170)
    pd = ImageDraw.Draw(ph)
    fnum = fit_font(num, "black", 104, ph.width - 110 - 50)
    full_w = text_size(num, fnum)[0]
    ix = (ph.width - full_w - 110) / 2
    ph.alpha_composite(icon_phone(92), (int(ix), 39))
    pd.text((ix + 110, 85), num, font=fnum, fill=WHITE, anchor="lm")
    if n:
        pd.text((ix + 110, 85), num[:n], font=fnum, fill=GOLD_LT, anchor="lm")
    pulse = 1.0
    if t >= T["phone"]:
        pulse += 0.05 * math.sin(math.pi * prog(t, T["phone"], T["phone_end"] - T["phone"] + 0.3))
    paste(layer, ph, cx, y0 + 540, pulse, p)
    # website + cursor click
    if t >= T["web"]:
        pw = ease_out(prog(t, T["web"], 0.3))
        site = "allenandassociates.agency"
        fs = font("xb", 50)
        sw = text_size(site, fs)[0]
        wb = blank(CW - 60, 110)
        wd = ImageDraw.Draw(wb)
        ix2 = (wb.width - sw - 84) / 2
        wb.alpha_composite(icon_globe(66), (int(ix2), 22))
        clicked = t >= T["webclick"]
        wd.text((ix2 + 84, 55), site, font=fs, fill=GOLD_LT if clicked else WHITE, anchor="lm")
        if clicked:
            up = ease_out(prog(t, T["webclick"], 0.25))
            wd.rectangle([ix2 + 84, 86, ix2 + 84 + sw * up, 92], fill=GOLD_LT)
        wy = y0 + 700
        paste(layer, wb, cx, wy + 30 * (1 - pw), 1, pw)
        # cursor glides in then clicks
        tgt = (cx + 170, wy + 30)
        pc = ease_in_out(prog(t, T["web"] + 0.1, T["webclick"] - T["web"] - 0.15))
        cpos = (lerp(cx + 420, tgt[0], pc), lerp(y0 + 900, tgt[1], pc))
        press = 1.0
        if clicked:
            k = prog(t, T["webclick"], 0.16)
            press = 1 - 0.18 * math.sin(k * math.pi)
            rp = prog(t, T["webclick"], 0.5)
            if rp < 1:
                ring = blank(140, 140)
                ImageDraw.Draw(ring).ellipse([4, 4, 136, 136], outline=GOLD_LT, width=6)
                paste(layer, ring, cpos[0] - 8, cpos[1] - 18, 0.3 + rp, 1 - rp)
        paste(layer, icon_cursor(64), cpos[0] + 14, cpos[1] + 14, press, pw)


def draw_hero(layer, t):
    """Hook: big '3' stat in the data stage."""
    if t < T["tab1"] or t > S(2) + 0.35:
        return
    pin = pop_scale(t, T["tab1"], 0.4)
    pout = 1 - ease_in_out(prog(t, S(2) - 0.05, 0.35))
    a = pout
    im = hero_img()
    paste(layer, im, W / 2, 640, pin * lerp(0.85, 1, pout), a)


@lru_cache(None)
def hero_img():
    im = blank(CW, 600)
    d = ImageDraw.Draw(im)
    fg, sub = ((245, 166, 35), WHITE) if NAVY_THEME else (NAVY, INK)
    d.text((CW / 2, 210), "3", font=font("black", 330), fill=fg, anchor="mm")
    d.text((CW / 2, 420), "Medicare sales rules", font=font("xb", 60), fill=sub, anchor="mm")
    d.text((CW / 2, 494), "change in 2027", font=font("xb", 60), fill=sub, anchor="mm")
    d.rectangle([CW / 2 - 90, 548, CW / 2 + 90, 556], fill=GOLD)
    return im


def draw_namecard(layer, t):
    if t < T["name"] or t > T["tk"] + 0.4:
        return
    ps = pop_scale(t, T["name"], 0.38)
    pout = 1 - ease_in_out(prog(t, T["tk"], 0.3))
    im = namecard_img()
    paste(layer, im, W / 2, 760, ps * lerp(0.6, 1, pout), pout)


@lru_cache(None)
def cta_logo_panel():
    lg = official_logo(720)
    w_, h_ = lg.width + 60, lg.height + 50
    im = blank(w_, h_)
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w_ - 1, h_ - 1], radius=22, fill=WHITE)
    im.alpha_composite(lg, (30, 25))
    return im


@lru_cache(None)
def namecard_img():
    w_, h_ = 940, 250
    im, pad = shadowed_card(w_, h_, fill=WHITE, radius=26)
    d = ImageDraw.Draw(im)
    d.text((pad + 40, pad + 82), "Arric Allen", font=font("black", 64), fill=NAVY, anchor="lm")
    d.rectangle([pad + 40, pad + 130, pad + 108, pad + 136], fill=GOLD)
    d.text((pad + 40, pad + 178), "Since 1994", font=font("sb", 38), fill=MUTED, anchor="lm")
    d.line([(pad + 448, pad + 36), (pad + 448, pad + h_ - 36)], fill=LINE, width=3)
    lg = official_logo(450)
    im.alpha_composite(lg, (pad + 470, pad + (h_ - lg.height) // 2))
    return im


def graphics(t):
    layer = blank(W, H)
    # stage exits upward for the CTA
    out = ease_in_out(prog(t, T["out"], 0.45))
    yoff = -1100 * out
    if out < 1:
        stage = blank(W, H)
        # header drops down
        if t >= T["header"]:
            ph = ease_back(prog(t, T["header"], 0.45), 1.3)
            hy = lerp(-150, 0, ph)
            hi = header_img()
            paste(stage, hi, W / 2, (HEADER[1] + HEADER[3]) / 2 + hy, 1, clamp(ph * 2))
        # tabs
        for i in range(3):
            ts = T[f"tab{i + 1}"]
            if t < ts:
                continue
            st = tab_state(i, t)
            img = tab_img(*st)
            sc = pop_scale(t, ts, 0.3)
            wob = 0
            if i == 2 and T["qping"] <= t < T["qping"] + 0.6:
                k = prog(t, T["qping"], 0.6)
                sc *= 1 + 0.12 * math.sin(k * math.pi)
                wob = 8 * math.sin(k * math.pi * 4) * (1 - k)
            for j, key in enumerate(["dock1", "dock2", "dock3"]):
                if i == j and T[key] <= t < T[key] + 0.45:
                    k = prog(t, T[key] + 0.15, 0.3)
                    sc *= 1 + 0.08 * math.sin(k * math.pi)
            r = tab_rect(i)
            paste(stage, img, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2, sc, 1, rot=wob)
        draw_hero(stage, t)
        draw_namecard(stage, t)
        draw_card1(stage, t)
        draw_card2(stage, t)
        draw_card3(stage, t)
        draw_summary(stage, t)
        if yoff:
            layer.alpha_composite(stage, (0, int(yoff)))
        else:
            layer = stage
    draw_cta(layer, t)
    return layer


# ---------------------------------------------------------------- speaker
FACE = (360, 260)      # anchor point in source frame (between eyes)
FACE_Y = 1300          # where that anchor sits on the 9:16 canvas
BASE_K = 1.05          # source px -> canvas px at "100%"


def speaker_pose(t):
    """(x_frac, scale) with slides between segments."""
    i = max(k for k in range(len(SEGMENTS)) if t >= STARTS[k])
    x, s, slide = SEGMENTS[i][4:7]
    if slide and i > 0:
        px, ps_ = SEGMENTS[i - 1][4:6]
        k = ease_in_out(prog(t, STARTS[i], slide / FPS))
        x, s = lerp(px, x, k), lerp(ps_, s, k)
    return x, s


def speaker_alpha(t):
    """Hidden behind the Rule #1 takeover card."""
    if T["tk"] <= t < S(3):
        return 1 - ease_in_out(prog(t, T["tk"], 0.2))
    if S(3) <= t < S(3) + 0.3:
        return ease_in_out(prog(t, S(3) + 0.05, 0.25))
    return 1.0


def key_frame(rgb):
    """Chroma key the AI green screen -> RGBA with despill."""
    f = rgb.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    mx = np.maximum(r, b)
    diff = g - mx
    alpha = 1.0 - np.clip((diff - 18) / (52 - 18), 0, 1)
    # despill: clamp green toward max(r,b), a touch softer on bright pixels
    g2 = np.where(g > mx, mx + (g - mx) * 0.08, g)
    out = np.empty(rgb.shape[:2] + (4,), np.uint8)
    out[..., 0] = r
    out[..., 1] = np.clip(g2, 0, 255)
    out[..., 2] = b
    a8 = (alpha * 255).astype(np.uint8)
    img = Image.fromarray(out)
    am = Image.fromarray(a8).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    img.putalpha(am)
    return img


def place_speaker(canvas, rgb, t):
    a = speaker_alpha(t)
    if a <= 0.005:
        return
    x_frac, s = speaker_pose(t)
    k = BASE_K * s
    img = key_frame(rgb)
    if a < 0.999:
        img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    # crop away everything below the canvas before scaling
    src_bottom = min(1280, int(FACE[1] + (H - FACE_Y) / k) + 2)
    img = img.crop((0, 0, 720, src_bottom))
    sw, sh = round(720 * k), round(src_bottom * k)
    img = img.resize((sw, sh), Image.BILINEAR)
    ox = round(x_frac * W - FACE[0] * k)
    oy = round(FACE_Y - FACE[1] * k)
    canvas.alpha_composite(img, (ox, oy)) if 0 <= ox and ox + sw <= W else _composite_clipped(canvas, img, ox, oy)


def _composite_clipped(canvas, img, ox, oy):
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(W, ox + img.width), min(H, oy + img.height)
    if x1 <= x0 or y1 <= y0:
        return
    canvas.alpha_composite(img.crop((x0 - ox, y0 - oy, x1 - ox, y1 - oy)), (x0, y0))


@lru_cache(None)
def background():
    if NAVY_THEME:
        # navy canvas, soft lighter-navy glow behind the speaker for head separation
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / 620) ** 2 + ((yy - 1330) / 560) ** 2)
        glow = np.clip(1 - r, 0, 1) ** 1.6
        vign = np.clip(1 - 0.18 * (yy / H) ** 2, 0, 1)
        base, lift = np.array(NAVY_BG, np.float32), np.array((44, 84, 138), np.float32)
        rgb = (base + (lift - base) * glow[..., None]) * vign[..., None]
        a = np.dstack([rgb.clip(0, 255).astype(np.uint8), np.full((H, W), 255, np.uint8)])
        return Image.fromarray(a, "RGBA")
    bg = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(bg)
    # faint stage floor gradient for the speaker area
    for y in range(1100, H):
        k = (y - 1100) / (H - 1100)
        c = tuple(int(BG[i] - 10 * k) for i in range(3))
        d.line([(0, y), (W, y)], fill=c + (255,))
    return bg


def compose(rgb, t):
    canvas = background().copy()
    place_speaker(canvas, rgb, t)
    canvas.alpha_composite(graphics(t), (0, 0))
    return canvas.convert("RGB")


# ---------------------------------------------------------------- io
def video_reader(start, end):
    inputs, chains = [], []
    for i, seg in enumerate(SEGMENTS):
        f, a, b = seg[1:4]
        stretch = seg_len(seg) / (b - a)
        inputs += ["-i", os.path.join(ROOT, f)]
        chains.append(f"[{i}:v]trim={a}:{b},setpts=(PTS-STARTPTS)*{stretch:.6f},fps={FPS},format=rgb24[v{i}]")
    fc = ";".join(chains) + ";" + "".join(f"[v{i}]" for i in range(len(SEGMENTS))) + \
        f"concat=n={len(SEGMENTS)}:v=1:a=0,tpad=stop_mode=clone:stop_duration={TAIL}," \
        f"trim=start_frame={round(start * FPS)}:end_frame={round(end * FPS)},setpts=PTS-STARTPTS[out]"
    cmd = ["ffmpeg", "-v", "error"] + inputs + ["-filter_complex", fc, "-map", "[out]", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = 720 * 1280 * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(1280, 720, 3)
    p.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--still", type=float, nargs="*")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    end = args.end if args.end is not None else DURATION

    if args.still:
        for ts in args.still:
            fr = next(video_reader(ts, ts + 0.1))
            compose(fr, ts).save(os.path.join(args.out, f"still_{ts:06.2f}.png"))
        return

    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                            "-pix_fmt", "yuv420p", args.out], stdin=subprocess.PIPE)
    i0 = round(args.start * FPS)
    for k, fr in enumerate(video_reader(args.start, end)):
        t = (i0 + k) / FPS
        enc.stdin.write(compose(fr, t).tobytes())
        if k % 60 == 0:
            print(f"{args.out}: t={t:.1f}", file=sys.stderr, flush=True)
    enc.stdin.close()
    enc.wait()


if __name__ == "__main__":
    main()
