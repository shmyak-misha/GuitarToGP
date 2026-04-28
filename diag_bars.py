import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from services.pdf_parser import parse_pdf_tab
from pathlib import Path

events, bpm = parse_pdf_tab(Path(r'C:\Users\shnai\Downloads\Mr Lonely.pdf'))

# NoteEvent = (start_sec, end_sec, midi, amplitude, string_1based, fret)
bar_sec = 4 * 60 / bpm
bars = {}
for e in events:
    b = int(e[0] / bar_sec) + 1
    bars.setdefault(b, []).append(e)

print(f"BPM={bpm}, bar_sec={bar_sec:.3f}s, total_events={len(events)}")
print(f"Sample event[0]: {events[0] if events else 'NONE'}")
print(f"Fields per event: {len(events[0]) if events else 0}")
for bn in [1, 11, 16, 17, 18, 19, 20, 21, 22]:
    print(f"\n--- Bar {bn} ---")
    for e in sorted(bars.get(bn, []), key=lambda x: x[0]):
        # Try both 4-tuple and 6-tuple formats
        if len(e) >= 6:
            print(f"  t={e[0]:.3f}  midi={e[2]}  string={e[4]}  fret={e[5]}")
        else:
            print(f"  t={e[0]:.3f}  midi={e[2]}  (no string/fret)")
