# User Requests Log — MusicToGP

All user requests recorded from the development chat sessions.

---

## Session 1 (early development)

1. Build a web-based tool that converts YouTube videos into Guitar Pro (`.gp5`) tablature files.
2. Add a job-queue model with `pending → processing → completed | failed` status tracking.
3. Serve the frontend statically from `/` and all API routes under `/api/`.
4. Download audio with `yt-dlp`, run pitch detection with `basic-pitch`, and generate `.gp5` via `PyGuitarPro`.
5. Sanitise filenames derived from video titles before writing to disk.
6. Delete temp audio files immediately after the GP file is written.
7. Return structured JSON error responses from the API (never raw tracebacks).

---

## Session 2 (PDF parser + OCR)

8. Add a PDF tab parser (`pdf_parser.py`) that reads rasterised guitar tab PDFs and extracts note events.
9. Support OCR-based digit recognition per string cluster using Tesseract.
10. Detect BPM from the PDF (e.g. "♩ = 120") and fall back to 120 BPM.
11. Parse `Mr Lonely.pdf` (22 bars, 120 BPM) and generate a `.gp5` file from it.
12. Add a `/api/pdf-convert` endpoint and frontend UI for PDF upload and download.

---

## Session 3 (string/fret bug fixes)

13. Fix the `_quantize_events` function in `gp_converter.py` — it was discarding `ev[4:]` (string/fret), causing all strings to default to string 1.
14. Fix line 451 in `gp_converter.py` — `max_end_step` used 4-tuple destructuring on 6-tuple events.
15. Fix line 418 in `gp_converter.py` — `amps` calculation used 4-tuple destructuring on 6-tuple events.
16. Verify the fix: confirm that bar 1 of the generated `.gp5` now shows `string=3 fret=4` instead of defaulting to string 1.

---

## Session 4 (version + OCR improvements)

17. Add a dynamic version number: expose `/api/version` endpoint from the backend; fetch it in the frontend so it updates automatically when server-side changes are made (instead of a hardcoded string).
18. Increase the version number every time changes are made on the server side or GUI.
19. Improve OCR accuracy:
    - Use Tesseract digit whitelist (`tessedit_char_whitelist=0123456789`).
    - Lower binarisation threshold from 155 → 128.
    - Lower `dk` (dark-pixel) threshold from 5 → 3 to catch faint digits.
20. Add a song-specific correction map in `parse_pdf_tab` for the "Mr Lonely" PDF to deterministically fix OCR errors in bars 11, 17, 18, 22.

---

## Session 5 (correction map — bars 16–22)

21. Proceed with a full deterministic correction map for bars 16–22 in one pass (replacing OCR output for those bars entirely with reference data).
22. Also fix bar 1 in the correction map — phantom `fret=4 string=3` note that does not exist in the original PDF.
23. List all user requests from the chat in a separate file (`USER_REQUESTS.md`). ← **this file**

---

## Session 6 (visual comparison — 4 specific issues, 2026-04-27)

24. **Bar 1 phantom note**: The GP output shows `string=3 fret=4` at the very first position of bar 1, but this note does not exist in the original PDF. Fix: add bar 1 to the correction map with the correct reference data (`[[2,1],[5,3]]` at beat 0) and remove the erroneous guard code that was *adding* the phantom note.
25. **Bar 16 missing notes**: Visual comparison of PDF vs GP shows notes/tabs missing in bar 16 of the GP output. Ensure the correction map replacement for bar 16 is complete and the old OCR events are fully discarded.
26. **"Note 3" wrongly scanned**: A note (identified visually as the third distinct note position) in bars around 19–20 is incorrectly OCR'd, producing wrong string/fret in the GP output. Fix the correction map entry for the affected position.
27. **Bar 21 last note wrong**: The last note(s) of bar 21 are missing or have wrong tabs in the GP output compared to the PDF. Ensure the correction map for bar 21 includes the correct last two positions (`pos=4.0 → [[2,0]]`, `pos=4.5 → [[4,3]]`).

---

## Session 7 (follow-up fixes and UI updates, 2026-04-27)

28. **Issue 3 correction detail**: In the 3rd position, set `fret 3 string 2 + fret 4 string 3 + fret 3 string 4 + fret 3 string 6`.
29. Confirm whether the separate requests file was created and contains the user requests.
30. Fix app header where version number was not visible (`I can't see the version # on the app`).
31. Re-check bar 16 mismatch from PDF vs GP and ensure missing tabs are corrected.
32. Fix remaining bar 16 OCR mismatch where PDF shows 10 note positions vs 8 in GP.
33. **YouTube tab enhancement**: After a YouTube URL is added, show a preview frame from that URL.
34. Make the YouTube preview frame fit the app width.
35. Ensure all user requests are added to this requests list file.
36. Clarify whether scan quality improves if all YouTube URLs are fingerpicking on a single acoustic/classical guitar.
37. Apply that recommendation in the app (UI messaging + behavior) accordingly.

---

## Session 8 (workflow requirements, 2026-04-29)

38. After each requested change is completed, explicitly confirm it is finished and provide clear testing steps.
39. Update USER_REQUESTS.md every time a new user request is submitted.
40. Only add actual requests to USER_REQUESTS.md — do not log questions.
