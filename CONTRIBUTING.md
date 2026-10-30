# Contributing to DubLab

Thanks for helping! DubLab is maintained by a single maintainer, so small,
focused pull requests get reviewed fastest.

## Ground rules

- **Never commit secrets.** All keys come from environment variables
  (see `.env.example`). A real `.env` must never be committed.
- Keep the live-service behaviour in mind: DubLab runs in production, so
  pipeline changes should preserve the "never cut a sentence" sync rule.
- Respect the pinned dependencies in `requirements.txt` (`av==15.1.0`,
  `huggingface_hub<1`) — they exist because newer releases break
  faster-whisper.

## Good first contributions

- Burmese translation-prompt improvements (in `gemini.py`)
- New voices or TTS/STT backends
- UI/UX fixes in `templates/` and `static/` (mobile-first, iOS Safari included)
- Documentation and translation of the README

## Before you open a PR

1. Run `python3 -m py_compile app.py dub.py gemini.py gemini_tts.py edge_probe.py`
2. If you touched the pipeline, test one real dub end to end and say so in the PR.
