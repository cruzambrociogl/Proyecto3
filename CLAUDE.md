# PROJECT03 — Claude Code configuration

> Claude Code loads this file automatically in every session.
> It holds all the project context, so the work can continue on any machine from this folder alone.

---

## Project overview

Final project of CC8 (Networks), "Capa Física No Convencional". Two BeagleBone Black boards run a bidirectional web chat over non-conventional physical channels (laser, IR, sound) with a clock channel. The professor grades it only in an in-person defense, with a live demo: physical interference → validation → NACK → retransmission.

The protocol is designed and was **accepted by the professor on 2026-11-14**, but it is **not built yet**. The code in `phy-chat/` is an earlier version (v2).

## Quick reference

- **Assignment:** `Proyecto_-_Capa_Fisica_.pdf`
- **Protocol spec (source of truth):** `docs/protocol.md`. Items marked "(proposed)" are details not yet confirmed.
- **History, professor feedback, decisions, hardware:** `docs/design-log.md`
- **Code:** `phy-chat/`. Python 3, stdlib only, the same code runs on the laptop (simulated medium) and on the BBB (GPIO).
- **Tests:** `cd phy-chat && python3 -m unittest -v tests.test_stack tests.test_fec` (29 tests, all pass on v2)
- **Math checks:** `python3 docs/experiments/matrix_nibble.py` (run from this folder)
- **Evaluation speed:** 1 Hz for everything

## Context files

Load the file a task needs; don't load them all at once.

| File | When to load |
|---|---|
| `claude/context.md` | understanding the assignment, the professor's rules, what was rejected and why, hardware state |
| `claude/analysis.md` | working on the code: module map, data flow, where v6b plugs in |
| `claude/conventions.md` | writing code, docs, CSVs or messages |
| `claude/instructions/build-v6b.instructions.md` | implementing the accepted protocol |
| `claude/instructions/live-testing.instructions.md` | running nodes or servers to test |
| `claude/instructions/professor-material.instructions.md` | preparing anything the professor will see |
| `docs/protocol.md` | any protocol question; read the section, not the whole file |
| `docs/design-log.md` | why something was decided; the full quoted feedback |

## Rules

1. **The spec is `docs/protocol.md`.** Build what it says. If the code needs to differ, change the English spec first, then its Spanish translation `docs/protocolo.md`, then the code.
2. **Describe before building.** Cruz wants each build step explained (what changes, how it works) before code is written. Confirm before starting a step.
3. **Never drift to serial.** The professor rejected every design that splits one bit stream across channels or locks channels to shared clock windows. Any change must keep the matrix: rows serial, columns parallel, validation horizontal + vertical + diagonal. See `claude/context.md`.
4. **Recovery is by equations**, never majority vote, and not only by retransmission. CRC-8 + ACK/NACK stay as the last net.
5. **Folder layout:** context (docs, notes, decisions, instructions, experiment scripts) goes in `docs/` or `claude/`. `phy-chat/` holds only the implementation: code, tests, run scripts, its README.
6. **English** for all docs and notes. Spanish only when Cruz asks, and only as a translation of an English original. In Spanish versions keep technical terms in English (tick, frame, CLK, XOR, CRC-8, ACK/NACK).
7. **Keep scripts in the project**, never only in a scratch folder. An earlier scratchpad was wiped and the Excel generator was lost with it.
8. **Live tests never touch Cruz's processes:** non-default ports, stop by PID. See `claude/instructions/live-testing.instructions.md`.
9. **Commits:** Cruz is the only author (repo-local identity `cruzambrociogl`, his Galileo account). No `Co-Authored-By` or any Claude attribution, even if the tool suggests one. Commit only when asked. A pushed remote must use the `github-edu` SSH alias (`git@github-edu:Owner/repo.git`); plain `github.com` authenticates as his work account.
10. **Build over theory:** prefer a working skeleton with swap points over new speculative experiments. Run an experiment only if it settles a pending decision, and report only what actually ran.
11. **BBB GPIO is 3.3 V and not 5 V tolerant.** Never suggest wiring a 5 V output straight to a pin.
12. **Living documentation:** when the design, hardware or status changes, update `docs/design-log.md` (new dated section) and the tracker below.

## Status tracker

> Updated: 2026-11-15

**Done**
- v1/v2 stack in `phy-chat/`: web chat, LOG, oscilloscope view, UTF-8 / Extended ASCII, START/DATA/END messages, frame, CRC-8 ×4, ACK/NACK, stop-and-wait, SEQ, PING/PONG link health, simulated medium with interference buttons, GPIO PHY (1 read per tick), 29 tests.
- Protocol v6b designed, verified by brute force, written as `docs/protocol.md`, accepted by the professor.

**Next (build order, see `claude/instructions/build-v6b.instructions.md`)**
1. ⬜ Matrix line coding in the simulator (5 channels, three kinds of reading, D1 inverted, CLK matrix mark, LOG and oscilloscope).
2. ⬜ Queues: 4 priority levels, aging, repair buffer, channel report in ACK/NACK/PING/PONG.
3. ⬜ GPIO PHY with 4 reads per tick.
4. ⬜ Both nodes on one BBB over 10 plain wires (checkpoint).
5. ⬜ Swap wires for real media one channel at a time.
6. ⬜ Demo rehearsal + wiring document for the ZIP.

**Blocked / waiting on Cruz**
- Parts: only 3 channels per direction on hand, 5 needed (`docs/design-log.md` §22).
- DL-591 identity (probably IR receivers), buzzer type (active/passive).
- Second BBB not available yet. Both nodes run on one board until then.

## Decision log

Short entries; the full reasoning is in `docs/design-log.md` (section in brackets).

- **2026-10-28/29** — v1 built: full stack, plain level coding. [§3, §6]
- **2026-11-04** — v2: Manchester symbols (invalid pattern = erasure) + XOR parity lane. FEC adds to CRC + ACK/NACK, never replaces them. No majority vote. [§6, §9 D1–D3]
- **2026-11-05** — CLK is never interfered; any number of data channels can be. [§9 D4]
- **2026-11-05 → 11-08** — v3 (GF(16) RAID-6), v4 (blink-count FSK + mod 5), v5 (independent frequencies) explored. All rejected or dropped as serial. [§7, §8]
- **2026-11-11** — Professor's email: must be a hybrid of parallel and serial, validate bits during transmission, base case "validación de canales y recuperación de bits mediante matrices". [§13]
- **2026-11-11** — v6: one byte per 5×4 matrix with horizontal, diagonal and vertical XOR checks; survives 2 dead channels. Then v6b: one half byte per matrix, survives until one channel is left. [§14, §15]
- **2026-11-12** — Professor: positive on v6b; asks for queues with priorities "como CC7"; everything is evaluated at 1 Hz. [§16]
- **2026-11-13** — Queues, frame states and aging added, ignoring time cost on purpose (optimise later). Three kinds of reading, D1 inverted, channel report added. Link life, message and constants written down. [§17–§19]
- **2026-11-14** — Professor accepts the complete proposal ("even too complex, but ok"). Design phase closed. [§20]
- **2026-11-14** — `docs/protocol.md` written as the single spec. Hardware inventory and build plan recorded. Both nodes will be BBB. [§21, §22]
- **2026-11-15** — Context moved to the project root (`docs/`, `claude/`, this file); `phy-chat/` holds implementation only. Docs in English. [§23]
