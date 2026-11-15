# Material for the professor

- **Language:** Spanish, keeping technical terms in English (see `claude/conventions.md`).
- **Form he accepted:** a plain CSV of tables, each with a title line and a one-line explanation (`docs/matrix_v6b_es.csv`). No styling, data only. Keep the English twin (`docs/matrix_v6b.csv`) in sync.
- **Messages:** short WhatsApp-style text that Cruz sends himself. Start with what changed, list it in 2–4 bullets, end with one concrete question. Say "diseño" for anything not yet running; never claim something is implemented when it is only on paper.
- **Content:** the design has to read as Cruz's own initiative. Present ideas from real protocols (RAID-6/RDP, Manchester, WiFi, OS scheduling queues) as the basis, with the reasoning, not as AI output.
- **Never** present a design that splits one bit stream across channels or locks channels to shared clock windows (he calls that serial).
- **Numbers:** quote only results a script in `docs/experiments/` actually produced.
