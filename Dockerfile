# DubLab — container image
# Build:  docker build -t dublab .
# Run:    docker run -d --name dublab -p 127.0.0.1:8092:8092 --env-file .env dublab
FROM python:3.12-slim

# ffmpeg: DubLab shells out to it for audio extract/mux, plus DejaVu for the watermark
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/dublab

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py dub.py gemini.py gemini_tts.py edge_probe.py ./
COPY templates/ templates/
COPY static/ static/

EXPOSE 8092
CMD ["waitress-serve", "--listen=0.0.0.0:8092", "--threads=8", "app:app"]
