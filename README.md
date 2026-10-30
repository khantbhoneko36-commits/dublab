# DubLab — English ↔ Burmese Video Dubbing

**Upload a short video, get it back dubbed in the other language.**

DubLab is a self-hosted web app that dubs short videos between **English and
Burmese (Myanmar)** — a low-resource language pair with almost no open-source
dubbing tooling. It transcribes the speech, translates it, synthesizes a new
voice track in the target language, syncs it to the picture, and returns a
finished MP4.

🌐 **Live demo:** https://dublab.kbko.qzz.io
📄 **License:** MIT

---

## Why this exists

Burmese is spoken by 50M+ people, yet creators who want to dub content
between English and Burmese have almost no free, open tooling: commercial
dubbing services rarely support Burmese voices, and generic pipelines break
on Burmese text segmentation and speech timing. DubLab is built specifically
for this pair and runs in production for Myanmar content creators.

## Features

- 🎬 **Video dubbing** — upload a video (≤ 5 min, ≤ 250 MB), download the dubbed MP4
- 🗣️ **Burmese + English voices** — male and female voices both directions
  (`my-MM-ThihaNeural`, `my-MM-NilarNeural`, `en-US-AndrewNeural`, `en-US-AvaNeural`)
- 🎙️ **Local transcription** — [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on your own machine, no audio leaves your server for STT
- 🌏 **Translation** — Gemini API (free tier works), tuned prompts for subtitle-style lines
- ⏱️ **Sync engine that never cuts a sentence** — speech is time-fitted up to a
  capped speed-up (1.65×); overflow cascades into the next slot instead of
  truncating, so sentence tails are never lost
- 🔁 **TTS with fallbacks + key rotation** — Edge-TTS primary, Gemini TTS
  fallback with multi-key rotation and rate-limit cooldowns, gTTS last resort
- 💧 **Credit watermark** — small lower-right watermark (configurable text)
- 🛡️ **Abuse protection built in** — job queue cap, per-IP upload rate limit,
  24 h result retention, optional admin page for user reviews
- 📝 **SRT translator tab** — the UI ships with a tab that embeds a companion
  SRT translation service at `/srt/` (optional; the dubbing app works without it)

## How it works

```
upload ──► extract audio (ffmpeg) ──► transcribe (faster-whisper)
       ──► translate lines (Gemini) ──► synthesize voices (Edge-TTS / Gemini TTS)
       ──► time-fit + cascade placement ──► mux + watermark (ffmpeg) ──► MP4
```

| File | Role |
|---|---|
| `app.py` | Flask web app: upload, job queue, status polling, download, reviews/admin |
| `dub.py` | Dubbing pipeline: audio extract, transcription, TTS orchestration, sync engine, mux |
| `gemini.py` | Translation via Gemini API |
| `gemini_tts.py` | Gemini TTS with key rotation, cooldown and invalid-key handling |
| `edge_probe.py` | Tiny helper to probe Edge-TTS endpoint health |

## Quick start

Requirements: Python 3.11+, `ffmpeg`, and a free
[Gemini API key](https://aistudio.google.com/apikey).

```bash
git clone https://github.com/khantbhoneko36-commits/dublab.git
cd dublab
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # put your GEMINI_API_KEY in .env
set -a; source .env; set +a
waitress-serve --listen=127.0.0.1:8092 --threads=8 app:app
```

Open http://127.0.0.1:8092, drop in a short video, pick a direction and a
voice, and download the dubbed result.

> ⚠️ Dependency pins matter: `requirements.txt` pins `av==15.1.0` and
> `huggingface_hub<1` — newer versions break faster-whisper 1.2.x.

### Docker

```bash
docker build -t dublab .
docker run -d --name dublab -p 127.0.0.1:8092:8092 --env-file .env dublab
```

### Production (systemd)

See `dublab.service.example` — run behind nginx/Caddy as a reverse proxy with
HTTPS, exactly like the live deployment.

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Translation (and TTS fallback if no TTS keys set) |
| `GEMINI_TTS_API_KEYS` | — | Comma-separated keys for Gemini TTS rotation |
| `DUBLAB_ADMIN_KEY` | — | Password for the `/admin` reviews page |
| `DUBLAB_WATERMARK` | — | Watermark text (default: `made with DubLab`) |

## မြန်မာဘာသာ အကျဉ်းချုပ်

DubLab ဆိုတာ ဗီဒီယိုအတိုတွေကို **အင်္ဂလိပ် ↔ မြန်မာ** အပြန်အလှန်
အသံသွင်း (dub) လုပ်ပေးတဲ့ open-source web app တစ်ခုပါ။ ဗီဒီယိုတင်လိုက်ရင်
စကားပြောကို စာသားအဖြစ်ပြောင်း၊ ဘာသာပြန်၊ မြန်မာအသံ (ကျား/မ) နဲ့
အသံအသစ်ဖော်ပြီး၊ စာကြောင်းမပြတ်အောင် အချိန်ကိုက် ညှိပေးကာ
dub လုပ်ပြီးသား MP4 ပြန်ချပေးပါတယ်။ မြန်မာဘာသာအတွက် ဒီလို tooling
အရမ်းရှားတာမို့ Myanmar creator တွေ အခမဲ့ self-host လုပ်သုံးနိုင်အောင်
ထုတ်ပေးထားတာ ဖြစ်ပါတယ်။ Live သုံးကြည့်ချင်ရင်
https://dublab.kbko.qzz.io မှာ စမ်းနိုင်ပါတယ်။

## Contributing

Issues and pull requests are welcome — especially Burmese language fixes
(translation prompts, segmentation, voice timing) and new TTS/STT backends.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Maintainer

Built and maintained by **Khant Bhone Ko** ([@khantbhoneko36-commits](https://github.com/khantbhoneko36-commits)) —
sole maintainer: releases, issue triage, and the production deployment.
More projects: https://pro.kxant.org
