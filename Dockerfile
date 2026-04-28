# ── Stage 1: builder — install Python deps into a clean prefix ─────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System build deps (for librosa/soundfile native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./

# basic-pitch 0.4.0 has strict install-order requirements; handle them here.
# 1. Pin resampy first so basic-pitch can't pull a newer incompatible version.
# 2. Install basic-pitch without deps to preserve the pinned resampy.
# 3. Install everything else WITH deps (so uvicorn gets click, h11, etc.).
RUN pip install --upgrade pip setuptools==69.5.1 && \
    pip install "resampy==0.4.2" onnxruntime mir-eval pretty-midi && \
    pip install "basic-pitch==0.4.0" --no-deps && \
    pip install -r requirements.txt

# ── Stage 2: runtime image ─────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Runtime system dependencies:
#   ffmpeg     — required by yt-dlp for audio extraction
#   tesseract  — required by pytesseract / pdf_parser.py for OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create runtime directories (gitignored, so not in the repo)
RUN mkdir -p backend/temp backend/output

WORKDIR /app/backend

EXPOSE 8000

# Health check — uses $PORT with fallback to 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT','8000') + '/api/version')" || exit 1

# Render (and other platforms) inject $PORT at runtime; fall back to 8000 locally.
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
