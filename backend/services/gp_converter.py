"""
gp_converter.py — MIDI note events → Guitar Pro (.gp5)
Maps detected note events onto a 6-string guitar in standard tuning and writes
a .gp5 file using PyGuitarPro.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Tuple

import guitarpro

# NoteEvent: (start_sec, end_sec, midi_pitch, amplitude)
NoteEvent = Tuple[float, float, int, float]

# --------------------------------------------------------------------------
# Standard tuning: string number (1=high, 6=low) → open MIDI note
# --------------------------------------------------------------------------
STRING_OPEN: dict[int, int] = {
    1: 64,  # E4
    2: 59,  # B3
    3: 55,  # G3
    4: 50,  # D3
    5: 45,  # A2
    6: 40,  # E2
}
MAX_FRET = 22

# Quarter-note tick resolution used by PyGuitarPro
_QT = guitarpro.Duration.quarterTime  # 960

# Map GP Duration.value → beats (quarter notes)
_GP_VALUES = [
    (16, 0.25),
    (8,  0.5),
    (4,  1.0),
    (2,  2.0),
    (1,  4.0),
]
_STEPS_PER_MEASURE = 32  # 32nd-note grid in 4/4 (finer timing resolution)


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------

def _find_string_fret(midi_pitch: int) -> Tuple[int, int]:
    """
    Return (string_number, fret) for *midi_pitch* using standard tuning.
    Prefers the lowest fret across all playable strings (minimises stretch).
    String numbers: 1 = highest (E4), 6 = lowest (E2).
    """
    best_string, best_fret, best_fret_val = 1, 0, 999
    for string_num, open_note in STRING_OPEN.items():
        fret = midi_pitch - open_note
        if 0 <= fret <= MAX_FRET and fret < best_fret_val:
            best_fret_val = fret
            best_string, best_fret = string_num, fret
    return best_string, best_fret


def _find_string_fret_options(midi_pitch: int) -> List[Tuple[int, int]]:
    """Return all playable string/fret choices, sorted by low fret first."""
    options: List[Tuple[int, int]] = []
    for string_num, open_note in STRING_OPEN.items():
        fret = midi_pitch - open_note
        if 0 <= fret <= MAX_FRET:
            options.append((string_num, fret))
    return sorted(options, key=lambda item: (item[1], item[0]))


def _seconds_to_gp_value(duration_sec: float, bpm: float) -> int:
    """Map a note duration in seconds to the nearest GP Duration.value integer."""
    beat_dur = 60.0 / bpm
    beats = duration_sec / beat_dur
    return min(_GP_VALUES, key=lambda pair: abs(pair[1] - beats))[0]


# (steps_in_32nds, gp_duration_value, isDotted) — ordered largest first
# The 1-step entry (32nd note) is the safety minimum: it ensures _add_rests and
# _note_dur can always fill exactly the remaining steps in a measure without
# overflow (e.g. 1 step left before m_end → 32nd note, not a 16th that overflows).
_STEP_DUR_TABLE: List[Tuple[int, int, bool]] = [
    (32, 1,  False),
    (24, 2,  True ),
    (16, 2,  False),
    (12, 4,  True ),
    (8,  4,  False),
    (6,  8,  True ),
    (4,  8,  False),
    (3,  16, True ),
    (2,  16, False),
    (1,  32, False),   # 32nd note — fills the last step of a measure cleanly
]

# 12/8 time: step = 1 eighth note (_QT//2 = 480 ticks), 12 steps per measure
# (steps_in_8ths, gp_duration_value, isDotted) — ordered largest first
_STEP_DUR_TABLE_12_8: List[Tuple[int, int, bool]] = [
    (12, 1,  True ),   # dotted whole  (12 × 8th = full 12/8 measure)
    (8,  1,  False),   # whole note    (8 × 8th)
    (6,  2,  True ),   # dotted half   (6 × 8th)
    (4,  2,  False),   # half note     (4 × 8th)
    (3,  4,  True ),   # dotted quarter (3 × 8th = 1 compound beat)
    (2,  4,  False),   # quarter       (2 × 8th)
    (1,  8,  False),   # eighth note   (basic unit)
]


def _add_rests(
    voice: guitarpro.Voice,
    steps: int,
    step_dur_table: List[Tuple[int, int, bool]] = _STEP_DUR_TABLE,
) -> None:
    """Fill *steps* grid steps with rest beats using greedy decomposition."""
    remaining = steps
    for step_val, dur_val, dotted in step_dur_table:
        while remaining >= step_val:
            rest = guitarpro.Beat(voice, status=guitarpro.BeatStatus.rest)
            rest.duration = guitarpro.Duration(value=dur_val, isDotted=dotted)
            voice.beats.append(rest)
            remaining -= step_val


def _note_dur(
    desired_steps: int,
    max_steps: int,
    step_dur_table: List[Tuple[int, int, bool]] = _STEP_DUR_TABLE,
    fallback_steps: int = 2,
    fallback_val: int = 16,
) -> Tuple[guitarpro.Duration, int]:
    """Best-fit single GP Duration for a note onset fitting within max_steps.

    Returns (Duration, actual_steps_it_represents).

    The fallback is intentionally initialised to the smallest valid entry so
    that when max_steps is limited (e.g. 1 step left before a barline) we
    never return a duration that overflows the remaining space.
    """
    # Seed best from table itself (smallest entry that fits) so the fallback
    # always respects max_steps — a hard-coded 16th-note seed would overflow
    # when max_steps == 1.
    best_steps: int | None = None
    best_val   = fallback_val
    best_dot   = False
    best_diff  = float('inf')
    for step_val, dur_val, dotted in step_dur_table:
        if step_val <= max_steps:
            diff = abs(desired_steps - step_val)
            if diff < best_diff or (diff == best_diff and (best_steps is None or step_val > best_steps)):
                best_diff  = diff
                best_steps = step_val
                best_val   = dur_val
                best_dot   = dotted
    if best_steps is None:
        # Safety net: no entry fits (shouldn't happen if table has a 1-step entry)
        best_steps = min(fallback_steps, max_steps)
    return guitarpro.Duration(value=best_val, isDotted=best_dot), best_steps


def _map_chord_notes(midi_pitches: List[int]) -> List[Tuple[int, int, int]]:
    """Assign each MIDI pitch to a unique guitar string when possible."""
    used_strings: set[int] = set()
    mapped: List[Tuple[int, int, int]] = []
    for midi_pitch in sorted(midi_pitches):
        options = _find_string_fret_options(midi_pitch)
        chosen: Tuple[int, int] | None = None
        for string_num, fret in options:
            if string_num not in used_strings:
                chosen = (string_num, fret)
                break
        if chosen is None:
            string_num, fret = _find_string_fret(midi_pitch)
            if string_num in used_strings:
                continue
            chosen = (string_num, fret)
        used_strings.add(chosen[0])
        mapped.append((midi_pitch, chosen[0], chosen[1]))
    return mapped


def _apply_bars_per_line(track: guitarpro.Track, bars_per_line: int = 3) -> None:
    """Force a stable bars-per-line layout for GP editors/viewers.

    For each group, bars 1..(N-1) are protected from auto-wrap and bar N
    forces a new line.
    """
    if bars_per_line <= 0:
        return
    for idx, measure in enumerate(track.measures, start=1):
        if idx % bars_per_line == 0:
            measure.lineBreak = guitarpro.LineBreak.break_
        else:
            measure.lineBreak = guitarpro.LineBreak.protect


def _suppress_resonance(
    quantized: List[Tuple[int, int, int, float]],
    window: int = 8,
) -> List[Tuple[int, int, int, float]]:
    """
    Suppress re-attacks of the same pitch within *window* grid steps.

    Fingerstyle guitar strings ring sympathetically; basic-pitch re-detects ringing
    strings as new onsets. The window should be roughly one quarter-note equivalent:
    8 steps for the 32nd-note grid (4/4), or 2 steps for the 8th-note grid (12/8).
    """
    last_seen: dict[int, int] = {}
    out: List[Tuple[int, int, int, float]] = []
    for ev in quantized:
        start, end, pitch, amp = ev[:4]
        prev = last_seen.get(pitch)
        if prev is None or (start - prev) >= window:
            out.append((start, end, pitch, amp) + ev[4:])
            last_seen[pitch] = start
    return out


def _quantize_events(
    note_events: List[NoteEvent],
    step_sec: float,
    chord_merge_steps: int = 1,
) -> List[Tuple[int, int, int, float]]:
    """Quantize note events to a grid defined by *step_sec* seconds per step.

    *chord_merge_steps*: snap notes whose quantized start falls within this many
    steps after the previous onset onto that same step, treating them as a chord.
    Use 0 to disable merging (appropriate when the step is coarse, e.g. 12/8).
    """
    quantized: List[Tuple[int, int, int, float]] = []
    for ev in note_events:
        start_sec, end_sec, midi_pitch, amplitude = ev[:4]
        start_step = max(0, int(round(start_sec / step_sec)))
        end_step = max(start_step + 1, int(round(end_sec / step_sec)))
        # Preserve extra fields (e.g. string/fret from PDF parser) beyond the
        # first 4 so that the PDF-assigned positions survive into the GP writer.
        quantized.append((start_step, end_step, midi_pitch, float(amplitude)) + tuple(ev[4:]))
    quantized.sort(key=lambda item: (item[0], item[2]))

    if chord_merge_steps > 0 and quantized:
        merged: List[Tuple[int, int, int, float]] = [quantized[0]]
        for ev in quantized[1:]:
            if ev[0] - merged[-1][0] <= chord_merge_steps:
                # Preserve extra fields (string/fret) when merging onto same step
                merged.append((merged[-1][0], ev[1], ev[2], ev[3]) + tuple(ev[4:]))
            else:
                merged.append(ev)
        quantized = sorted(merged, key=lambda item: (item[0], item[2]))
    return quantized


def _select_notes_for_beat(pitch_amp_pairs: List[Tuple[int, float]]) -> List[int]:
    """
    Choose up to 4 notes from a simultaneous detection group.

    Guitar strings produce overtones: plucking C3 creates resonances at G3,
    C4, G4 which basic-pitch registers as separate notes.  Strategy:

    1. Drop any note whose amplitude is < 60 % of the loudest onset — these
       are nearly always sympathetic harmonics, not genuinely plucked strings.
    2. For each remaining pitch-class keep the highest-amplitude representative
       to remove octave doublings.
    3. Return all surviving notes (up to 4).  If more than 4 survive (very
       rare) keep the lowest (bass) plus the three highest (top melody voices).
    """
    if not pitch_amp_pairs:
        return []

    # Step 1 – drop weak harmonics / sympathetic resonance
    max_amp = max(amp for _, amp in pitch_amp_pairs)
    strong = [(p, a) for p, a in pitch_amp_pairs if a >= max_amp * 0.45]
    if not strong:
        strong = pitch_amp_pairs  # safety fallback

    # Step 2 – pitch-class deduplication.
    # Always keep the strongest note per pitch class.  Also keep a second note
    # in the same pitch class (e.g. C3 + C4) when its amplitude is ≥ 70% of the
    # strongest — that indicates it was genuinely plucked (bass-pinch chord),
    # not just a sympathetic harmonic whose amplitude would be much weaker.
    by_pc: Dict[int, List[Tuple[int, float]]] = {}
    for pitch, amp in strong:
        pc = pitch % 12
        by_pc.setdefault(pc, []).append((pitch, amp))

    survivors: List[int] = []
    for pc_notes in by_pc.values():
        pc_notes.sort(key=lambda x: x[1], reverse=True)  # strongest first
        survivors.append(pc_notes[0][0])                  # always keep strongest
        for pitch, amp in pc_notes[1:]:
            if amp >= pc_notes[0][1] * 0.70:              # near-equal → keep (chord, not harmonic)
                survivors.append(pitch)
    survivors.sort()

    # Step 3 – return all survivors, capped at 4 (bass + up to 3 voices)
    if len(survivors) <= 4:
        return survivors
    return [survivors[0]] + survivors[-3:]


# --------------------------------------------------------------------------
# Feel detection
# --------------------------------------------------------------------------

def _detect_feel(note_events: List[NoteEvent], bpm: float) -> str:
    """Return 'triplet' if onsets cluster at 1/3-beat intervals (12/8 compound feel).

    Computes the inter-onset intervals, normalises them to fractions of a beat,
    then counts how many fall near 1/3 beat (triplet-8th / 12/8) vs near 1/4 or
    1/2 beat (binary 16th / 8th).  The majority class wins.
    """
    if len(note_events) < 8:
        return 'straight'
    beat_sec = 60.0 / bpm
    onsets = sorted(e[0] for e in note_events)
    iois = [
        onsets[i + 1] - onsets[i]
        for i in range(len(onsets) - 1)
        if onsets[i + 1] - onsets[i] > 0.04   # ignore sub-40ms near-duplicates
    ]
    if not iois:
        return 'straight'
    beat_fracs = [ioi / beat_sec for ioi in iois]
    triplet_8th = sum(1 for f in beat_fracs if 0.27 <= f <= 0.39)   # ~1/3 beat
    binary_16th = sum(1 for f in beat_fracs if 0.20 <= f <= 0.27)   # ~1/4 beat
    binary_8th  = sum(1 for f in beat_fracs if 0.44 <= f <= 0.56)   # ~1/2 beat
    return 'triplet' if triplet_8th > (binary_16th + binary_8th) else 'straight'


# --------------------------------------------------------------------------
# Core conversion
# --------------------------------------------------------------------------

def convert_to_gp(
    note_events: List[NoteEvent],
    title: str,
    output_path: str,
    bpm: float = 120.0,
    force_feel: str | None = None,
    resonance_window: int | None = None,
    chord_merge: int | None = None,
    density_cap: int | None = None,
    beat1_snap: int = 0,
) -> None:
    """
    Convert *note_events* to a Guitar Pro 5 file at *output_path*.

    Parameters
    ----------
    note_events:       List of (start_sec, end_sec, midi_pitch, amplitude)
    title:             Song/track title embedded in the GP file
    output_path:       Destination .gp5 file path (string)
    bpm:               Tempo in beats per minute
    force_feel:        Override automatic feel detection.  Pass 'straight' for
                       4/4 (PDF tabs) or 'triplet' for 12/8.  None = auto.
    resonance_window:  Override resonance-suppression window (steps).  Pass 0
                       for PDF/tab sources where every note is explicit.
    chord_merge:       Override chord-merge step tolerance.  Pass 0 for PDF
                       sources where note positions are already on-grid.
    density_cap:       Override max notes per measure kept (highest amplitude).
                       Pass a large value (e.g. 32) for PDF tabs to keep every
                       notated note.
    beat1_snap:        When > 0, the first event in each measure is pulled back
                       to beat 1 (step 0) if it falls within this many steps of
                       the measure start and step 0 is otherwise vacant.  Use 4
                       for PDF tab sources: fret digits are printed 15-60 px
                       after each barline (standard digit left-margin), which
                       quantises to steps 1-4 instead of step 0, creating
                       spurious 32nd-note leading rests in Guitar Pro.  Steps
                       5+ are kept as genuine pickup rests (bars 1, 11 of
                       'Mr Lonely' genuinely start on beat 1.625+).
    """
    bpm = max(40.0, min(300.0, bpm))

    song = guitarpro.Song()
    song.title = title
    song.tempo = int(round(bpm))

    # ---- Configure the default track as a 6-string guitar ----------------
    track = song.tracks[0]
    track.name = "Guitar"
    track.isPercussionTrack = False
    track.strings = [
        guitarpro.GuitarString(number=num, value=open_note)
        for num, open_note in STRING_OPEN.items()
    ]
    track.channel.instrument = 25   # "Acoustic Guitar (Steel)" GM patch
    track.channel.volume = 127
    track.fretCount = MAX_FRET

    if not note_events:
        guitarpro.write(song, output_path)
        return

    # ---- Auto-detect rhythm feel: compound/triplet (12/8) or binary (4/4) --
    beat_dur_sec = 60.0 / bpm
    if force_feel is not None:
        feel = force_feel
    else:
        feel = _detect_feel(note_events, bpm)

    if feel == 'triplet':
        # 12/8: 12 eighth-note steps per measure; each step = 1/3 quarter beat
        steps_per_measure = 12
        step_sec          = beat_dur_sec / 3.0        # 8th-note step
        ticks_per_measure = 12 * (_QT // 2)           # 5760 ticks
        ts_num, ts_den    = 12, 8
        sdt               = _STEP_DUR_TABLE_12_8
        fallback_steps    = 1
        fallback_val      = 8                          # minimum = 8th note
        resonance_window  = 2 if resonance_window is None else resonance_window
        density_cap       = 13 if density_cap is None else density_cap
        chord_merge       = 0 if chord_merge        is None else chord_merge
        empty_rest_dur    = guitarpro.Duration(value=1, isDotted=True)  # dotted whole
    else:
        # 4/4 binary: 32 thirty-second-note steps per measure
        steps_per_measure = 32
        step_sec          = beat_dur_sec / 8.0         # 32nd-note step
        ticks_per_measure = 4 * _QT                    # 3840 ticks
        ts_num, ts_den    = 4, 4
        sdt               = _STEP_DUR_TABLE
        fallback_steps    = 2
        fallback_val      = 16                         # minimum = 16th note
        resonance_window  = 8 if resonance_window is None else resonance_window
        density_cap       = 14 if density_cap is None else density_cap
        chord_merge       = 1  if chord_merge        is None else chord_merge
        empty_rest_dur    = guitarpro.Duration(value=1)  # whole rest

    # ---- Quantize, suppress resonance, prune, cap per-measure density ----
    quantized_events = _quantize_events(note_events, step_sec, chord_merge)
    quantized_events = _suppress_resonance(quantized_events, resonance_window)
    if len(quantized_events) > 4:
        amps = sorted(ev[3] for ev in quantized_events)
        amp_cutoff = amps[int(len(amps) * 0.10)]  # drop only the weakest 10% (was 15%)
        quantized_events = [ev for ev in quantized_events if ev[3] >= amp_cutoff]

    capped: List[Tuple[int, int, int, float]] = []
    cur_m = -1
    measure_bucket: List[Tuple[int, int, int, float]] = []
    for ev in quantized_events:
        m = ev[0] // steps_per_measure
        if m != cur_m:
            if measure_bucket:
                if len(measure_bucket) > density_cap:
                    measure_bucket = sorted(
                        measure_bucket, key=lambda e: e[3], reverse=True
                    )[:density_cap]
                    measure_bucket.sort(key=lambda e: e[0])
                capped.extend(measure_bucket)
            measure_bucket = []
            cur_m = m
        measure_bucket.append(ev)
    if measure_bucket:
        if len(measure_bucket) > density_cap:
            measure_bucket = sorted(
                measure_bucket, key=lambda e: e[3], reverse=True
            )[:density_cap]
            measure_bucket.sort(key=lambda e: e[0])
        capped.extend(measure_bucket)
    quantized_events = capped

    if not quantized_events:
        guitarpro.write(song, output_path)
        return

    max_end_step = max(ev[1] for ev in quantized_events)
    num_measures = max(1, math.ceil(max_end_step / steps_per_measure))

    # ---- Build measure headers -------------------------------------------
    song.measureHeaders.clear()
    for i in range(num_measures):
        hdr = guitarpro.MeasureHeader(
            number=i + 1,
            start=_QT + i * ticks_per_measure,
        )
        hdr.timeSignature.numerator = ts_num
        hdr.timeSignature.denominator.value = ts_den
        song.measureHeaders.append(hdr)

    # ---- Build one empty measure per header on the track -----------------
    track.measures.clear()
    for hdr in song.measureHeaders:
        track.measures.append(guitarpro.Measure(track, hdr))

    # Keep engraving consistent: wrap every 3 bars across the whole score.
    _apply_bars_per_line(track, bars_per_line=3)

    # ---- Place notes into measures with rests ----------------------------
    grouped_by_start: Dict[int, List[Tuple[int, int, float]]] = defaultdict(list)
    for ev in quantized_events:
        start_step, end_step, midi_pitch, amplitude = ev[:4]
        grouped_by_start[start_step].append((midi_pitch, end_step, amplitude) + ev[4:])

    # Beat-1 snap: in PDF tabs fret digits are printed 15-60 px after each
    # barline (standard digit left-margin), causing them to quantise to step 1
    # or 2 instead of step 0.  Pull such notes back to beat 1 when step 0 is
    # vacant.
    if beat1_snap > 0:
        for m_idx in range(num_measures):
            m_start_s = m_idx * steps_per_measure
            if m_start_s not in grouped_by_start:
                for delta in range(1, beat1_snap + 1):
                    candidate = m_start_s + delta
                    if candidate in grouped_by_start:
                        grouped_by_start[m_start_s] = grouped_by_start.pop(candidate)
                        break

    for measure_idx, measure in enumerate(track.measures):
        voice = measure.voices[0]
        m_start = measure_idx * steps_per_measure
        m_end   = m_start + steps_per_measure

        active_steps = sorted(s for s in grouped_by_start if m_start <= s < m_end)

        current_step = m_start
        for step in active_steps:
            if step > current_step:
                _add_rests(voice, step - current_step, sdt)
                current_step = step

            next_candidates = [s for s in active_steps if s > step]
            next_step = next_candidates[0] if next_candidates else m_end

            group_end = min(m_end, max(ev[1] for ev in grouped_by_start[step]))
            desired_steps = max(1, min(group_end, next_step) - step)
            max_steps     = max(1, next_step - step)

            beat = guitarpro.Beat(voice, status=guitarpro.BeatStatus.normal)
            dur, actual_steps = _note_dur(
                desired_steps, max_steps, sdt, fallback_steps, fallback_val
            )
            beat.duration = dur

            # Check if we have explicit string/fret data (PDF mode)
            is_perfect = all(len(ev) >= 5 for ev in grouped_by_start[step])

            if is_perfect and grouped_by_start[step]:
                # PDF mode: strings/frets perfectly defined
                # ev is (midi, end_step, amp, string=si+1, fret)
                # Keep top 6 loudest/important if overlapping strings? No, PDF is already clean
                for ev in grouped_by_start[step]:
                    m_pitch, m_end, m_amp, s_num, s_fret = ev[:5]
                    note = guitarpro.Note(
                        beat,
                        string=s_num,
                        value=s_fret,
                        type=guitarpro.NoteType.normal,
                        velocity=guitarpro.Velocities.forte,
                    )
                    beat.notes.append(note)
            else:
                pitch_amp_pairs = [(ev[0], ev[2]) for ev in grouped_by_start[step]]
                midi_pitches = _select_notes_for_beat(pitch_amp_pairs)
                for _, string_num, fret in _map_chord_notes(midi_pitches):
                    note = guitarpro.Note(
                        beat,
                        string=string_num,
                        value=fret,
                        type=guitarpro.NoteType.normal,
                        velocity=guitarpro.Velocities.forte,
                    )
                    beat.notes.append(note)

            if beat.notes:
                voice.beats.append(beat)
            else:
                _add_rests(voice, actual_steps, sdt)
            current_step += actual_steps

        if current_step < m_end:
            _add_rests(voice, m_end - current_step, sdt)

    # Ensure every voice has at least one beat
    for measure in track.measures:
        for voice in measure.voices:
            if not voice.beats:
                rest = guitarpro.Beat(voice, status=guitarpro.BeatStatus.rest)
                rest.duration = empty_rest_dur
                voice.beats.append(rest)

    guitarpro.write(song, output_path)

