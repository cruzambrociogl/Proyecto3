# Conventions

## Code (`phy-chat/`)

- Python 3, **standard library only**, so the same code runs on the laptop and on the BBB without installing anything.
- Keep the layering of `claude/analysis.md`: the link never knows about channels, and the PHY never knows about frames.
- A new coding is selected with `--coding` in `node.py`; old codings stay available for comparison (`plain`, `fec`).
- Every protocol rule gets a unit test in `phy-chat/tests/`. Use seeded random generators so failures repeat.
- Math that the protocol depends on must match `docs/experiments/` (the verified scripts). If the code and the script disagree, the script's verified table wins until the spec changes.
- User-facing text in the web UI is Spanish (the UI is shown in the defense). Code, comments and identifiers are English.

## Docs

- English by default. A Spanish file is a translation of an English original (`protocol.md` → `protocolo.md`, `matrix_v6b.csv` → `matrix_v6b_es.csv`). Update the English one first.
- In Spanish versions, keep technical terms in English: tick, frame, CLK, XOR, CRC-8, ACK/NACK, script, buffer, FIFO.
- Explanations for Cruz: simple words, step by step, ASCII diagrams, the 'h' (`0x68`) example.
- Mark unconfirmed details "(proposed)".
- Design changes get a new dated section in `docs/design-log.md`; never rewrite the history sections.

## CSVs for the professor

- Data only, no styling. Each table: a title line, a header row, data rows, and a one-line explanation.
- Excel-safe: write bit groups with spaces (`0 0 1 1`, otherwise Excel shows `11`); avoid `320/320` (can become a date); no cell may start with `=`, `+`, `-` or `@`; avoid commas in text cells.
- Spanish CSV saved as UTF-8 with BOM so Excel shows accents. If Cruz's Excel puts everything in column A, switch the separator to `;`.
- Check after writing: parse with Python's `csv` module and scan for formula-like cells.

## Experiments (`docs/experiments/`)

- Stdlib Python, runnable from `PROJECT03/` as `python3 docs/experiments/<name>.py`.
- The docstring says what is tested and how to run it; the output prints the result table that goes into the docs.
- Brute force over every case when possible; otherwise a seeded random generator with the trial count printed.
