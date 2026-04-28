# MusicToGP — Copilot Workspace Instructions

These instructions apply automatically to every Copilot interaction in this workspace.
Add new project-wide rules below and they will be picked up immediately.

## Project Overview

**MusicToGP** is a web-based application that converts YouTube videos into Guitar Pro (`.gp5`) tablature files.

**Pipeline**:
1. User submits a YouTube URL via the web UI
2. Backend downloads the audio with `yt-dlp`
3. (Optional) Source separation via `demucs` to isolate melodic content
4. Polyphonic pitch detection via `basic-pitch` (Spotify) → MIDI note events
5. MIDI note events mapped to guitar string/fret positions → `.gp5` via `PyGuitarPro`
6. User downloads the finished Guitar Pro file

**Tech Stack**:
- **Backend**: Python 3.11+, FastAPI, uvicorn
- **Audio processing**: `yt-dlp`, `librosa` (piptrack + onset detection for pitch), `demucs`
- **GP generation**: `PyGuitarPro` (`guitarpro` package)
- **Frontend**: Plain HTML5 / CSS3 / Vanilla JS (no framework)
- **Job queue**: In-memory dict (dev); Redis-backed queue for production

**Folder layout**:
```
MusicToGP/
├── backend/
│   ├── main.py               # FastAPI app + routes
│   ├── services/
│   │   ├── downloader.py     # yt-dlp wrapper
│   │   ├── transcriber.py    # basic-pitch wrapper
│   │   └── gp_converter.py   # MIDI → GP5
│   ├── temp/                 # transient audio files (gitignored)
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

## Coding Standards

- Python: follow PEP 8; use type hints on all function signatures
- Use `async`/`await` for FastAPI routes; CPU-heavy work runs in `BackgroundTasks`
- Keep each service file focused on a single responsibility
- Frontend: ES2020+ vanilla JS; no jQuery or bundlers
- CSS: custom properties (`--var`) for theming; mobile-first responsive layout

## Architecture & Patterns

- **Job model**: Each conversion is a `job_id` (UUID). Status is tracked as `pending → processing → completed | failed` with a `progress` (0–100 int) and human-readable `message`.
- **API surface**: All backend routes live under `/api/`; static frontend is served from `/`
- **String/fret mapping**: Prefer lowest fret number across all strings (minimise stretch); standard tuning only (E2 A2 D3 G3 B3 E4)
- **Tempo**: Detected via `librosa.beat.beat_track`; falls back to 120 BPM
- **Note quantization**: 16th-note grid; map duration in seconds → nearest GP `Duration.value` (1/2/4/8/16/32)

## Do's and Don'ts

- **DO** sanitise any filename derived from user input / video title before writing to disk
- **DO** delete temp audio files immediately after the GP file is written
- **DO** return structured JSON error responses from the API (never raw tracebacks)
- **DON'T** store YouTube URLs or user data beyond the lifetime of the job
- **DON'T** add authentication — this is a local/offline tool
- **DON'T** use blocking I/O inside async route handlers
