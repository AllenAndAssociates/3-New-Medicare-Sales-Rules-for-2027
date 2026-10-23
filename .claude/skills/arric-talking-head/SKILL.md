---
name: arric-talking-head
description: Required workflow for any video that shows Arric Allen (Allen & Associates) talking on camera — AI avatar clips (Google Omni/Veo, HeyGen, green-screen generations), Shorts/Reels/TikToks, explainers, ads. Converts every on-camera line to Arric's real cloned voice with ElevenLabs speech-to-speech, and puts the official Allen & Associates logo on name cards and end cards. Use whenever editing, assembling, or rendering a talking-head video of Arric, even if the request doesn't mention voice or logo.
---

# Arric Allen talking-head videos

AI-generated clips of Arric speak in a generic model voice, not his. Every talking-head
video must replace that voice with Arric's ElevenLabs clone and use the official logo.

## 1. Voice: speech-to-speech on every on-camera line (mandatory)

- Voice: **"Arric Allen"** cloned voice, `voice_id = 3glBps71Sq7dUQi9biZa`
- Model: `eleven_english_sts_v2`, settings `stability 0.5, similarity_boost 0.85, style 0, speaker_boost on`
- Endpoint: `POST https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}` (the proxy injects the API key)

Steps:

1. Convert the **full source clip audio** for each clip *before* trimming, so cut points
   stay identical between picture and sound:
   ```
   python3 .claude/skills/arric-talking-head/scripts/sts_convert.py --out <edit>/audio/sts clip1.mp4 clip2.mp4 ...
   ```
   The script reports the timing offset per clip. Speech-to-speech keeps timing, so the offset
   should be 0–20 ms; anything over 40 ms is flagged — re-run that clip.
2. Transcribe the converted files (`/v1/speech-to-text`, `scribe_v1`) and compare with the
   original transcripts. Words must match; re-run any clip that dropped or changed words.
3. In the mix, use the converted tracks for all on-camera speech — never the clip's original
   audio. Apply the same trims, fades and level matching you would to the original.
4. Lines that don't exist in any clip (pickups, added transitions): generate them with
   text-to-speech using the **same voice_id**, and play them over a full-screen graphic or
   with Arric off-screen — never over his face with mouth not moving.
5. Do **not** create new voice clones (instant voice cloning); only use the existing clone.

## 2. Branding

- Official logo: `.claude/skills/arric-talking-head/assets/allen-associates-logo.png`
  (577×181, white background, green/blue mark, "INSURANCE AGENCY — MAKING MEDICARE EASY").
  - Use it on the intro name card and the final call-to-action card. Never redraw, recolor,
    or substitute a monogram.
  - It has a white background and dark tagline text: on dark cards, place it on a white
    rounded panel; don't put it straight on navy/dark backgrounds.
  - Don't upscale past ~1.3× (≈750 px wide) — it's a small source file.
- Name spelling: **Arric Allen** (speech-to-text writes "Eric" — always correct it in
  captions and on-screen text).
- Contact details: 📞 **800-324-9986** · 🌐 **allenandassociates.agency** · agency since **1994**.

## 3. Checks before delivering

- Transcribe the final mix: every scripted line present, name spelled correctly in graphics.
- Spot-check lip-sync at the start, middle and end of each clip.
- Name card and end card show the official logo.
- Say in the delivery note which lines (if any) are TTS rather than converted on-camera audio.
