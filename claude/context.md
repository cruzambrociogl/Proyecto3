# Context: assignment, professor, design history

The full quoted record is `docs/design-log.md`. This file is the short version a session needs before touching the design.

## People

- **Team:** Rosangela Rodriguez (22000127) and Cruz Ambrocio (20005588); both names go on every submitted document.
- **Cruz** — owns the project and does the hardware. He prefers explanations in simple words, step by step, with ASCII diagrams and a worked example (the letter 'h' = `0x68`). He shows proposals to the professor and relays the feedback, often as WhatsApp messages or voice transcripts.
- **The professor** — grades only the in-person defense. He wants the design initiative to come from the student and treats AI as a support tool, not a substitute. Write material for him in Spanish, short and to the point.

## The assignment (from the PDF)

- Two boards, bidirectional web chat.
- 3–8 physical channels per direction, one of them the clock.
- At least 3 different non-conventional media, each ending as a GPIO 0/1.
- Frame `SYN → SFD → CTRL (4) → DATA (8) → CRC-8 → [optional]`.
- Selectable CRC-8 variants: SMBUS, AUTOSAR, SAE-J1850, MAXIM-DOW.
- Encodings: UTF-8 (1–4 bytes) and Extended ASCII.
- ACK/NACK with retransmission, and a LOG.
- A live demo: interference → CRC → NACK → retransmission.
- Delivery: a ZIP with code and docs, including the wiring for each medium.

## The professor's rules (accumulated)

| Rule | Source |
|---|---|
| The CLK is never interfered. Any number of data channels can be at once: hand (all 0), IR pointer (all 1), noise, and fast flicker that can look valid. | 2026-11-05 |
| Recovery by a mathematical equation (FEC), not majority vote, not only retransmission. | 2026-11-04 |
| **Not serial.** It must be a hybrid of parallel and serial processing, or there is no grade. | email 2026-11-11 |
| The frame in the PDF is the bit structure, not the PHY protocol. CRC validates after the frame; the protocol must also validate bits *during* transmission. | email 2026-11-11 |
| Base case from class: "validación de canales y recuperación de bits mediante matrices" (Cruz recalls it as XOR with horizontal and vertical validation). Start at 1 Hz, configurable up to a computed maximum. LOG at 1 Hz "porque somos humanos". | email 2026-11-11 |
| Queues with priorities, "como CC7" (operating systems): ready queue, waiting list, priority. | WhatsApp 2026-11-12 |
| The whole evaluation runs at 1 Hz; no high speeds. | WhatsApp 2026-11-12 |
| Block retransmission (another team's idea) is optional, only if needed. | recording 2026-11-04 |
| Use ideas from real protocols; truth tables in Excel. | recording 2026-11-04 |

## What "serial" meant to him (so we don't repeat it)

He rejected these designs as serial:

1. The frame as one bit stream chopped onto lanes (v1, v2): each lane carries different bits of the same stream.
2. D0 and D1 carrying two different bits each tick (v2, v3).
3. Every channel locked to the CLK's windows (v4), even when each window carried a frequency value.
4. "AI proposes serial solutions that only look parallel" (email). Every Claude proposal before v6 converged to serial. Watch for this.

What he accepted (v6b): a matrix where **rows are ticks (serial)** and **columns are channels sent at the same time (parallel)**. Every channel carries the whole half byte in a different XOR mix, and validation runs horizontally (every tick), diagonally (tick to tick) and vertically (per channel). More channels alive means the data is known sooner.

## Design iterations

| Version | Idea | Outcome |
|---|---|---|
| v1 | plain level per lane | built; serial |
| v2 | Manchester symbol (invalid = erasure) + XOR parity lane | **built (current code)**; serial, only horizontal validation |
| v2b / v2c | WiFi-style fallback / 5-light [5,2,3] code | paper |
| v3 | GF(16) RAID-6 P+Q | verified; on hold (still splits data across lanes) |
| v4 | blink-count FSK + line code mod 5 | rejected: serial, locked to the CLK |
| v5 | independent channel frequencies | dropped after the email (we over-read "frequency carries information"; he meant the tick rate) |
| v6 | 1 byte per 5×4 matrix, RDP-style checks | verified; survives 2 dead channels |
| **v6b** | 1 half byte per 5×4 matrix, every channel carries all 4 bits | **accepted 2026-11-14**; survives until 1 channel is left |

## Hardware state (2026-11-14)

- Boards: two BeagleBone Black planned, one on hand. Arduino Mega, 2× MCP23017 and a logic analyzer are also available.
- Media parts: 2 KY-008 lasers, 4 DL-591 (IR receivers, confirmed 2026-11-15), 2 IR LED emitters, 2 KY-038 microphones, 2 buzzers (active or passive unknown).
- That makes 3 channels per direction; the design needs 5. Details, shopping list and circuit rules are in `docs/design-log.md` §22.
- Media (2026-11-16): laser, IR, sound, Hall, light (placeholder), one per channel. Proposed: CLK laser, D0 IR, D1 sound, P Hall, Q light. Pins on P8 only, same map on both boards (`docs/design-log.md` §28).

## Still open

- LOG line format for the matrix.
- Time optimizations (deferred on purpose): ACK interrupting a frame, repeat only the failed matrix, drop SYN/SFD, back to one byte per matrix.
