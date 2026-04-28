from backend.services.gp_converter import _select_notes_for_beat, convert_to_gp
import mido

# Test chord dedup fix
r1 = _select_notes_for_beat([(48, 0.60), (60, 0.60)])
print("C3+C4 equal amp:", r1, "(expect [48, 60])")

r2 = _select_notes_for_beat([(48, 0.60), (60, 0.20)])
print("C3 strong + C4 harmonic:", r2, "(expect [48])")

# Load reference MIDI
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
events.sort()

out = r'd:\Projects\MusicToGP\backend\output\ref_converted2.gp5'
convert_to_gp(events, 'Mr Lonely Ref v2', out, bpm=bpm)

import guitarpro
song = guitarpro.parse(out)
track = song.tracks[0]
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
STRING_OPEN = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}

print()
print(f"Measures: {len(song.measureHeaders)}, TS: {song.measureHeaders[0].timeSignature.numerator}/{song.measureHeaders[0].timeSignature.denominator.value}")
for mi in range(3):
    meas = track.measures[mi]
    beats = [b for b in meas.voices[0].beats if b.status.name == 'normal']
    print(f"\nMeasure {mi+1}: {len(beats)} note-beats")
    for i, b in enumerate(beats):
        parts = []
        for n in b.notes:
            midi = STRING_OPEN[n.string] + n.value
            nm = NOTE_NAMES[midi % 12] + str(midi // 12 - 1)
            parts.append(nm + "(str" + str(n.string) + "/fr" + str(n.value) + ")")
        print("  [" + str(i) + "] " + " + ".join(parts))
