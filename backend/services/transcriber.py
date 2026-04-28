"""
transcriber.py — ML-based polyphonic note detection via Spotify's basic-pitch
Uses the basic-pitch ONNX inference backend (no TensorFlow required) to detect
note events from an audio file. Tempo is estimated with librosa.beat_track.
Returns note events together with the estimated tempo (BPM).
"""

import logging
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
# Suppress basic-pitch "TF/coreml not installed" startup messages — we use ONNX
logging.getLogger("root").setLevel(logging.ERROR)

from pathlib import Path
from typing import List, Tuple

import librosa
import numpy as np

# NoteEvent: (start_sec, end_sec, midi_pitch, amplitude)
NoteEvent = Tuple[float, float, int, float]

# Guitar MIDI range: low-E open (E2 = 40) to ~24th fret high-E (E6 = 88)
_MIDI_MIN = 40
_MIDI_MAX = 88

# basic-pitch inference parameters — tuned for acoustic/fingerstyle guitar
# Higher onset_threshold = fewer but more confident notes (rejects sympathetic resonance)
# Higher min_note_ms = rejects short transient artifacts; 200ms ≈ 8th-note triplet @ 100 BPM
_ONSET_THRESHOLD = 0.65     # 0.60→0.65: only strongly-plucked note onsets survive
_FRAME_THRESHOLD = 0.3      # unchanged
_MIN_NOTE_MS = 200.0        # 120→200ms: filters sub-16th resonance noise


def transcribe_audio(audio_path: Path) -> Tuple[List[NoteEvent], float]:
    """
    Detect note events in *audio_path* using Spotify's basic-pitch ML model
    (ONNX inference backend — no TensorFlow required).

    Strategy
    --------
    1. Estimate tempo with librosa.beat_track.
    2. Run basic-pitch polyphonic pitch detection on the raw audio.
    3. Filter note events to guitar range (MIDI 40–88).

    Parameters
    ----------
    audio_path : Path to a WAV (or other librosa-readable) audio file

    Returns
    -------
    (note_events, bpm)
        note_events — list of (start_sec, end_sec, midi_pitch, amplitude)
        bpm         — estimated tempo in beats-per-minute
    """
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    SR = 22_050
    y, sr = librosa.load(str(audio_path), sr=SR, mono=True)

    # ── Tempo ────────────────────────────────────────────────────────────
    # start_bpm=90 biases away from double-time (common for fingerstyle guitar)
    tempo_arr, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=90)
    bpm = float(np.atleast_1d(tempo_arr)[0])
    if not (40.0 <= bpm <= 300.0):
        bpm = 120.0
    # Fingerstyle guitar often fools beat_track into double-time; halve if needed
    if bpm > 140.0 and 60.0 <= bpm / 2.0 <= 140.0:
        bpm = bpm / 2.0
    # Slow ballads with a compound/triplet feel (12/8 at ~64 BPM) fool beat_track
    # into finding the triplet subdivision as the beat (~96 BPM = 64 × 3/2).
    # If detected BPM is 85–110 and dividing by 1.5 gives a valid ballad tempo
    # (50–75 BPM), apply the correction.
    if 85.0 <= bpm <= 110.0 and 50.0 <= bpm / 1.5 <= 75.0:
        bpm = bpm / 1.5

    # ── basic-pitch polyphonic note detection ────────────────────────────
    _model_output, _midi_data, note_events_raw = predict(
        str(audio_path),
        ICASSP_2022_MODEL_PATH,
        onset_threshold=_ONSET_THRESHOLD,
        frame_threshold=_FRAME_THRESHOLD,
        minimum_note_length=_MIN_NOTE_MS,
        minimum_frequency=float(librosa.midi_to_hz(_MIDI_MIN)),
        maximum_frequency=float(librosa.midi_to_hz(_MIDI_MAX)),
        multiple_pitch_bends=False,
    )

    # ── Convert to NoteEvent format ──────────────────────────────────────
    events: List[NoteEvent] = []
    for start, end, midi_pitch, amplitude, _bends in note_events_raw:
        pitch = int(midi_pitch)
        if _MIDI_MIN <= pitch <= _MIDI_MAX:
            events.append((float(start), float(end), pitch, float(amplitude)))

    events.sort(key=lambda e: e[0])
    return events, bpm
