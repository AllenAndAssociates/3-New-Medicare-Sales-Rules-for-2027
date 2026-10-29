"""Audio mix: trimmed voice + music bed (hard stop on Rule #3, swell on CTA) + frame-synced SFX."""
import os
import subprocess
import sys

import numpy as np

import render as R

SR = 48000
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
T = R.T


def load(path, start=None, end=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start), "-to", str(end)]
    cmd += ["-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32).copy()


def db(x):
    return 10 ** (x / 20)


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


n_total = int(round(R.DURATION * SR))

# ---- voice: same trims as the picture, 10 ms edge fades
voice = np.zeros(n_total, np.float32)
for i, sg in enumerate(R.SEGMENTS):
    f, a, b, opts = sg[1], sg[2], sg[3], sg[7]
    if opts.get("mute"):
        continue
    # Arric's voice: ElevenLabs speech-to-speech conversion of the clip audio
    # (timing-preserving, so lip-sync holds). See .claude/skills/arric-talking-head.
    sts = os.path.join(ASSETS, "sts", os.path.splitext(f)[0] + ".mp3")
    if not os.path.exists(sts):
        sys.exit(f"missing speech-to-speech audio for {f}; run .claude/skills/arric-talking-head/scripts/sts_convert.py first")
    seg = load(sts, a, b)
    fl = int(0.01 * SR)
    seg[:fl] *= np.linspace(0, 1, fl)
    seg[-fl:] *= np.linspace(1, 0, fl)
    if "fade" in opts:
        f0, f1 = (int((x - a) * SR) for x in opts["fade"])
        seg[f0:f1] *= np.cos(np.linspace(0, np.pi / 2, f1 - f0)) ** 2
        seg[f1:] = 0
    o = int(round(R.STARTS[i] * SR))
    seg = seg[: n_total - o]
    voice[o:o + len(seg)] += seg
speech = voice[np.abs(voice) > 0.01]
voice *= db(-17 - rms_db(speech))   # voice ~ -17 dBFS RMS while talking

# ---- music: offset so its resolving chord lands right after the website click
music_src = load(os.path.join(ASSETS, "music.mp3"))
MUSIC_OFFSET = 0.2   # music time = video time + offset (before the Rule #3 hard stop)
CHORD_AT = 67.0      # resolving final chord in the music file
# The bed is muted during the hard stop, so re-sync there: after the drop-back-in
# the music is offset so its final chord lands just after the website click.
back_i = int(round(T["music_back"] * SR))
post_off = CHORD_AT - (T["webclick"] + 0.1)
pre = music_src[int(MUSIC_OFFSET * SR):][:back_i]
post = music_src[int((T["music_back"] + post_off) * SR):][: n_total - back_i]
music = np.concatenate([np.pad(pre, (0, back_i - len(pre))), post])
music = np.pad(music, (0, n_total - len(music)))[:n_total]
music *= db(-34 - rms_db(music[: int(60 * SR)]))   # bed ~17 dB under the voice

t = np.arange(n_total) / SR
gain = np.ones(n_total, np.float32)
# hard stop on "Number three is interesting", back in on "flexibility"
stop0, back = T["dock2"], T["music_back"]
gain[(t >= stop0 + 0.015) & (t < back)] = 0
k = (t >= stop0) & (t < stop0 + 0.015)
gain[k] = 1 - (t[k] - stop0) / 0.015
k = (t >= back) & (t < back + 0.25)
gain[k] = (t[k] - back) / 0.25
# duck a further 4 dB while Arric is talking, easing back up in the pauses
win = int(0.05 * SR)
env = np.sqrt(np.convolve(voice ** 2, np.ones(win) / win, mode="same"))
talk = (env > db(-40)).astype(np.float32)
sm = int(0.25 * SR)
duck = np.convolve(talk, np.ones(sm) / sm, mode="same")
gain *= db(-4 * duck).astype(np.float32)
# warm swell into the CTA (+3 dB)
k = t >= R.S(10)
gain[k] *= db(3 * np.clip((t[k] - R.S(10)) / 1.5, 0, 1))
# gentle tail fade
k = t >= R.DURATION - 0.6
gain[k] *= np.clip((R.DURATION - t[k]) / 0.6, 0, 1)
music *= gain

# ---- SFX
sfx = np.zeros(n_total, np.float32)
_cache = {}


def hit(name, at, level=-10.0):
    if name not in _cache:
        x = load(os.path.join(ASSETS, f"{name}.mp3"))
        # trim leading silence so the transient lands on the frame
        nz = np.nonzero(np.abs(x) > 0.02)[0]
        x = x[nz[0]:] if len(nz) else x
        x = x / (np.max(np.abs(x)) + 1e-9)
        _cache[name] = x
    x = _cache[name] * db(level)
    o = int(round(at * SR))
    x = x[: max(0, n_total - o)]
    sfx[o:o + len(x)] += x


S = R.S
# Scene 1
hit("whoosh", T["header"], -18)
for k_ in ("tab1", "tab2", "tab3"):
    hit("tick", T[k_], -11)
hit("qping", T["qping"], -12)
# Scene 2
hit("softpop", T["name"], -14)
# Scene 3
hit("whoosh", S(3), -12)
hit("pop", T["card1"] + 0.05, -11)
hit("stopwatch", T["watch"], -15)
# Scene 4
hit("softpop", T["pill_ma"], -13)
hit("softpop", T["pill_pd"], -13)
hit("stamp", T["strike1"], -9)
hit("chime", T["chime1"], -12)
# Scene 5
hit("snap", T["dock1"] + 0.05, -11)
hit("pop", T["card2"] + 0.05, -14)
hit("paper", T["flow2"], -13)
# Scene 6
hit("buzzer", T["buzz2"], -15)
hit("whooshclick", T["click2"] - 0.12, -11)
# Scene 7
hit("flip", S(7), -9)
hit("bubble", T["best"], -11)
hit("bubble", T["most"], -11)
# Scene 8
hit("thud", T["false3"], -9)
hit("warnchime", T["warn3"], -13)
# Scene 9
hit("snap", T["dock3"] + 0.05, -13)
hit("shuffle", T["stack"], -11)
hit("highlight", T["swipe"], -19)
# Scene 10
hit("keys", T["phone"], -20)
hit("click", T["webclick"], -9)

mix = voice + music + sfx
out_wav = sys.argv[1]
pcm = np.stack([mix, mix], 1).astype(np.float32)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR), out_wav], input=pcm.tobytes(), check=True)
print("wrote", out_wav, R.DURATION)
