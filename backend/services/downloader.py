"""
downloader.py — yt-dlp wrapper
Downloads audio from a YouTube URL and returns the local WAV path + video title.
"""

import re
import shutil
from pathlib import Path
from typing import Tuple

import yt_dlp


def _find_ffmpeg() -> str | None:
    """
    Resolve the ffmpeg executable path.
    Checks PATH first, then falls back to the default winget install location.
    """
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    # winget (Gyan.FFmpeg) default location
    winget_path = (
        Path.home()
        / "AppData/Local/Microsoft/WinGet/Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        / "ffmpeg-8.1-full_build/bin/ffmpeg.exe"
    )
    if winget_path.exists():
        return str(winget_path.parent)
    return None


def _sanitise_title(title: str) -> str:
    """Remove characters that are unsafe in filenames."""
    return re.sub(r'[\\/*?:"<>|]', "_", title).strip()


def download_audio(url: str, output_dir: Path) -> Tuple[Path, str]:
    """
    Download the best-quality audio from *url* and convert it to a WAV file.

    Parameters
    ----------
    url:        YouTube (or yt-dlp-compatible) video URL
    output_dir: Directory in which the temporary WAV file is written

    Returns
    -------
    (wav_path, video_title)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # We use a placeholder; yt-dlp will append the real extension after conversion
    outtmpl = str(output_dir / "%(id)s.%(ext)s")

    ffmpeg_location = _find_ffmpeg()

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",  # lossless PCM
            }
        ],
        "quiet": True,
        "no_warnings": True,
        # Do not download playlists — only the first (or given) video
        "noplaylist": True,
    }

    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    video_id: str = info["id"]
    title: str = _sanitise_title(info.get("title", "Unknown"))
    wav_path = output_dir / f"{video_id}.wav"

    if not wav_path.exists():
        raise FileNotFoundError(
            f"Expected WAV file not found after download: {wav_path}"
        )

    return wav_path, title
