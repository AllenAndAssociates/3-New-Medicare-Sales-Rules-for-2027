"""Convert talking-head clip audio to Arric Allen's cloned voice (ElevenLabs speech-to-speech).

Usage: python3 sts_convert.py --out DIR clip1.mp4 [clip2.mp4 ...]

Writes DIR/<clip name>.mp3 for each clip, then checks that each converted track is
still time-aligned with the original (speech-to-speech keeps timing, so lip-sync
holds). Exits non-zero if a request fails or a track drifts by more than 40 ms.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

VOICE_ID = "3glBps71Sq7dUQi9biZa"   # "Arric Allen" cloned voice in the ElevenLabs account
MODEL = "eleven_english_sts_v2"
SETTINGS = {"stability": 0.5, "similarity_boost": 0.85, "style": 0, "use_speaker_boost": True}


def envelope(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    n = len(x) // 160                      # 10 ms frames
    e = np.log10(np.sqrt(np.mean(x[: n * 160].reshape(n, 160) ** 2, 1)) + 1e-5)
    return e - e.mean()


def lag_ms(a_path, b_path):
    a, b = envelope(a_path), envelope(b_path)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    best = max(range(-30, 31), key=lambda l: float(np.sum(a[max(0, -l):n - max(0, l)] * b[max(0, l):n - max(0, -l)])))
    return best * 10


def convert(clip, out_dir):
    dst = os.path.join(out_dir, os.path.splitext(os.path.basename(clip))[0] + ".mp3")
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "in.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-vn", "-ac", "1", "-ar", "44100", wav], check=True)
        code = subprocess.run(
            ["curl", "-sS", "-X", "POST",
             f"https://api.elevenlabs.io/v1/speech-to-speech/{VOICE_ID}?output_format=mp3_44100_192",
             "-F", f"model_id={MODEL}", "-F", f"voice_settings={json.dumps(SETTINGS)}",
             "-F", "remove_background_noise=false", "-F", f"audio=@{wav}",
             "-o", dst, "-w", "%{http_code}"], capture_output=True, text=True, check=True).stdout
        if code != "200":
            sys.exit(f"{clip}: HTTP {code}: {open(dst, errors='replace').read()[:300]}")
        lag = lag_ms(wav, dst)
    status = "ok" if abs(lag) <= 40 else "DRIFT"
    print(f"{status} lag={lag:+d}ms {dst}")
    return abs(lag) <= 40


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("clips", nargs="+")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    results = [convert(c, args.out) for c in args.clips]
    sys.exit(0 if all(results) else 1)
