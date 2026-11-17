# PROJECT03 — Non-Conventional Physical Layer

| Folder / file | Content |
|---|---|
| `Proyecto_-_Capa_Fisica_.pdf` | the assignment |
| `docs/protocol.md` | full specification of the accepted protocol (v6b) |
| `docs/protocolo.md` | Spanish translation of `protocol.md` |
| `docs/protocol-document.md` / `.pdf` | the submission document: protocol, physical implementation, demo, decisions, results (English original) |
| `docs/documento-protocolo.md` / `.pdf` | Spanish translation of the submission document |
| `docs/build_pdf.py` | markdown → PDF with headless Chrome: `python3 docs/build_pdf.py [file.md]` |
| `docs/design-log.md` | design history, professor feedback, decisions, hardware, open questions |
| `docs/matrix_v6b_es.csv`, `docs/matrix_v6b.csv` | the tables shown to the professor (Spanish / English) |
| `docs/diseno_canales.xlsx` | v2 design workbook (older) |
| `docs/experiments/` | scripts that verify the math (Python, stdlib only); run from this folder, e.g. `python3 docs/experiments/matrix_nibble.py` |
| `CLAUDE.md`, `claude/` | context for Claude Code: overview, rules, status tracker, decision log, code map, conventions, instructions |
| `phy-chat/` | the implementation: code, tests and run scripts (see `phy-chat/README.md`) |

Documentation, notes and decisions go in `docs/`, in English. `phy-chat/` holds only the implementation.
