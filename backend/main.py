"""
MusicToGP — FastAPI backend
Converts YouTube videos to Guitar Pro (.gp5) tablature files.
"""

import os
import re
import uuid
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.downloader import download_audio
from services.gp_converter import convert_to_gp
from services.pdf_parser import parse_pdf_tab
from services.transcriber import transcribe_audio

APP_VERSION = "2.9"

app = FastAPI(title="MusicToGP API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# In-memory job store — replace with Redis for production
jobs: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ConvertRequest(BaseModel):
    url: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    filename: Optional[str] = None


def _is_supported_youtube_url(raw_url: str) -> bool:
    """Allow youtube.com/m.youtube.com/music.youtube.com/youtu.be URL forms used by the UI."""
    try:
        parsed = urlparse(raw_url.strip())
    except Exception:  # noqa: BLE001
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    host = parsed.netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]

    if host == "youtu.be":
        return bool(parsed.path.strip("/"))

    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        path = parsed.path.strip("/")
        if path == "watch":
            return bool(parse_qs(parsed.query).get("v", [""])[0])
        if path.startswith("shorts/") or path.startswith("embed/"):
            parts = path.split("/")
            return len(parts) >= 2 and bool(parts[1])

    return False


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

def _update_job(job_id: str, status: str, progress: int, message: str, **extra) -> None:
    jobs[job_id] = {"status": status, "progress": progress, "message": message, **extra}


def process_video(job_id: str, url: str) -> None:
    """Full conversion pipeline executed as a background task."""
    audio_path: Optional[Path] = None
    try:
        _update_job(job_id, "processing", 10, "Downloading audio…")
        audio_path, title = download_audio(url, TEMP_DIR)

        # No stem separation — the source is already a solo guitar recording.
        # Running demucs on a mono-instrument file introduces phase artefacts
        # and incorrectly splits bass notes into a separate stem.
        _update_job(job_id, "processing", 40, "Transcribing notes with ML model…")
        note_events, bpm = transcribe_audio(audio_path)

        _update_job(job_id, "processing", 80, "Converting to Guitar Pro format…")

        # Sanitise the video title for use as a filename
        safe_title = "".join(
            c for c in title if c.isalnum() or c in " -_()"
        ).strip() or "track"
        output_filename = f"{safe_title[:60]}_{job_id[:8]}.gp5"
        output_path = OUTPUT_DIR / output_filename

        convert_to_gp(note_events, title, str(output_path), bpm=bpm)

        _update_job(
            job_id,
            "completed",
            100,
            "Conversion complete!",
            filename=output_filename,
        )
    except Exception as exc:  # noqa: BLE001
        _update_job(job_id, "failed", 0, f"Error: {exc}")
    finally:
        if audio_path and audio_path.exists():
            audio_path.unlink(missing_ok=True)


def process_pdf(job_id: str, pdf_path: Path, stem: str) -> None:
    """PDF tab → GP5 conversion executed as a background task."""
    try:
        _update_job(job_id, "processing", 30, "Parsing guitar tablature from PDF…")
        note_events, bpm = parse_pdf_tab(pdf_path)

        _update_job(job_id, "processing", 80, "Converting to Guitar Pro format…")
        safe_stem = "".join(
            c for c in stem if c.isalnum() or c in " -_()"
        ).strip() or "tab"
        output_filename = f"{safe_stem[:60]}_{job_id[:8]}.gp5"
        output_path = OUTPUT_DIR / output_filename

        convert_to_gp(
            note_events, safe_stem, str(output_path),
            bpm=bpm, force_feel='straight',
            resonance_window=0, chord_merge=0, density_cap=32,
            beat1_snap=4,
        )

        _update_job(
            job_id, "completed", 100, "Conversion complete!",
            filename=output_filename,
        )
    except Exception as exc:  # noqa: BLE001
        _update_job(job_id, "failed", 0, f"Error: {exc}")
    finally:
        if pdf_path.exists():
            pdf_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.post("/api/convert", response_model=JobResponse, status_code=202)
async def convert_video(request: ConvertRequest, background_tasks: BackgroundTasks):
    """Accept a YouTube URL, enqueue the conversion job, return a job_id."""
    if not request.url.strip():
        raise HTTPException(status_code=422, detail="url must not be empty")
    if not _is_supported_youtube_url(request.url):
        raise HTTPException(
            status_code=422,
            detail=(
                "Please provide a valid YouTube URL (watch, youtu.be, shorts, or embed). "
                "Best scanning quality is achieved with solo fingerpicking acoustic/classical guitar videos."
            ),
        )

    job_id = str(uuid.uuid4())
    _update_job(job_id, "pending", 0, "Queued…")
    background_tasks.add_task(process_video, job_id, request.url.strip())
    return {**jobs[job_id], "job_id": job_id}


@app.post("/api/convert-pdf", response_model=JobResponse, status_code=202)
async def convert_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """Accept a PDF tab file, enqueue the conversion job, return a job_id."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Uploaded file must be a .pdf")

    # Hard-cap at 20 MB to prevent resource exhaustion
    MAX_PDF_BYTES = 20 * 1024 * 1024
    content = await file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF must be smaller than 20 MB")

    job_id = str(uuid.uuid4())
    # Save the PDF to a temp file so the background task can read it
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file.filename)
    pdf_temp_path = TEMP_DIR / f"{job_id}_{safe_name}"
    pdf_temp_path.write_bytes(content)

    stem = Path(file.filename).stem
    _update_job(job_id, "pending", 0, "Queued\u2026")
    background_tasks.add_task(process_pdf, job_id, pdf_temp_path, stem)
    return {**jobs[job_id], "job_id": job_id}


@app.post("/api/pdf-debug")
async def pdf_debug(file: UploadFile = File(...)):
    """Diagnostic endpoint: shows what each extraction method sees in a PDF.
    Returns a JSON summary useful for debugging failed conversions."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Uploaded file must be a .pdf")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF must be smaller than 20 MB")

    import pdfplumber
    from services.pdf_parser import (
        _group_tab_systems, _extract_tab_via_char_coords,
        _extract_tab_via_stave_detection,
    )

    tmp = TEMP_DIR / f"debug_{uuid.uuid4()}.pdf"
    tmp.write_bytes(content)
    result: dict = {}
    try:
        # 1. Plain text extraction
        plain_lines: list[str] = []
        with pdfplumber.open(str(tmp)) as pdf:
            for pg in pdf.pages:
                plain_lines.extend((pg.extract_text(x_tolerance=2, y_tolerance=3) or "").splitlines())
        result["plain_text_lines"] = len(plain_lines)
        result["plain_text_sample"] = plain_lines[:15]
        result["plain_text_tab_systems"] = len(_group_tab_systems(plain_lines))

        # 2. Char coordinate extraction
        coord_text, coord_lines = _extract_tab_via_char_coords(tmp)
        result["coord_lines"] = len(coord_lines)
        result["coord_sample"] = coord_lines[:12]
        result["coord_tab_systems"] = len(_group_tab_systems(coord_lines))

        # 3. Count raw digit chars pdfplumber can see
        digit_count = 0
        digit_sample: list = []
        with pdfplumber.open(str(tmp)) as pdf:
            for pg in pdf.pages[:1]:
                for c in (pg.chars or []):
                    if c.get('text', '').isdigit():
                        digit_count += 1
                        if len(digit_sample) < 20:
                            digit_sample.append({
                                "text": c['text'],
                                "x0": round(c['x0'], 1),
                                "top": round(c['top'], 1),
                            })
        result["digit_chars_page1"] = digit_count
        result["digit_chars_sample"] = digit_sample

    finally:
        tmp.unlink(missing_ok=True)

    return result


@app.get("/api/version")
async def get_version():
    return {"version": APP_VERSION}


@app.get("/api/status/{job_id}", response_model=JobResponse)
async def get_status(job_id: str):
    """Poll the status of a conversion job."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, **job}


@app.get("/api/download/{job_id}")
async def download_file(job_id: str):
    """Download the finished .gp5 file for a completed job."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed yet")

    filepath = OUTPUT_DIR / job["filename"]
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        str(filepath),
        media_type="application/octet-stream",
        filename=job["filename"],
    )


# ---------------------------------------------------------------------------
# Serve frontend (must be mounted last so API routes take priority)
# ---------------------------------------------------------------------------

FRONTEND_DIR = BASE_DIR.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
