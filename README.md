# MusicToGP 🎸

Convert any YouTube video into a downloadable **Guitar Pro (.gp5)** tablature file — entirely in your browser, running locally.

## How it works

```
YouTube URL → yt-dlp → WAV → basic-pitch (AI) → note events → PyGuitarPro → .gp5
```

1. **yt-dlp** downloads the best-quality audio track from the YouTube video.
2. **librosa** estimates the tempo (BPM).
3. **basic-pitch** (Spotify's AI model) detects every pitch in the audio as MIDI note events.
4. **gp_converter** maps each note to a guitar string/fret position using standard tuning (E A D G B e) and writes a `.gp5` file with **PyGuitarPro**.
5. The file is served to the browser for immediate download.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://www.python.org) |
| ffmpeg | any recent | `winget install ffmpeg` / `brew install ffmpeg` |
| pip | latest | bundled with Python |

---

## Quick start

```bash
# 1. Clone / open the project
cd MusicToGP

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r backend/requirements.txt

# 4. Start the server
cd backend
uvicorn main:app --reload --port 8000

# 5. Open your browser
#    http://localhost:8000
```

Paste a YouTube URL into the input field and click **Convert**.  
When the progress bar reaches 100 %, click **Download .gp5 file**.

---

## Deploying with Docker

### Build and run locally

```bash
# Build the image (takes a few minutes — downloads ML models on first use)
docker build -t musictogp .

# Run the container
docker run -p 8000:8000 musictogp

# Open http://localhost:8000
```

The image includes all system dependencies (`ffmpeg`, `tesseract-ocr`) so no separate installs are needed.

### Deploy to a cloud platform

The container can be pushed to any Docker-compatible host.

#### Render (free tier available)

1. Push your code to a GitHub repository.
2. Go to [render.com](https://render.com) → **New Web Service** → connect your repo.
3. Set **Environment** to `Docker` — Render auto-detects the `Dockerfile`.
4. Set the port to `8000`.
5. Click **Deploy**.

#### Railway

```bash
# Install the Railway CLI, then:
railway login
railway init
railway up
```

#### Fly.io

```bash
fly launch          # auto-detects Dockerfile, prompts for region
fly deploy
```

> **Note on job state**: The server stores job status in memory. Restarting or scaling to multiple instances will lose in-flight jobs. For production use, replace the in-memory `_jobs` dict in `main.py` with a Redis-backed store.

---

## Project structure

```
MusicToGP/
├── backend/
│   ├── main.py               # FastAPI app + API routes
│   ├── services/
│   │   ├── downloader.py     # yt-dlp wrapper → WAV
│   │   ├── transcriber.py    # basic-pitch wrapper → note events + BPM
│   │   └── gp_converter.py   # note events → .gp5 (PyGuitarPro)
│   ├── temp/                 # transient audio (auto-deleted, gitignored)
│   ├── output/               # generated .gp5 files (gitignored)
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── css/styles.css
│   └── js/app.js
├── .github/
│   └── copilot-instructions.md
├── .gitignore
└── README.md
```

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/convert` | Start a conversion job. Body: `{"url": "..."}` |
| `GET`  | `/api/status/{job_id}` | Poll job status (pending / processing / completed / failed) |
| `GET`  | `/api/download/{job_id}` | Stream the finished `.gp5` file |

### Job status response

```json
{
  "job_id": "uuid",
  "status": "processing",
  "progress": 40,
  "message": "Transcribing audio to notes…",
  "filename": null
}
```

---

## Notes & limitations

- **Accuracy** depends on the source audio. Clean, single-instrument recordings work best.
- Only **standard tuning** (E A D G B e) is supported at this time.
- Long videos (> 10 min) may take several minutes to process.
- Job state is stored **in memory** — restarting the server clears all jobs.
- No authentication or user accounts — this is a local/offline tool.

---

## License

MIT
