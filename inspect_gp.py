"""Inspect the latest GP5 output file and export its events for analysis."""
import guitarpro
import glob, os
from collections import Counter

outputs = sorted(glob.glob(r'd:\Projects\MusicToGP\backend\output\*.gp5'), key=os.path.getmtime)
print(f"Files: {[os.path.basename(f) for f in outputs[-3:]]}\n")

latest = outputs[-1]
song = guitarpro.parse(latest)

note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
def pitch_name(p):
    return f"{note_names[p%12]}{p//12-1}({p})"

print(f"=== {os.path.basename(latest)} ===")
print(f"BPM: {song.tempo}")
print(f"Tracks: {len(song.tracks)}")

total_beats = 0
note_beats = 0
rest_beats = 0
chord_sizes = []
pitches_seen = []
durations_seen = []
beat_notes_per_measure = []

for track in song.tracks:
    for measure in track.measures:
        for voice in measure.voices:
            beats_in_measure = 0
            notes_in_measure = 0
            for beat in voice.beats:
                total_beats += 1
                dur_val = beat.duration.value
                durations_seen.append(dur_val)
                if beat.status == guitarpro.BeatStatus.rest or not beat.notes:
                    rest_beats += 1
                else:
                    note_beats += 1
                    beats_in_measure += 1
                    chord_sizes.append(len(beat.notes))
                    for n in beat.notes:
                        # string/fret -> midi pitch
                        string_open = {1:64, 2:59, 3:55, 4:50, 5:45, 6:40}
                        midi = string_open[n.string] + n.value
                        pitches_seen.append(midi)

print(f"Total beats: {total_beats}, Note beats: {note_beats}, Rest beats: {rest_beats}")
print(f"Chord size dist: {dict(Counter(chord_sizes))}")
print(f"Duration dist: {dict(Counter(durations_seen))}")
pc = Counter(pitches_seen)
print(f"Top pitches: {[(pitch_name(p),c) for p,c in pc.most_common(10)]}")
print(f"Pitch range: {pitch_name(min(pitches_seen))} - {pitch_name(max(pitches_seen))}" if pitches_seen else "No notes")
print(f"Total note events: {sum(chord_sizes)}")
