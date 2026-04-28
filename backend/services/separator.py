"""
separator.py — Instrument isolation via Meta's Demucs
Strips drums, bass, and lead vocals from a full-band recording so that
basic-pitch works on a much cleaner guitar/melodic signal.

Model used: htdemucs (4-stem: drums | bass | other | vocals)
The 'other' stem captures guitar, piano, strings, and all other melodic content.

The demucs model (~80 MB) is downloaded to ~/.cache/torch/hub/checkpoints on
first use and cached for subsequent runs.
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def separate_to_other_stem(audio_path: Path, output_path: Path) -> None:
    """
    Run demucs on *audio_path* and write the 'other' instrumental stem
    (guitar + melodic instruments, no drums/bass/vocals) to *output_path*.

    Parameters
    ----------
    audio_path  : Input audio file (any format readable by librosa)
    output_path : Destination WAV file for the separated stem
    """
    import torch
    import librosa
    import soundfile as sf
    from demucs.pretrained import get_model
    from demucs.apply import apply_model

    logger.info("Loading demucs htdemucs model…")
    model = get_model("htdemucs")
    model.eval()

    # Load at demucs native sample rate (44 100 Hz) as stereo
    audio, _ = librosa.load(str(audio_path), sr=model.samplerate, mono=False)
    if audio.ndim == 1:
        audio = np.stack([audio, audio])  # mono → pseudo-stereo

    wav = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)  # [1, 2, N]

    logger.info("Running source separation (this may take a few minutes)…")
    with torch.no_grad():
        sources = apply_model(
            model,
            wav,
            device="cpu",
            shifts=0,        # no TTA — trades a little quality for 2× speed
            split=True,      # process in chunks to save memory
            overlap=0.25,
            progress=False,
        )

    # sources shape: [batch=1, stems=4, channels=2, samples]
    # stem order from htdemucs: drums=0, bass=1, other=2, vocals=3
    #
    # For fingerstyle guitar: the thumb bass notes typically end up in the
    # "bass" stem. Include both "bass" and "other" so we capture the full
    # guitar range (melody + bass line).
    bass_idx = model.sources.index("bass")
    other_idx = model.sources.index("other")
    mixed = sources[0, other_idx] + sources[0, bass_idx]   # [channels=2, samples]
    mono_audio = mixed.numpy().mean(axis=0)                 # average to mono

    sf.write(str(output_path), mono_audio, model.samplerate)
    duration = len(mono_audio) / model.samplerate
    logger.info("Separation complete: %.1f s of audio saved to %s", duration, output_path.name)
