import mido, os, glob
from collections import Counter

def extract_note_groups(path):
    mid = mido.MidiFile(path)
    tpb = mid.ticks_per_beat
    tempo = 500000
    for t in mid.tracks:
        for m in t:
            if m.type == 'set_tempo':
                tempo = m.tempo
                break
    bpm = 60_000_000 / tempo
    groups = []
    cur_time = None
    cur_notes = []
    for t in mid.tracks:
        abs_time = 0
        for m in t:
            abs_time += m.time
            if m.type == 'note_on' and m.velocity > 0:
                if cur_time is not None and abs_time != cur_time:
                    groups.append((cur_time, sorted(cur_notes)))
                    cur_notes = []
                cur_notes.append(m.note)
                cur_time = abs_time
    if cur_notes:
        groups.append((cur_time, sorted(cur_notes)))
    groups.sort(key=lambda x: x[0])
    return bpm, tpb, groups

note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def pitch_name(p):
    return f"{note_names[p%12]}{p//12-1}({p})"

ref = extract_note_groups(r'c:\Users\shnai\OneDrive\Documents\Mr Lonely Vinton.mid')
our = extract_note_groups(r'd:\Projects\MusicToGP\our_output.mid')

# Also check latest GP output converted back via the GP file MIDI
outputs = sorted(glob.glob(r'd:\Projects\MusicToGP\backend\output\*.gp5'), key=os.path.getmtime)
print(f"Latest GP outputs: {[os.path.basename(f) for f in outputs[-3:]]}\n")

for label, (bpm, tpb, groups) in [('REFERENCE', ref), ('OUR_OUTPUT.MID (old)', our)]:
    print(f'=== {label} ===')
    print(f'  BPM={bpm:.1f}  TPB={tpb}  Groups={len(groups)}')
    gaps = [groups[i+1][0]-groups[i][0] for i in range(len(groups)-1)]
    gc = Counter(gaps)
    print(f'  Gap histogram (ticks): {gc.most_common(8)}')
    # Normalize gaps to fractions of a beat
    beat_fracs = Counter()
    for gap, cnt in gc.items():
        frac = gap / tpb
        beat_fracs[round(frac, 3)] += cnt
    print(f'  Gap histogram (beats): {beat_fracs.most_common(8)}')
    print(f'  Polyphony: {dict(Counter(len(g[1]) for g in groups))}')
    all_p = [n for _,ns in groups for n in ns]
    pc = Counter(all_p)
    print(f'  Top pitches: {[(pitch_name(p),c) for p,c in pc.most_common(10)]}')
    print(f'  Pitch range: {min(all_p)} - {max(all_p)} ({pitch_name(min(all_p))} - {pitch_name(max(all_p))})')
    print()
