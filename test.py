import sys
sys.path.insert(0, 'backend')
from services.pdf_parser import parse_pdf_tab

events, bpm = parse_pdf_tab(r'C:\Users\shnai\Downloads\Mr Lonely.pdf')

bars = {}
for e in events:
    b = int(e[0]//2)+1
    bars.setdefault(b, []).append((e[1], e[2]))

midi_to_strfret = {}
for s, strm in {0:64,1:59,2:55,3:50,4:45,5:40}.items():
    for f in range(25):
        midi_to_strfret[strm+f] = (s+1, f)

for b in [1, 5, 8]:
    if b not in bars: continue
    print(f'\nBar {b}: {len(bars[b])} notes')
    for pos, midi in sorted(bars[b]):
        st, fr = midi_to_strfret.get(midi, ('?', '?'))
        print(f'  pos={pos:.2f}  str={st} fr={fr} (midi={midi})')

found_3_2 = sum(1 for e in events if midi_to_strfret.get(e[2]) == (3,2))
found_4_3 = sum(1 for e in events if midi_to_strfret.get(e[2]) == (4,3))
print(f'\nOverall: (3,2)x{found_3_2}   (4,3)x{found_4_3}')
