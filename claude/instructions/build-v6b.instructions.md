# Building the accepted protocol (v6b)

Spec: `docs/protocol.md`. Code map: `claude/analysis.md`. Describe each step to Cruz and get a go before writing its code.

## Step 1 — Matrix coding in the simulator

1. New `phychat/matrixcode.py`:
   - encode a half byte into a 5×4 matrix (recipes in spec §4; port `docs/experiments/matrix_nibble.py`);
   - D1 inverted on the channel;
   - classify 4 reads as valid / blocked / noisy (spec §3), and distrust a noisy channel for the whole matrix;
   - decode with the rules of spec §5 (exact match, safe radius, one lying channel, otherwise lost).
2. A PHY wrapper (like `CodedPhy`) with channels `CLK D0 D1 P Q`, 4 samples per tick, CLK `1 0 1 0` on tick 0 of each matrix.
   - The receiver keeps its place in the matrix from the CLK.
   - It decodes when the matrix ends and hands the frame bits to the link.
3. Frame = 10 matrices: `Link.frame_time` must use a coding hook (50 ticks), otherwise the ACK timeouts are too short.
4. `node.py --coding matrix`; `run_sim.sh` works with it; the simulator's interference buttons cover 5 channels.
5. Tests: the verified tables of spec §13 reproduced through the real module (blocked channels, lying bits, flicker with the noise rule, same reading on all channels), plus an end-to-end chat test.
6. UI: the oscilloscope shows the 5×4 matrix per received matrix, the failing checks, and what was rebuilt; the LOG notes it.

## Step 2 — Queues and link (spec §8–§11)

- 4 priority levels (0 ACK/NACK, 1 retransmission, 2 START/DATA/END, 3 PING/PONG), FIFO within a level, aging after 3 turns.
- Frame states NEW → READY → RUNNING → WAITING → DONE / FAILED, shown in the LOG.
- Repair buffer: keep good cells of a failed frame and merge them with the repeat (rule in spec §8.7).
- Channel report: 4 bits in DATA of ACK/NACK/PING/PONG (order D0 D1 P Q = bits 3..0).
- Link states with the IDLE / TRANSFER names.
- Tests for each rule, including the two-way example of spec §9.

## Step 3 — GPIO PHY with 4 reads per tick

- TX: 4 quarter-tick levels per channel; RX: 4 reads per tick, timed from the received CLK.
- 1 Hz only (the evaluation speed); measure the real limit on the board later.
- New pin map for 5 channels per direction (10 out + 10 in per board, 20 per BBB while both nodes share it).

## Step 4 — Wires checkpoint

Both nodes on one BBB with 10 plain jumpers per direction. `tools/gpio_selftest.py` passes, the chat works, and the interference cases work by pulling wires. After this, any failure is in a circuit, not the code.

## Step 5 — Real media

Replace one wire at a time with a real channel (emitter → medium → sensor → 3.3 V). Test each with a blink script and the logic analyzer before the chat.

## Step 6 — Defense

Rehearse: hand over channels, IR pointer, flicker, down to one channel alive, then all blocked → NACK → retransmission. Write the per-medium wiring document for the ZIP.

## When something in the spec is unclear

Ask Cruz. Don't invent protocol behaviour in code. If a decision is made, write it into `docs/protocol.md` (and `docs/protocolo.md`) and the design log first.
