"""
notation_parser.py — Parse *standard music notation* PDFs into NoteEvents.

ASCII guitar tab PDFs are handled by pdf_parser.py.  This module covers the
complementary case: PDFs that contain staff notation (treble/bass clef), as
produced by MuseScore, Finale, Sibelius, LilyPond, or similar applications.

Two strategies are attempted in order:

1. **Embedded MusicXML** — Notation software (MuseScore 4, LilyPond, some
   Sibelius/Finale exports) can embed a MusicXML attachment *inside* the PDF
   binary.  PyMuPDF's embedded-file API is used to extract it.

2. **OMR via oemer** — If no embedded XML is found, each PDF page is
   rasterised with PyMuPDF and fed to the ``oemer`` optical-music-recognition
   engine (https://github.com/BreezeWhite/oemer), which outputs MusicXML.
   ``oemer`` is NOT installed by default (it requires PyTorch and is ~1.5 GB).
   Install it separately::

       pip install oemer

In both cases the MusicXML is parsed by ``music21`` to produce a flat list of
NoteEvents: ``(start_sec, end_sec, midi_pitch, amplitude)``.

``music21`` *is* a required dependency (listed in requirements.txt).
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# NoteEvent: (start_sec, end_sec, midi_pitch, amplitude)
NoteEvent = Tuple[float, float, int, float]

_DEFAULT_BPM = 120.0

# Guitar MIDI range (E2 = 40, high fret = 88)
_GUITAR_MIDI_MIN = 40
_GUITAR_MIDI_MAX = 88

# Guitar notation is written an octave *above* concert pitch.
# Subtract 12 when converting written pitch → sounding pitch.
_GUITAR_OCTAVE_OFFSET = -12


# ---------------------------------------------------------------------------
# Strategy 1 — Embedded MusicXML
# ---------------------------------------------------------------------------

def _extract_embedded_musicxml(pdf_path: Path) -> Optional[str]:
    """Return the first embedded MusicXML string found inside the PDF, or None."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.debug("PyMuPDF not available; skipping embedded XML extraction.")
        return None

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.debug("fitz.open failed: %s", exc)
        return None

    count = doc.embfile_count()
    for i in range(count):
        try:
            info = doc.embfile_info(i)
            name: str = info.get("name", "") or info.get("filename", "") or ""
            if name.lower().endswith((".xml", ".musicxml", ".mxl")):
                data: bytes = doc.embfile_get(i)
                try:
                    return data.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        return data.decode("latin-1")
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("Embedded file %d read error: %s", i, exc)

    doc.close()
    return None


# ---------------------------------------------------------------------------
# Strategy 2 — OMR via oemer
# ---------------------------------------------------------------------------

def _rasterise_pages(pdf_path: Path, dpi: int = 200) -> List[str]:
    """Rasterise every page to a temp PNG; return list of file paths."""
    import fitz  # PyMuPDF — guaranteed to be present (already in requirements)

    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    paths: List[str] = []

    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        pix.save(tmp_path)
        paths.append(tmp_path)

    doc.close()
    return paths


def _run_oemer(image_path: str) -> Optional[str]:
    """Run oemer on *image_path*; return the produced MusicXML text or None.

    oemer writes its output next to the image by default.  The output file
    has the same stem as the image with a ``.musicxml`` extension.
    """
    out_xml = os.path.splitext(image_path)[0] + ".musicxml"

    try:
        result = subprocess.run(
            ["oemer", image_path],
            capture_output=True,
            text=True,
            timeout=300,  # OMR can take a while on free-tier CPU
        )
        logger.debug("oemer stdout: %s", result.stdout[-500:] if result.stdout else "")
        logger.debug("oemer stderr: %s", result.stderr[-500:] if result.stderr else "")
    except FileNotFoundError:
        # oemer is not installed — not a hard error, handled by the caller
        raise RuntimeError(
            "oemer is not installed. "
            "To enable optical music recognition, run: pip install oemer"
        )
    except subprocess.TimeoutExpired:
        logger.warning("oemer timed out processing %s", image_path)
        return None
    except Exception as exc:
        logger.warning("oemer failed: %s", exc)
        return None

    if os.path.isfile(out_xml):
        try:
            with open(out_xml, encoding="utf-8") as f:
                return f.read()
        except Exception as exc:
            logger.warning("Could not read oemer output %s: %s", out_xml, exc)

    # oemer sometimes puts output in cwd — also check there
    cwd_xml = os.path.join(
        os.getcwd(),
        os.path.splitext(os.path.basename(image_path))[0] + ".musicxml",
    )
    if cwd_xml != out_xml and os.path.isfile(cwd_xml):
        try:
            with open(cwd_xml, encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# MusicXML → NoteEvents (via music21)
# ---------------------------------------------------------------------------

def _musicxml_to_events(xml_str: str) -> Tuple[List[NoteEvent], float]:
    """Parse a MusicXML string with music21; return (NoteEvents, bpm).

    Notes:
    - Guitar notation is transposing: written pitch sounds an octave lower.
      We subtract 12 from the MIDI pitch to get the sounding pitch.
    - Notes outside the guitar MIDI range (40–88) are discarded.
    """
    try:
        from music21 import converter
        from music21 import tempo as m21tempo
    except ImportError as exc:
        raise RuntimeError(
            "music21 is required for standard notation parsing. "
            "Run: pip install music21"
        ) from exc

    try:
        score = converter.parseData(xml_str, format="musicxml")
    except Exception as exc:
        raise RuntimeError(f"music21 could not parse MusicXML: {exc}") from exc

    # Extract the first tempo marking; fall back to 120 BPM
    bpm = _DEFAULT_BPM
    for mm in score.flat.getElementsByClass(m21tempo.MetronomeMark):
        if mm.number:
            bpm = float(mm.number)
            break

    beat_dur_sec = 60.0 / bpm
    events: List[NoteEvent] = []

    for el in score.flat.notesAndRests:
        if el.isRest:
            continue

        # offset is in quarter-note beats from the start of the score
        start_sec = float(el.offset) * beat_dur_sec
        end_sec = start_sec + float(el.duration.quarterLength) * beat_dur_sec

        # Support both Note and Chord elements
        pitches = [el.pitch] if hasattr(el, "pitch") else list(getattr(el, "pitches", []))

        for pitch in pitches:
            # Apply guitar octave transposition: written concert pitches for
            # guitar notation are one octave above sounding pitch
            midi = pitch.midi + _GUITAR_OCTAVE_OFFSET
            if _GUITAR_MIDI_MIN <= midi <= _GUITAR_MIDI_MAX:
                events.append((start_sec, end_sec, midi, 0.8))

    events.sort(key=lambda e: e[0])
    return events, bpm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_notation_pdf(pdf_path: Path) -> Tuple[List[NoteEvent], float]:
    """Parse a standard-notation PDF into NoteEvents.

    Tries, in order:
      1. Embedded MusicXML inside the PDF
      2. oemer OMR on each rasterised page

    Raises
    ------
    RuntimeError
        When neither strategy yields any note events.  The message explains
        what was tried and what the user can do.
    """
    errors: List[str] = []

    # ── 1. Embedded MusicXML ────────────────────────────────────────────────
    xml = _extract_embedded_musicxml(pdf_path)
    if xml:
        logger.info("Found embedded MusicXML in %s", pdf_path.name)
        try:
            events, bpm = _musicxml_to_events(xml)
            if events:
                logger.info(
                    "Extracted %d note events from embedded MusicXML (BPM=%.1f)",
                    len(events), bpm,
                )
                return events, bpm
            errors.append("Embedded MusicXML contained no notes in the guitar range.")
        except RuntimeError as exc:
            errors.append(f"Embedded MusicXML parse error: {exc}")

    # ── 2. OMR via oemer ────────────────────────────────────────────────────
    img_paths: List[str] = []
    try:
        img_paths = _rasterise_pages(pdf_path)
        all_events: List[NoteEvent] = []
        bpm = _DEFAULT_BPM
        oemer_missing = False

        for img_path in img_paths:
            try:
                xml = _run_oemer(img_path)
            except RuntimeError as exc:
                # oemer not installed
                errors.append(str(exc))
                oemer_missing = True
                break

            if xml:
                try:
                    evs, page_bpm = _musicxml_to_events(xml)
                    if page_bpm != _DEFAULT_BPM:
                        bpm = page_bpm
                    # Offset page events by the end time of the previous page
                    t_offset = all_events[-1][1] if all_events else 0.0
                    for ev in evs:
                        all_events.append((
                            ev[0] + t_offset,
                            ev[1] + t_offset,
                            ev[2],
                            ev[3],
                        ))
                except RuntimeError as exc:
                    errors.append(f"oemer output parse error: {exc}")
            else:
                errors.append(f"oemer produced no output for page {img_path}.")

        if all_events:
            logger.info(
                "OMR extracted %d note events (BPM=%.1f)", len(all_events), bpm
            )
            return all_events, bpm

    finally:
        # Always clean up temp raster images
        for p in img_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    # ── Nothing worked ──────────────────────────────────────────────────────
    detail = "\n  • ".join(errors) if errors else "Unknown error."
    raise RuntimeError(
        f"Could not extract notes from the notation PDF '{pdf_path.name}'.\n\n"
        f"Attempted:\n  • {detail}\n\n"
        "Suggestions:\n"
        "  1. If this PDF was created with MuseScore, export it as MusicXML "
        "(.xml) and upload that file instead.\n"
        "  2. To enable optical music recognition (OMR), install oemer:\n"
        "       pip install oemer\n"
        "     Note: oemer requires PyTorch and ~1.5 GB of disk space.\n"
        "  3. If this PDF contains guitar *tablature* (not staff notation), "
        "make sure the tab lines are selectable text (not a scanned image)."
    )
