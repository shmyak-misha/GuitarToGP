import sys, io
sys.path.insert(0, 'D:/Projects/MusicToGP/backend')
_log = open('D:/Projects/MusicToGP/regen_out.txt', 'w')
sys.stdout = sys.stderr = _log
from services.pdf_parser import parse_pdf_tab
from services.gp_converter import convert_to_gp
from pathlib import Path
import guitarpro

events, bpm = parse_pdf_tab(Path(r'C:\Users\shnai\Downloads\Mr Lonely.pdf'))
out = r'D:/Projects/MusicToGP/backend/output/test_v20.gp5'
convert_to_gp(events, 'Mr Lonely', out, bpm=bpm, force_feel='straight',
              resonance_window=0, chord_merge=0, density_cap=32, beat1_snap=4)
print(f"Written: {out}")

# Inspect bar 1 to confirm fix
song = guitarpro.parse(out)
track = song.tracks[0]
print("\n=== Bar 1 notes (GP file) ===")
for beat in track.measures[0].voices[0].beats:
    if beat.notes:
        for n in beat.notes:
            print(f"  string={n.string}  fret={n.value}")

print("\n=== Bar 11 notes (GP file) ===")
for beat in track.measures[10].voices[0].beats:
    if beat.notes:
        for n in beat.notes:
            print(f"  string={n.string}  fret={n.value}")
        print("  ---")

_log.flush()
_log.close()
