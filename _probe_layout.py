import guitarpro
from backend.services.gp_converter import convert_to_gp
out = r"D:\Projects\MusicToGP\backend\output\_layout_probe.gp5"
ev = []
bpm = 120.0
beat = 60.0 / bpm
for m in range(9):
    for b in range(4):
        t = (m * 4 + b) * beat
        ev.append((t, t + 0.2, 64, 0.9))
convert_to_gp(
    ev,
    "layout_probe",
    out,
    bpm=bpm,
    force_feel="straight",
    resonance_window=0,
    chord_merge=0,
    density_cap=200,
    beat1_snap=0,
)
s = guitarpro.parse(out)
print([m.lineBreak.value for m in s.tracks[0].measures])
