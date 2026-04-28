"""
Full structural comparison: app output vs reference.
Prints measure-by-measure note sequences for both.
"""
import mido
from collections import Counter

APP_PATH = r'c:\Users\shnai\OneDrive\Documents\Mr Lonely MusicToGP.mid'
REF_PATH = r'c:\Users\shnai\OneDrive\Documents\Mr Lonely Vinton.mid'

note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
def pn(p): return f"{note_names[p%12]}{p//12-1}({p})"

def load_midi(path):
    mid = mido.MidiFile(path)
    tpb = mid.ticks_per_beat
    tempo = 500000
    for t in mid.tracks:
        for m in t:
            if m.type == 'set_tempo':
                tempo = m.tempo; break
    bpm = 60_000_000 / tempo

    # Build (abs_tick, [pitches]) groups
    events = []
    cur_tick = None; cur_notes = []
    for t in mid.tracks:
        abs_tick = 0
        for m in t:
            abs_tick += m.time
            if m.type == 'note_on' and m.velocity > 0:
                if cur_tick is not None and abs_tick != cur_tick:
                    events.append((cur_tick, sorted(cur_notes)))
                    cur_notes = []
                cur_notes.append(m.note)
                cur_tick = abs_tick
    if cur_notes:
        events.append((cur_tick, sorted(cur_notes)))
    events.sort(key=lambda x: x[0])
    return bpm, tpb, tempo, events

app_bpm, app_tpb, app_tempo, app_ev = load_midi(APP_PATH)
ref_bpm, ref_tpb, ref_tempo, ref_ev = load_midi(REF_PATH)

print(f"APP: BPM={app_bpm:.1f}  TPB={app_tpb}  Events={len(app_ev)}")
print(f"REF: BPM={ref_bpm:.1f}  TPB={ref_tpb}  Events={len(ref_ev)}")
print()

# Split into measures (4/4)
def to_measures(events, tpb, tempo):
    ticks_per_measure = tpb * 4
    measures = {}
    for tick, pitches in events:
        m = tick // ticks_per_measure
        pos = tick % ticks_per_measure
        # position as fraction of measure (0.0 - 1.0)
        frac = pos / ticks_per_measure
        measures.setdefault(m, []).append((frac, pitches))
    return measures

app_m = to_measures(app_ev, app_tpb, app_tempo)
ref_m = to_measures(ref_ev, ref_tpb, ref_tempo)

all_measures = sorted(set(app_m) | set(ref_m))
print(f"{'M':>3}  {'REF events':>10}  {'APP events':>10}  {'REF notes':>3}  {'APP notes':>3}  STATUS")
print("-" * 90)
for m in all_measures:
    re = ref_m.get(m, [])
    ae = app_m.get(m, [])
    rn = sum(len(p) for _, p in re)
    an = sum(len(p) for _, p in ae)
    status = "OK" if len(re) == len(ae) else f"{'EXTRA' if len(ae)>len(re) else 'MISSING'} {abs(len(ae)-len(re))}"
    print(f"{m:>3}  {len(re):>10}  {len(ae):>10}  {rn:>9}  {an:>9}  {status}")

print()
# Detailed breakdown for first 8 measures
print("=== DETAILED MEASURE COMPARISON (first 10 measures) ===")
for m in sorted(all_measures)[:10]:
    re = ref_m.get(m, [])
    ae = app_m.get(m, [])
    print(f"\nMeasure {m}:")
    max_len = max(len(re), len(ae))
    for i in range(max_len):
        rf = f"  {re[i][0]:.3f} {' '.join(pn(p) for p in re[i][1])}" if i < len(re) else "  ---"
        af = f"  {ae[i][0]:.3f} {' '.join(pn(p) for p in ae[i][1])}" if i < len(ae) else "  ---"
        flag = "" if (i < len(re) and i < len(ae) and re[i][1] == ae[i][1]) else " <<<"
        print(f"  REF:{rf:<35}  APP:{af}{flag}")
