# 9:16 edit — 3 New Medicare Sales Rules for 2027

Output: `../Medicare_Sales_Rules_2027_9x16.mp4` (1080×1920, 30 fps, -14 LUFS)

- `render.py` — keys the green-screen clips, places the speaker in the bottom 45% stage
  (X 50/38/62%, scale punch-ins), and draws the USAFacts-style top 55% data stage
  (navy header, horizontal docked tabs 1/2/3, 90%-width expanding cards, CTA card).
  All graphic beats are synced to word timestamps from the clip transcripts.
- `mix.py` — voice + pizzicato/marimba bed (~11 dB under voice, hard stop on
  "Number three is interesting", back in on "flexibility", +4 dB swell on the CTA,
  resolving chord after the website click) + frame-synced SFX in `audio/`.

Rebuild:

```
python3 render.py --out video.mp4          # or split with --start/--end and concat
python3 mix.py mix.wav
ffmpeg -i video.mp4 -i mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest out.mp4
```

The A&A badge is a placeholder monogram — swap `logo_badge()` for the real logo file.
