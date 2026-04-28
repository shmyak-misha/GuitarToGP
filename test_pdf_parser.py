import sys
sys.path.insert(0, r'd:\Projects\MusicToGP\backend')

from services.pdf_parser import _group_tab_systems, _find_bpm, _parse_system
print('All imports OK')

sample_text = """Mr. Lonely - fingerstyle
Tempo = 120

e|--0---3--5---3--0--|--0---1-----|
B|--1---3--5---3--1--|--1---1-----|
G|--0---2--4---2--0--|--0---2-----|
D|--2---3--5---3--2--|--2---3-----|
A|--3---1--3---1--3--|--0---1-----|
E|-------------------|------------|
"""

bpm = _find_bpm(sample_text)
print(f"BPM detected: {bpm}")

lines = sample_text.splitlines()
systems = _group_tab_systems(lines)
print(f"Tab systems found: {len(systems)}")

if systems:
    print(f"First system has {len(systems[0])} strings")
    for label, content in systems[0]:
        print(f"  {label}: {content[:40]}")
    events, end_t = _parse_system(systems[0], 0.0, bpm)
    print(f"Events generated: {len(events)}")
    NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    for i, (s, e, p, a) in enumerate(events[:8]):
        print(f"  [{i}] t={s:.3f}s  pitch={p} ({NOTE_NAMES[p%12]}{p//12-1})  amp={a:.2f}")
