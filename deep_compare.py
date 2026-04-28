"""
Deep note-by-note comparison between reference MIDI and latest GP5 output.
Converts everything to a common time grid (seconds) and compares pitch sequences.
"""
import mido, guitarpro, glob, os
from collections import Counter

REF_PATH = r'c:\Users\shnai\OneDrive\Documents\Mr Lonely Vinton.mid'
outputs = sorted(glob.glob(r'd:\Projects\MusicToGP\backend\output\*.gp5'), key=os.path.getmtime)
GP_PATH = outputs[-1]

note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
def pn(p): return f"{note_names[p%12]}{p//12-1}({p})"

# ── Extract reference note sequence ─────────────────────────────────────────
mid = mido.MidiFile(REF_PATH)
tpb = mid.ticks_per_beat    # 480
tempo = 500000
for t in mid.tracks:
    for m in t:
        if m.type == 'set_tempo':
            tempo = m.tempo; break

def ticks_to_sec(ticks): return ticks * tempo / 1_000_000 / tpb

ref_events = []   # (time_sec, pitches_sorted)
cur_tick = None; cur_notes = []
for t in mid.tracks:
    abs_tick = 0
    for m in t:
        abs_tick += m.time
        if m.type == 'note_on' and m.velocity > 0:
            if cur_tick is not None and abs_tick != cur_tick:
                ref_events.append((ticks_to_sec(cur_tick), sorted(cur_notes)))
                cur_notes = []
            cur_notes.append(m.note)
            cur_tick = abs_tick
if cur_notes:
    ref_events.append((ticks_to_sec(cur_tick), sorted(cur_notes)))
ref_events.sort(key=lambda x: x[0])

# ── Extract GP5 note sequence ────────────────────────────────────────────────
song = guitarpro.parse(GP_PATH)
gp_bpm = song.tempo
beat_sec = 60.0 / gp_bpm
_QT = guitarpro.Duration.quarterTime  # 960

STRING_OPEN = {1:64, 2:59, 3:55, 4:50, 5:45, 6:40}

def dur_to_beats(dur):
    base = 4.0 / dur.value
    if dur.isDotted: base *= 1.5
    return base

gp_events = []  # (time_sec, pitches_sorted)
for track in song.tracks:
    for mi, measure in enumerate(track.measures):
        measure_start_beat = mi * 4.0
        for voice in measure.voices:
            beat_pos = 0.0
            for beat in voice.beats:
                beats = dur_to_beats(beat.duration)
                if beat.status != guitarpro.BeatStatus.rest and beat.notes:
                    t_sec = (measure_start_beat + beat_pos) * beat_sec
                    pitches = sorted(STRING_OPEN[n.string] + n.value for n in beat.notes)
                    gp_events.append((t_sec, pitches))
                beat_pos += beats

gp_events.sort(key=lambda x: x[0])

print(f"Reference: {len(ref_events)} events")
print(f"GP output: {len(gp_events)} events  (BPM={gp_bpm})")
print()

# ── Side-by-side: align by index and compare ─────────────────────────────────
print("=== SIDE BY SIDE (first 60 events) ===")
print(f"{'IDX':>4}  {'REF_T':>7}  {'REF_NOTES':<30}  {'GP_T':>7}  {'GP_NOTES'}")
max_idx = max(len(ref_events), len(gp_events))
mismatches = 0
for i in range(min(60, max_idx)):
    rt, rn = ref_events[i] if i < len(ref_events) else (None, [])
    gt, gn = gp_events[i] if i < len(gp_events) else (None, [])
    rs = ' '.join(pn(p) for p in rn) if rn else '—'
    gs = ' '.join(pn(p) for p in gn) if gn else '—'
    match = 'OK' if rn == gn else 'XX'
    if rn != gn: mismatches += 1
    rt_s = f"{rt:.2f}s" if rt is not None else "—"
    gt_s = f"{gt:.2f}s" if gt is not None else "—"
    print(f"{i:>4}  {rt_s:>7}  {rs:<30}  {gt_s:>7}  {gs}  {match}")

print()

# ── Pitch coverage comparison ────────────────────────────────────────────────
ref_all = [p for _, ps in ref_events for p in ps]
gp_all  = [p for _, ps in gp_events  for p in ps]
ref_pc = Counter(ref_all)
gp_pc  = Counter(gp_all)
all_pitches = sorted(set(ref_all) | set(gp_all))
print("=== PITCH COVERAGE ===")
print(f"{'PITCH':<15} {'REF_COUNT':>10} {'GP_COUNT':>10} {'DIFF':>8}")
for p in all_pitches:
    rc = ref_pc.get(p, 0)
    gc = gp_pc.get(p, 0)
    diff = gc - rc
    flag = ' <<<' if abs(diff) > 5 else ''
    print(f"{pn(p):<15} {rc:>10} {gc:>10} {diff:>+8}{flag}")

print()
ref_gaps = [ref_events[i+1][0]-ref_events[i][0] for i in range(len(ref_events)-1)]
gp_gaps  = [gp_events[i+1][0]-gp_events[i][0]  for i in range(len(gp_events)-1)]
print(f"Ref avg gap: {sum(ref_gaps)/len(ref_gaps):.3f}s   GP avg gap: {sum(gp_gaps)/len(gp_gaps):.3f}s")
print(f"Ref gap histogram (s): {Counter(round(g,2) for g in ref_gaps).most_common(6)}")
print(f"GP  gap histogram (s): {Counter(round(g,2) for g in gp_gaps).most_common(6)}")
