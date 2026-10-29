# 9:16 edit — 3 New Medicare Sales Rules for 2027

Output: `../Medicare_Sales_Rules_2027_9x16.mp4` — navy canvas (default; `THEME=light` renders the off-white variant), 1080×1920, 30 fps, -14 LUFS

- Source: `../Avatar Video_1080p.mp4` (single take). `render.py` — keys the green-screen footage, places the speaker in the bottom 45% stage
  (X 50/38/62%, scale punch-ins), and draws the USAFacts-style top 55% data stage
  (navy header, horizontal docked tabs 1/2/3, 90%-width expanding cards, CTA card).
  All graphic beats are synced to word timestamps from the clip transcripts.
- `mix.py` — voice + pizzicato/marimba bed (~19 dB under voice, ducked while he talks, hard stop on
  "Number three is interesting", back in on "flexibility", +3 dB swell on the CTA,
  resolving chord after the website click) + frame-synced SFX in `audio/`.

- Voice: all on-camera lines use Arric's ElevenLabs clone via speech-to-speech
  (`audio/sts/`), per the `arric-talking-head` skill in `.claude/skills/`.

Rebuild:

```
python3 ../.claude/skills/arric-talking-head/scripts/sts_convert.py --out audio/sts ../*720p*.mp4 ../Man_speaking_about_Medicare_rules_20261023175043.mp4
python3 render.py --out video.mp4          # or split with --start/--end and concat
python3 mix.py mix.wav
ffmpeg -i video.mp4 -i mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest out.mp4
```

The name card and end card use the official logo (`assets/allen-associates-logo.png`).

`audio/vo_first.wav` ("First: the 48-hour waiting rule is gone") is not in any source
clip; it was generated with the "Arric Allen" ElevenLabs voice and plays over a
full-screen Rule #1 card with the speaker hidden, so there is no lip-sync mismatch.
Replace it with a real Omni take if you regenerate that line.
