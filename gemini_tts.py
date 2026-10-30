"""Gemini native TTS for DubLab (primary voice engine since 2026-10-11).

Free tier, no credit card. Burmese (my) is officially supported.
30 prebuilt voices, language-independent -> pick male/female per job.
Output: 24kHz 16-bit mono PCM, wrapped as WAV here.

Key rotation: GEMINI_TTS_API_KEYS (comma-separated). A key that hits
429/5xx cools down for COOLDOWN seconds; the next key is tried.
Only stdlib is used (urllib) - no new dependencies.
"""
import base64
import io
import json
import threading
import time
import urllib.error
import urllib.request
import wave

MODEL = "gemini-3.1-flash-tts-preview"
COOLDOWN = 60          # seconds a rate-limited key rests
TIMEOUT = 120          # per-request timeout

_keys = []
_cooling_until = {}
_invalid = set()
_lock = threading.Lock()


class QuotaExhausted(RuntimeError):
    """All TTS keys are rate-limited right now."""


class _HttpError(Exception):
    def __init__(self, code, body):
        super().__init__(f"HTTP {code}: {body}")
        self.code = code


def configure(keys):
    """keys: iterable of API key strings."""
    global _keys
    with _lock:
        _keys = [k.strip() for k in keys if k and k.strip()]
        _cooling_until.clear()
        _invalid.clear()


def key_count():
    with _lock:
        return len([k for k in _keys if k not in _invalid])


def _pick_key():
    now = time.time()
    with _lock:
        for k in _keys:
            if k not in _invalid and _cooling_until.get(k, 0) <= now:
                # round-robin: move to the back
                _keys.remove(k)
                _keys.append(k)
                return k
    return None


def _cool(key):
    with _lock:
        _cooling_until[key] = time.time() + COOLDOWN


def _drop(key):
    """Permanently drop a key (bad credentials) for this process lifetime."""
    with _lock:
        _invalid.add(key)


def _request(text, voice, lang, api_key):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
           f":generateContent?key={api_key}")
    # Language instruction as a prompt prefix: the model speaks only the
    # Burmese/English line that follows (verified: prefix is not spoken).
    # NOTE: systemInstruction caused HTTP 500s on this preview model (2026-10-11).
    instruction = ("Speak in Burmese: " if lang == "my" else "Speak in English: ")
    body = {
        "contents": [{"parts": [{"text": instruction + text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise _HttpError(e.code, e.read().decode(errors="replace")[:200])
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for p in parts:
        b64 = (p.get("inlineData") or {}).get("data")
        if b64:
            return base64.b64decode(b64)
    raise RuntimeError("gemini tts: no audio in response: "
                       + json.dumps(data)[:200])


def _earliest_cooldown():
    with _lock:
        if not _cooling_until:
            return 0
        return min(_cooling_until.values())


def synthesize(text, voice, lang, out_path, max_rounds=3):
    """Synthesize one utterance.

    text: the line to speak. voice: Gemini prebuilt voice name
    (e.g. "Aoede", "Charon"). lang: "my" or "en". out_path: WAV file written.
    When every key is cooling down, waits for the cooldown to expire and
    retries (up to max_rounds). Raises QuotaExhausted only when truly stuck.
    """
    if not key_count():
        raise RuntimeError("no gemini tts keys configured")
    last_err = None
    for rnd in range(max_rounds):
        rate_limited = 0
        tried = 0
        total = key_count()
        for _ in range(total):
            key = _pick_key()
            if key is None:
                break
            tried += 1
            try:
                pcm = _request(text, voice, lang, key)
                buf = io.BytesIO()
                with wave.open(buf, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(24000)
                    w.writeframes(pcm)
                with open(out_path, "wb") as f:
                    f.write(buf.getvalue())
                return
            except _HttpError as e:
                last_err = e
                if e.code in (401, 403):
                    _drop(key)  # bad key - never try it again this run
                    continue
                if e.code in (429, 500, 502, 503):
                    rate_limited += 1
                    _cool(key)
                    continue
                raise
            except Exception as e:  # network blip etc - cool the key, try next
                last_err = e
                _cool(key)
                continue
        if rate_limited == tried and rnd < max_rounds - 1:
            # every key cooling (or none usable) - wait it out and retry
            wait = max(0, _earliest_cooldown() - time.time()) + 2
            time.sleep(min(wait, COOLDOWN + 5))
            continue
        break
    if key_count() == 0:
        raise QuotaExhausted(
            "Gemini TTS key အားလုံး အသုံးမဝင်ဘူး (key မှားနေတာ ဖြစ်နိုင်တယ်). "
            f"(last: {last_err})")
    raise QuotaExhausted(
        "Gemini TTS quota ကုန်နေတယ် — key အားလုံး ခဏနားနေတယ်. "
        f"(last: {last_err})")
