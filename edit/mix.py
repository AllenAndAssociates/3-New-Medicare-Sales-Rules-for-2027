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
for i, (f, a, b) in enumerate(R.SEGMENTS):
    seg = load(os.path.join(R.ROOT, f), a, b)
    fl = int(0.01 * SR)
    seg[:fl] *= np.linspace(0, 1, fl)
    seg[-fl:] *= np.linspace(1, 0, fl)
    o = int(round(R.STARTS[i] * SR))
    seg = seg[: n_total - o]
    voice[o:o + len(seg)] += seg
speech = voice[np.abs(voice) > 0.01]
voice *= db(-17 - rms_db(speech))   # voice ~ -17 dBFS RMS while talking

# ---- music: offset so its resolving chord lands right after the website click
music_src = load(os.path.join(ASSETS, "music.mp3"))
MUSIC_OFFSET = 0.2  # music time = video time + offset
music = music_src[int(MUSIC_OFFSET * SR):][:n_total]
music = np.pad(music, (0, n_total - len(music)))
music *= db(-28 - rms_db(music[: int(60 * SR)]))   # bed ~11 dB under the voice

t = np.arange(n_total) / SR
gain = np.ones(n_total, np.float32)
# hard stop on "Number three is interesting", back in on "flexibility"
stop0, back = T["dock2"], T["music_back"]
gain[(t >= stop0 + 0.015) & (t < back)] = 0
k = (t >= stop0) & (t < stop0 + 0.015)
gain[k] = 1 - (t[k] - stop0) / 0.015
k = (t >= back) & (t < back + 0.25)
gain[k] = (t[k] - back) / 0.25
# warm swell into the CTA (+4 dB, i.e. -26 -> -22)
k = t >= R.S(10)
gain[k] *= db(4 * np.clip((t[k] - R.S(10)) / 1.5, 0, 1))
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
hit("highlight", T["swipe"], -11)
# Scene 10
hit("whoosh", T["cta"], -14)
hit("keys", T["phone"], -16)
hit("click", T["webclick"], -9)

mix = voice + music + sfx
out_wav = sys.argv[1]
pcm = np.stack([mix, mix], 1).astype(np.float32)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR), out_wav], input=pcm.tobytes(), check=True)
print("wrote", out_wav, R.DURATION)
