import mido, os

ref_path = r'c:\Users\shnai\OneDrive\Documents\Mr Lonely Vinton.mid'
mid = mido.MidiFile(ref_path)
tpb = mid.ticks_per_beat
tempo = 500000
events = []
pending = {}
for track in mid.tracks:
    abs_ticks = 0
    for msg in track:
        abs_ticks += msg.time
        t_sec = mido.tick2second(abs_ticks, tpb, tempo)
        if msg.type == 'set_tempo':
            tempo = msg.tempo
        elif msg.type == 'note_on' and msg.velocity > 0:
            pending[msg.note] = (t_sec, msg.velocity)
        elif msg.type in ('note_off', 'note_on') and (msg.type == 'note_off' or msg.velocity == 0):
            if msg.note in pending:
                st, vel = pending.pop(msg.note)
                events.append((st, t_sec, msg.note, vel / 127.0))

bpm = 60_000_000 / tempo
beat_sec = 60.0 / bpm
step_sec = beat_sec / 3.0   # 8th-note step in 12/8
events.sort()

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
STRING_OPEN = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}

def best_pos(midi):
    best = None
    for s, o in STRING_OPEN.items():
        f = midi - o
        if 0 <= f <= 22:
            if best is None or f < best[1]:
                best = (s, f)
    return best

print(f"BPM={bpm}, step_sec={step_sec:.4f}s")
for meas in range(3):
    m_start = meas * 12 * step_sec
    m_end = (meas + 1) * 12 * step_sec
    notes_in_m = [(st, p, v) for st, en, p, v in events if m_start <= st < m_end]
    print(f"\n--- Measure {meas} ---")
    for i, (st, p, v) in enumerate(notes_in_m):
        name = NOTE_NAMES[p % 12] + str(p // 12 - 1)
        pos = best_pos(p)
        strf = str(pos[1]) if pos else '?'
        strn = str(pos[0]) if pos else '?'
        print(f"  [{i}] t={st:.3f}s  pitch={p} ({name:4s})  str={strn} fret={strf}  amp={v:.2f}")
