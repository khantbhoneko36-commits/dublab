"""DubLab — short-video dubbing website. Upload video -> dubbed video."""
import json
import os
import re
import shutil
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from dub import (build_dub_track, configure_tts, extract_audio, has_audio_stream,
                 has_video_stream, merge_segments, mux, probe_duration, transcribe)
from gemini import translate_lines

# Gemini TTS key rotation (same 5-key pool style as the SRT site).
# GEMINI_TTS_API_KEYS is comma-separated; falls back to the single GEMINI_API_KEY.
_tts_keys = [k.strip() for k in
             os.environ.get("GEMINI_TTS_API_KEYS",
                            os.environ.get("GEMINI_API_KEY", "")).split(",")
             if k.strip()]
configure_tts(_tts_keys)

BASE = Path(__file__).parent
JOBS = BASE / "jobs"
JOBS.mkdir(exist_ok=True)

MAX_DURATION = 300      # seconds
MAX_MB = 250
TTL = 24 * 3600        # keep results a day

# ---- abuse protection (public site) ----
MAX_QUEUE = 15          # max jobs waiting in line
UPLOADS_PER_HOUR = 10   # per client IP
_ip_hits = {}
_ip_lock = threading.Lock()

# ---- maintenance mode (TTS outage) ----
# Turn True to pause new dub jobs; the home page shows the maintenance image.
MAINTENANCE = False
MAINTENANCE_MSG = ("🔧 DubLab ခေတ္တ ရပ်ထားပါတယ် — Microsoft အသံထုတ် service "
                   "ပျက်နေလို့ ပြင်ဆင်နေပါတယ်။ ပြန်ကောင်းတာနဲ့ အကြောင်းကြားမယ် 🙏")

# ---- reviews ----
REVIEWS = BASE / "reviews.jsonl"
ADMIN_KEY = os.environ.get("DUBLAB_ADMIN_KEY", "")

VOICES = {
    "en2mm": {"female": "my-MM-NilarNeural", "male": "my-MM-ThihaNeural"},
    "mm2en": {"female": "en-US-AvaNeural", "male": "en-US-AndrewNeural"},
}
STAGE_LABEL = {
    "queue": "တန်းစီနေတယ်",
    "audio": "အသံထုတ်ယူနေတယ်",
    "transcribe": "စကားပြောမှတ်နေတယ်",
    "translate": "ဘာသာပြန်နေတယ်",
    "voice": "အသံဖော်နေတယ်",
    "mux": "ဗီဒီယိုပေါင်းနေတယ်",
    "done": "ပြီးပြီ",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

jobs = {}
queue = []
lock = threading.Condition()


def jlog(job, msg):
    """Append a timestamped line to the job's live log file."""
    line = f"[{time.strftime('%H:%M:%S')}] {msg}\n"
    try:
        with open(job["dir"] / "job.log", "a") as fh:
            fh.write(line)
    except OSError:
        pass


def clean_err(e):
    """User-facing error text — never leak server paths."""
    s = str(e)
    if ("speech.platform.bing.com" in s or "WSServerHandshakeError" in s
            or "Invalid response status" in s):
        return ("အသံထုတ်တဲ့ service (Microsoft) ခေတ္တ ပျက်နေတယ် — "
                "ပြန်ကောင်းအောင် ပြင်နေပါတယ်။ ခဏနေမှ ပြန်စမ်းပါ 🙏")
    return s.replace(str(BASE), "[app]").replace(str(JOBS), "[jobs]")[:300]


def _client_ip():
    # nginx sets X-Forwarded-For; first entry is the real client
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() or request.remote_addr or "?")


def _rate_ok(ip):
    now = time.time()
    with _ip_lock:
        dq = _ip_hits.get(ip)
        if dq is None:
            dq = _ip_hits[ip] = deque()
        while dq and now - dq[0] > 3600:
            dq.popleft()
        if len(dq) >= UPLOADS_PER_HOUR:
            return False
        dq.append(now)
        if len(_ip_hits) > 5000:  # don't let the table grow forever
            _ip_hits.clear()
        return True


# drop leftover job dirs from before a restart
for _old in JOBS.iterdir():
    try:
        if _old.is_dir() and time.time() - _old.stat().st_mtime > TTL:
            shutil.rmtree(_old, ignore_errors=True)
    except OSError:
        pass


def sweep_old():
    now = time.time()
    for jid, job in list(jobs.items()):
        if now - job["created"] > TTL and job["status"] in ("done", "failed"):
            shutil.rmtree(job["dir"], ignore_errors=True)
            jobs.pop(jid, None)


def process_job(jid):
    job = jobs[jid]
    d = job["dir"]
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("server config missing (GEMINI_API_KEY)")
        direction, voice_name = job["direction"], VOICES[job["direction"]][job["voice"]]
        lang_hint = "en" if direction == "en2mm" else "my"
        src = d / ("input" + job["ext"])
        jlog(job, f"job {jid} started · {direction} · {job['voice']} voice")
        total = probe_duration(src)
        jlog(job, f"video duration: {total:.1f}s")
        if not has_video_stream(src):
            raise ValueError("ဗီဒီယိုဖိုင် မဟုတ်ဘူး")
        if not has_audio_stream(src):
            raise ValueError("ဒီဗီဒီယိုမှာ အသံမပါဘူး — အသံပါတဲ့ ဗီဒီယိုမှ dub လို့ရမယ်")

        job.update(stage="audio", pct=4)
        jlog(job, "extracting audio…")
        wav = d / "audio.wav"
        extract_audio(src, wav)

        job.update(stage="transcribe", pct=8)
        jlog(job, "transcribing with whisper…")
        segs = transcribe(wav, lang_hint)
        if not segs:
            raise ValueError("အသံထဲမှာ စကားပြောသံ မတွေ့ဘူး")
        utter = merge_segments(segs)
        jlog(job, f"transcribed {len(segs)} segments → {len(utter)} utterances")

        job.update(stage="translate", pct=45)
        jlog(job, "translating with gemini…")
        texts = translate_lines([u["text"] for u in utter], direction, api_key)
        for u, t in zip(utter, texts):
            u["text"] = t or u["text"]
        jlog(job, f"translated {len(texts)} lines")

        job.update(stage="voice", pct=58)
        jlog(job, f"synthesizing {len(utter)} utterances ({voice_name})…")
        def tts_prog(i, n):
            job.update(pct=58 + int(32 * i / max(n, 1)))
            if i % 5 == 0 or i == n:
                jlog(job, f"tts {i}/{n}")
        dub_wav = build_dub_track(utter, voice_name, d, total, tts_prog)

        job.update(stage="mux", pct=93)
        jlog(job, "muxing dubbed audio with video…")
        mux(src, dub_wav, d / "dubbed.mp4")

        job.update(status="done", stage="done", pct=100)
        jlog(job, "done ✅")
    except Exception as e:  # noqa: BLE001 - surfaced to UI
        err = clean_err(e)
        jlog(job, f"FAILED: {type(e).__name__}: {err}")
        job.update(status="failed", error=err)


def worker():
    while True:
        with lock:
            while not queue:
                lock.wait()
            jid = queue.pop(0)
        jobs[jid]["status"] = "processing"
        process_job(jid)
        sweep_old()


threading.Thread(target=worker, daemon=True).start()


@app.get("/")
def index():
    return render_template("index.html",
                           maintenance=MAINTENANCE,
                           maintenance_msg=MAINTENANCE_MSG)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/jobs")
def create_job():
    if MAINTENANCE:
        return jsonify(error=MAINTENANCE_MSG), 503
    if len(queue) >= MAX_QUEUE:
        return jsonify(error="လူများနေတယ် — ခဏနေမှ ပြန်စမ်းပါ"), 429
    if not _rate_ok(_client_ip()):
        return jsonify(error="ခဏခဏ တင်နေတယ် — ၁ နာရီနေမှ ပြန်စမ်းပါ"), 429
    f = request.files.get("video")
    direction = request.form.get("direction", "en2mm")
    voice = request.form.get("voice", "female")
    if not f or not f.filename:
        return jsonify(error="ဗီဒီယိုဖိုင် ရွေးပေးပါ"), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".mp4", ".mov", ".mkv", ".webm", ".m4v"):
        return jsonify(error="MP4/MOV ဖိုင်ပဲ လက်ခံတယ်"), 400
    if direction not in VOICES or voice not in ("female", "male"):
        return jsonify(error="ရွေးချယ်မှု မှားနေတယ်"), 400
    jid = uuid.uuid4().hex[:12]
    d = JOBS / jid
    try:
        d.mkdir(parents=True)
        src = d / ("input" + ext)
        f.save(src)
        # fail fast on bad files — nothing reaches the worker queue
        if probe_duration(src) > MAX_DURATION:
            raise ValueError("၅ မိနစ်ထက် ရှည်တဲ့ ဗီဒီယို လက်မခံဘူး")
        if not has_video_stream(src):
            raise ValueError("ဗီဒီယိုဖိုင် မဟုတ်ဘူး")
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(d, ignore_errors=True)
        if isinstance(e, ValueError):
            return jsonify(error=clean_err(e)), 400
        return jsonify(error="ဖိုင်စစ်ရင်း အမှားရှိတယ်"), 500
    jobs[jid] = {"status": "queued", "stage": "queue", "pct": 0, "error": "",
                 "dir": d, "ext": ext, "direction": direction,
                 "voice": voice, "created": time.time()}
    fname = re.sub(r"[\r\n]", " ", f.filename or "?")[:80]
    jlog(jobs[jid], f"uploaded {fname} ({src.stat().st_size / 1048576:.1f} MB)")
    with lock:
        queue.append(jid)
        lock.notify()
    return jsonify(job_id=jid)


@app.get("/api/jobs/<jid>")
def job_status(jid):
    job = jobs.get(jid)
    if not job:
        return jsonify(error="job မတွေ့ဘူး"), 404
    return jsonify(status=job["status"], stage=job["stage"], pct=job["pct"],
                   label=STAGE_LABEL.get(job["stage"], job["stage"]),
                   error=job["error"])


@app.get("/api/jobs/<jid>/log")
def job_log(jid):
    job = jobs.get(jid)
    if not job:
        return jsonify(error="job မတွေ့ဘူး"), 404
    p = job["dir"] / "job.log"
    return jsonify(log=p.read_text() if p.exists() else "")


@app.post("/api/reviews")
def add_review():
    if not _rate_ok(_client_ip()):
        return jsonify(error="ခဏနေမှ ပြန်စမ်းပါ"), 429
    data = request.get_json(force=True, silent=True) or {}
    try:
        stars = int(data.get("stars", 0))
    except (TypeError, ValueError):
        stars = 0
    msg = re.sub(r"\s+", " ", str(data.get("message") or "")).strip()[:500]
    jid = re.sub(r"[^0-9a-f]", "", str(data.get("job_id") or ""))[:12]
    if not (1 <= stars <= 5) and not msg:
        return jsonify(error="star ဒါမှမဟုတ် စာတစ်ခုခု ပေးပါ"), 400
    rec = {"id": uuid.uuid4().hex[:8], "ts": time.time(), "ip": _client_ip(),
           "stars": stars if 1 <= stars <= 5 else 0,
           "message": msg, "job_id": jid}
    try:
        with open(REVIEWS, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        return jsonify(error="သိမ်းမရဘူး"), 500
    return jsonify(ok=True)


@app.get("/admin/reviews")
def admin_reviews():
    if not ADMIN_KEY or request.args.get("key") != ADMIN_KEY:
        return "not found", 404
    return render_template("admin.html")


def _read_reviews():
    rows = []
    if REVIEWS.exists():
        for line in REVIEWS.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return rows


def _admin_ok():
    return bool(ADMIN_KEY) and request.args.get("key") == ADMIN_KEY


@app.get("/admin/api/reviews")
def admin_api_reviews():
    if not _admin_ok():
        return jsonify(error="not found"), 404
    rows = _read_reviews()
    dist = {str(i): 0 for i in range(1, 6)}
    total_stars = rated = 0
    for r in rows:
        s = r.get("stars", 0)
        if 1 <= s <= 5:
            dist[str(s)] += 1
            total_stars += s
            rated += 1
    return jsonify(reviews=rows[:300], stats={
        "total": len(rows), "rated": rated,
        "avg": round(total_stars / rated, 1) if rated else 0,
        "dist": dist})


@app.delete("/admin/api/reviews/<rid>")
def admin_del_review(rid):
    if not _admin_ok():
        return jsonify(error="not found"), 404
    rid = re.sub(r"[^0-9a-f]", "", rid)[:8]
    rows = _read_reviews()
    kept = [r for r in rows if r.get("id") != rid]
    if len(kept) == len(rows):
        return jsonify(error="not found"), 404
    try:
        with open(REVIEWS, "w", encoding="utf-8") as fh:
            for r in kept:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError:
        return jsonify(error="write failed"), 500
    return jsonify(ok=True)


@app.get("/r/<jid>")
def result(jid):
    job = jobs.get(jid)
    if not job or job["status"] != "done":
        return jsonify(error="အဆင်သင့် မဖြစ်သေးဘူး"), 404
    return send_file(job["dir"] / "dubbed.mp4", as_attachment=True,
                     download_name="dublab-dubbed.mp4")
