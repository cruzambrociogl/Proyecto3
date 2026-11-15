# PHY Chat protocol — full specification (v6b)

Project 03, Non-Conventional Physical Layer. This document holds the whole protocol as designed: channels, symbol, matrix, frame, message, queues and the life of the link.

- **Status:** design accepted by the professor on 2026-11-14 ("even too complex, but it is ok"). The whole evaluation runs at 1 Hz.
- **What is built:** the chat, the frame, CRC-8, ACK/NACK and the link exist in the code (version v2, with a different line coding). The matrix, the three kinds of reading and the full queues do not yet. See [section 14](#14-implementation-status).
- **Time:** the design ignores the time cost on purpose. Optimizations are in [section 15](#15-open-points-and-pending-optimizations).
- **History and decisions:** [design-log.md](design-log.md). Table version shown to the professor: [matrix_v6b_es.csv](matrix_v6b_es.csv) (Spanish), [matrix_v6b.csv](matrix_v6b.csv) (English). Spanish translation of this document: [protocolo.md](protocolo.md).

Items marked **(proposed)** are details not yet confirmed with anyone; the rest is what was shown to the professor.

---

## 1. Overview

- Two boards (BeagleBone) with a bidirectional web chat.
- Each direction has **5 physical channels of its own**: `CLK`, `D0`, `D1`, `P`, `Q`.
- Half a byte (4 bits) travels as **one matrix of 5 ticks × 4 channels**.
  - Rows are ticks: the **serial** part.
  - Columns are channels sent at the same time: the **parallel** part.
- Every data channel carries all 4 bits in a different XOR mix, so **one surviving channel is enough**.
- Bits are validated during transmission by three families of XOR equations: horizontal, diagonal and vertical.
- The frame CRC-8 and ACK/NACK remain as the last net.

### Layers

```
Application    web chat + LOG
Presentation   UTF-8 (1 to 4 bytes) or Extended ASCII
Message        START, one DATA per byte, END
Link           priority queues, stop-and-wait, ACK/NACK, SEQ, CRC-8
Frame          SYN | SFD | CTRL | DATA | CRC | SEQ = 40 bits = 10 matrices
Matrix         4 bits -> 5 ticks x 4 channels, with horizontal, diagonal and vertical validation
Symbol         4 reads per tick: valid, blocked or noisy
Medium         light, sound, etc. Each channel ends as a 0/1 on a pin
```

### Units

```
read  <  tick (4 reads)  <  matrix (5 ticks)  <  frame (10 matrices)  <  message (bytes + 2 frames)
```

| Unit | Contains | Duration |
|---|---|---|
| Read | one sample of the sensor (0 or 1) | a quarter of a tick |
| Tick | 4 reads per channel = one row of the matrix | 1 s at 1 Hz |
| Matrix | 5 ticks × 4 channels = 20 cells = 4 data bits | 5 ticks |
| Frame | 10 matrices = 40 bits | 50 ticks |
| Message | START + one DATA per byte + END | (bytes + 2) frames |

---

## 2. Channels

| Channel | Role | Interference |
|---|---|---|
| `CLK` | marks every tick and the start of every matrix | never interfered (professor's rule) |
| `D0` | the 4 bits in order | can be blocked or noisy |
| `D1` | the 4 bits shifted by one tick; travels **inverted** | same |
| `P` | `D0 ^ D1` at every tick | same |
| `Q` | diagonal mix of `D0` and `P` | same |

- 5 channels per direction, 10 in total. Each direction has its own `CLK`.
- The two directions share nothing in the medium: both boards can send at the same time.
- At rest all emitters are off (level 0) and the `CLK` is silent.
- Media assignment **(proposed, depends on the parts)**: `CLK` and `D0` on laser, `D1` and `P` on IR, `Q` on sound. A hand that blocks all the light then leaves the sound channel alive.

---

## 3. Symbol: one tick

Each tick is split into 4 quarters. The sender holds one level per quarter, and the receiver reads each channel 4 times, once in the middle of each quarter.

| Pattern of 4 reads | Meaning |
|---|---|
| `0 0 1 1` | bit 1 |
| `1 1 0 0` | bit 0 |
| `0 0 0 0` | **blocked** (hand between emitter and sensor) |
| `1 1 1 1` | **blocked** (saturated sensor, IR pointer) |
| anything else | **noisy** (flicker, noise) |

Rules:

1. A blocked or noisy tick is an **unknown** cell (`E`).
2. If a channel showed **noise** on any tick of a matrix, **it is not believed for that whole matrix**: all its cells become unknown, even if some tick looked valid.
3. A channel that was only **blocked** keeps its good ticks.
4. `D1` travels inverted: the sender inverts the bit before sending it and the receiver inverts it back before the checks. Without this, the all-zero matrix would be valid, and the same interference on all 4 sensors could pass as data.

### The CLK

| Pattern | Meaning |
|---|---|
| `1 1 0 0` | normal tick |
| `1 0 1 0` | tick 0: start of a matrix (double blink) |
| silence | no transmission |

The receiver follows the rhythm of the `CLK` it receives, not its own clock, so the two directions can run at different rates.

---

## 4. The matrix

The 4 bits are `a b c d`, with `a` the most significant. Each cell has a fixed recipe:

```
            D0        D1       P        Q
  tick 0    a         b        a^b      a^b^c
  tick 1    b         c        b^c      b^c^d
  tick 2    c         d        c^d      a^b^c^d
  tick 3    d         a^b      a^b^d    a^c^d
  tick 4    a^b^c^d   a^c^d    b        a^b^d      <- vertical validation
```

### The three validations

All are XOR and must come out even.

| Validation | Rule | When it is checked |
|---|---|---|
| Horizontal | `P[t] = D0[t] ^ D1[t]` | every tick, tick 4 included |
| Diagonal | `D1[t] = D0[t+1]` and `Q[t] = D0[t] ^ P[t+1]`, for t = 0, 1, 2 | every tick from tick 1 |
| Vertical | tick-4 cell = XOR of the 4 cells above it in the same channel | at tick 4 |

### Where the recipes come from

The columns are windows of a single sequence `s[k+4] = s[k] ^ s[k+1]` that starts with `a, b, c, d`:

```
s0=a  s1=b  s2=c  s3=d  s4=a^b  s5=b^c  s6=c^d  s7=a^b^d  s8=a^c  s9=b^d
s10=a^b^c  s11=b^c^d  s12=a^b^c^d  s13=a^c^d  s14=a^d   (repeats every 15)
```

- `D0` starts at `s0`, `D1` at `s1`, `P` at `s4` and `Q` at `s10`.
- Each column is 4 consecutive terms plus their XOR.
- Any 4 consecutive terms of this sequence determine `a b c d`: that is why one channel is enough.

### Example: 'h' = `0110 1000`

A byte is two matrices, high half first.

```
  0110          D0  D1  P   Q          1000          D0  D1  P   Q
  tick 0        0   1   1   0          tick 0        1   0   1   1
  tick 1        1   1   0   0          tick 1        0   0   0   0
  tick 2        1   0   1   0          tick 2        0   0   0   1
  tick 3        0   1   1   1          tick 3        0   1   1   1
  tick 4        0   1   1   1          tick 4        1   1   0   1
```

What travels on the channels for `0110` (4 reads per tick; `D1` already inverted):

| Channel | Tick 0 | Tick 1 | Tick 2 | Tick 3 | Tick 4 | Matrix bits |
|---|---|---|---|---|---|---|
| CLK | `1 0 1 0` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | matrix start on tick 0 |
| D0 | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | `1 1 0 0` | `1 1 0 0` | 0 1 1 0 0 |
| D1 | `1 1 0 0` | `1 1 0 0` | `0 0 1 1` | `1 1 0 0` | `1 1 0 0` | 1 1 0 1 1 (travels as 0 0 1 0 0) |
| P | `0 0 1 1` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | `0 0 1 1` | 1 0 1 1 1 |
| Q | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | 0 0 0 1 1 |

All 16 matrices are in the [annex](#annex-the-16-matrices).

---

## 5. How the receiver decides

After tick 4 the receiver has 20 cells, each one 0, 1 or unknown.

1. **Mark the unknowns.** Blocked or noisy ticks, and every cell of a channel that showed noise ([section 3](#3-symbol-one-tick)).
2. **Solve.** Each known cell is an XOR equation in `a, b, c, d`. In practice the known cells are compared against the 16 possible matrices.
   - **Exactly one matrix matches everywhere:** accept it. If some cells were unknown, it was *rebuilt*.
   - **More than one matches:** not enough arrived. The matrix is **lost** (and known to be lost).
   - **None matches:** some channel lies. Go to step 3.
3. **Correct lies.**
   - *A few lying bits:* take the nearest matrix only inside the safe radius. Let `gap` be the smallest number of known cells in which two valid matrices differ, and `e` the differences to the nearest one: accept it if `2·e < gap` and it is the only one at that distance.
   - *One whole channel lying:* drop each channel in turn. If what remains matches exactly one matrix, and only one matrix appears across all the tries, accept it.
   - *Otherwise:* the matrix is **detected as bad** and treated as lost.
4. **Lost matrix:** the frame cannot be completed. Keep the good cells ([section 8](#8-link-ack-nack-and-retransmission)) and answer NACK.

### How fast the half byte is known

- With all 4 channels alive: tick 0 gives `a, b, c` and tick 1 gives `d`. Known after **2 ticks**; the other 3 only confirm.
- With one channel alive: known after **4 ticks**.

More channels alive = data known sooner. That is the hybrid part.

---

## 6. Cases

### A. One lying bit (flicker on `D1`, tick 2: reads 1 instead of 0)

```
            D0  D1  P   Q
  tick 0    0   1   1   0
  tick 1    1   1   0   0
  tick 2    1  [1]  1   0    horizontal fails: 1^1 = 0 but P = 1         -> names the row
  tick 3    0   1   1   1    diagonal fails:   D1[2] = 1 but D0[3] = 0
  tick 4    0   1   1   1    vertical of D1 fails: 1^1^1^1 = 0 but V = 1 -> names the column
```

The crossing of the row (tick 2) and the column (`D1`) is the liar. Flip it back to 0.

### B. Hand over `D0`, `D1` and `P` for the whole matrix (only `Q` alive)

```
            D0  D1  P   Q
  tick 0    E   E   E   0     a^b^c   = 0
  tick 1    E   E   E   0     b^c^d   = 0
  tick 2    E   E   E   0     a^b^c^d = 0    with tick 0: d = 0; with tick 1: a = 0
  tick 3    E   E   E   1     a^c^d   = 1    c = 1; then tick 1 gives b = 1
  tick 4    E   E   E   1     validation
```

Result: `0 1 1 0`, correct with no retransmission.

### C. The last channel also loses one tick

`Q` reads `0 E 0 1 1`. The lost tick is the XOR of the other four: `0^0^1^1 = 0`. Then solve as in B.

### D. The last channel loses two ticks

`Q` reads `0 E E 1 1`. Three equations are left for 4 bits: both `0110` and `0001` fit. The receiver **does not guess**: it keeps the 3 good cells and answers NACK. One more good cell from the repeat decides (for example `Q` on tick 1 is 0 for `0110` and 1 for `0001`).

---

## 7. Frame

This is the frame from the assignment. The matrix does not change it; it is only how its bits travel.

| Field | Bits | Content |
|---|---|---|
| SYN | 8 | `1010 1010` (lets the medium settle) |
| SFD | 8 | `B3` = `1011 0011` (start of frame) |
| CTRL | 4 | frame type |
| DATA | 8 | one byte |
| CRC | 8 | CRC-8 over two bytes: `(CTRL << 4) | SEQ` and `DATA` |
| SEQ | 4 | sequence number, 0 to 15 |

The 40 bits go most significant first, 4 bits per matrix:

```
  matrix   0    1    2    3    4     5    6    7    8    9
  field    SYN  SYN  SFD  SFD  CTRL  DATA DATA CRC  CRC  SEQ
```

Example: DATA with 'h' (`68`), SEQ 1 and CRC-8/SMBUS (`5D`) is the half bytes `A A B 3 1 6 8 5 D 1`.

| CTRL | Name | DATA |
|---|---|---|
| 1 | DATA | one byte of the text |
| 2 | ACK | channel report (bits 3 to 0) |
| 3 | NACK | channel report (bits 3 to 0) **(proposed)** |
| 4 | START | encoding id |
| 5 | END | number of bytes in the message mod 256 |
| 6 | PING | the board's CRC-8 (bits 7 and 6) + channel report (bits 3 to 0) |
| 7 | PONG | same as PING |

**Selectable CRC-8:** SMBUS (id 0), AUTOSAR (1), SAE-J1850 (2), MAXIM-DOW (3). PING and PONG are always checked with SMBUS, so the boards can read each other even when their settings differ.

**Start of frame (proposed):** the `CLK` is silent between frames, and since it is never interfered, the first tick after a silence is tick 0 of matrix 0. SYN and SFD confirm it when they can be solved.

---

## 8. Link: ACK, NACK and retransmission

1. **Stop-and-wait.** Each START, DATA or END frame waits for its ACK before the next one goes out.
2. **ACK.** The receiver answers ACK with the same SEQ when the frame is complete and the CRC-8 passes.
3. **NACK.** The receiver answers NACK when a matrix was lost or the CRC-8 fails.
4. **Timeout.** If neither ACK nor NACK arrives within 2 frame times, the sender repeats the frame. The other board may be in the middle of its own frame before it can answer.
5. **Retransmission.** The whole frame is repeated. At most 8 retries; then the frame goes to FAILED.
6. **Duplicates.** If an ACK is lost and a repeated frame arrives (same SEQ), the receiver drops it and sends the ACK again. START always opens a new message and is never treated as a duplicate.
7. **Repair.** The receiver keeps the good cells of a frame that failed. When the repeat arrives **(proposed rule)**:
   - if a matrix of the repeat solves on its own, use it;
   - otherwise merge the known cells of both copies and solve again; if the two copies contradict each other in any cell, drop the kept cells;
   - the frame CRC-8 decides at the end. Kept cells are cleared when a frame is accepted.
8. **Channel report.** ACK, NACK, PING and PONG carry 4 bits, one per channel: bit 3 = `D0`, bit 2 = `D1`, bit 1 = `P`, bit 0 = `Q` **(proposed order)**. A 1 means "in the last frame I received, that channel had blocked or noisy ticks". The sender shows it in its LOG.

---

## 9. Queues

Each board has its own queues. They exist because each direction can carry only one frame at a time.

```
  typed messages         frames ready to send               on the channels
 ┌──────────────┐      ┌───────────────────────────┐       ┌─────────────┐
 │ outbox (FIFO)│ ---> │ 0  ACK / NACK             │ ----> │ transmitter │ ---> other board
 └──────────────┘      │ 1  retransmission         │       │ one frame   │
                       │ 2  START / DATA / END     │       └──────┬──────┘
                       │ 3  PING / PONG            │              │ sent
                       └───────────────────────────┘              v
                                    ^                  ┌──────────────────────┐
                                    └── NACK/timeout ──│ waiting: one frame   │
                                                       │ blocked until ACK    │ ---> ACK: done
                                                       └──────────────────────┘
```

| Queue | What it holds | Order | CC7 (operating systems) equivalent |
|---|---|---|---|
| Outbox | messages typed by the user | FIFO | new job queue |
| Ready | frames ready to send | by priority; FIFO within a level | ready queue |
| Transmitter | the one frame on the channels | one at a time; not interrupted | running process |
| Waiting | frame sent and waiting for its ACK | one at a time, with timeout | process blocked on I/O |
| Repair | good cells of a frame that failed | until the repeat arrives | buffer |
| Inbox | bytes received and validated until END | FIFO | delivery buffer |

### Ready-queue priorities

| Level | What | Why |
|---|---|---|
| 0 | ACK / NACK | the other board is stopped waiting for it |
| 1 | Retransmission | it is already late |
| 2 | START / DATA / END of the current message | normal work |
| 3 | PING / PONG | only when there is nothing else |

**Aging:** a frame that waits more than 3 turns in ready moves up one level. Nothing waits forever. (1 turn = the time of one frame.)

### States of a frame

```
  NEW --> READY --> RUNNING --> WAITING --> DONE
            ^                      │
            └── NACK or timeout ───┘      (after 8 retries: FAILED)
```

| State | Meaning | Goes to | When |
|---|---|---|---|
| NEW | its message is in the outbox | READY | the previous frame of the message got its ACK |
| READY | waits its turn | RUNNING | the transmitter is free and it has the highest priority |
| RUNNING | its 10 matrices go out on the channels | WAITING | the last matrix ends (ACK, NACK, PING and PONG go straight to DONE) |
| WAITING | waits for its ACK | DONE | the ACK with its SEQ arrives |
| WAITING | waits for its ACK | READY level 1 | a NACK arrives or the timeout runs out |
| READY level 1 | retransmission | FAILED | 8 retries with no ACK |

### Example: both boards send at the same time

A sends 'h', B sends 'k', and the professor interferes with A's DATA. `[n]` is the priority level.

| Turn | A ready | A sends | B ready | B sends | At the end of the turn |
|---|---|---|---|---|---|
| 1 | `[2]` START(h) | START(h) | empty | nothing | B receives START and queues ACK. B's user types 'k'. |
| 2 | empty (START in waiting) | nothing | `[0]` ACK, `[2]` START(k) | ACK | The ACK goes before B's own START. DATA(h) enters ready. |
| 3 | `[2]` DATA(h) | DATA(h) | `[2]` START(k) | START(k) | Interference: B cannot solve matrix 5, keeps the good cells and queues NACK. A queues ACK. |
| 4 | `[0]` ACK | ACK | `[0]` NACK | NACK | DATA(h) goes from waiting to ready level 1. DATA(k) enters ready. |
| 5 | `[1]` DATA(h) retx | DATA(h) retx | `[2]` DATA(k) | DATA(k) | B fills the holes and the CRC-8 passes. Both queue ACK. |
| 6 | `[0]` ACK | ACK | `[0]` ACK | ACK | Both DATA frames are DONE. END enters ready. |
| 7 | `[2]` END | END | `[2]` END | END | Both receive END and queue ACK. |
| 8 | `[0]` ACK | ACK | `[0]` ACK | ACK | Messages complete: A shows 'k' and B shows 'h'. |

---

## 10. The message

A chat message is several frames, each with its own ACK.

| Frame | DATA | How many |
|---|---|---|
| START | encoding: 0 = UTF-8, 1 = Extended ASCII (CP437), 2 = Extended ASCII (ISO-8859-1) | 1 |
| DATA | one byte of the text | one per byte (UTF-8 uses 1 to 4 bytes per character) |
| END | number of bytes sent mod 256 | 1 |

Examples:

- 'h' in UTF-8: `START(0) DATA(68) END(1)`
- 'ñ' in UTF-8: `START(0) DATA(C3) DATA(B1) END(2)`
- 'ñ' in ISO-8859-1: `START(2) DATA(F1) END(1)`

Rules:

1. The receiver shows the message as complete only when END arrives and its count matches the bytes received.
2. If the count does not match, the message is marked as incomplete.
3. If a START arrives while a message is open, the previous message is dropped as incomplete.
4. A DATA or END outside a message is reported as an error and ignored.
5. If a frame ends in FAILED, the sender stops the message and marks it as not delivered.

---

## 11. Life of the link

```
  NO SIGNAL ──power on──> HELLO ──hear a frame──> RX ONLY ──PONG or ACK──> IDLE <────────┐
      ^                                              ^                      │            │
      │                                              │               message│            │ END + ACK
      │                                no ACK or PONG│                      v            │
      └──────── nothing heard ───────────────────────┴────────────────── TRANSFER ───────┘
```

| State | Meaning | Goes to | When |
|---|---|---|---|
| NO SIGNAL | no valid frame has been heard | HELLO | at power on, the board sends a PING right away |
| HELLO | each board announces its settings with PING; the other answers PONG | RX ONLY | a valid frame arrives |
| RX ONLY | I hear the other board, but nothing confirms my frames reach it | IDLE | a PONG or an ACK arrives |
| IDLE | connected, no messages | TRANSFER | there is a message in the outbox or a START arrives |
| TRANSFER | a message in progress | IDLE | END and its ACK |
| IDLE or TRANSFER | connected | RX ONLY | 7.5 frame times with no ACK and no PONG |
| any | | NO SIGNAL | 7.5 frame times without hearing a valid frame |

- **PING:** sent when the board has sent nothing for 3 frame times. Any received frame counts as a sign of life.
- **Different settings:** if the CRC-8 announced by the other board differs from our own, the user is warned and offered to adopt the other one.
- In the UI: 🟢 connected (IDLE or TRANSFER), 🟡 RX only, 🔴 no signal.

---

## 12. Constants

| Constant | Value | What for |
|---|---|---|
| Channels per direction | 5: CLK, D0, D1, P, Q | |
| Reads per tick | 4 | tell valid, blocked and noisy apart |
| Frequency | 1 Hz (configurable) | the whole evaluation runs at 1 Hz |
| Ticks per matrix | 5 | 4 data + 1 vertical validation |
| Matrices per frame | 10 | 40 bits |
| SYN | `1010 1010` | let the medium settle |
| SFD | `B3` | start of frame |
| SEQ | 0 to 15 | detect repeated frames |
| ACK timeout | 2 frame times | |
| Retries | 8 | then: FAILED |
| Aging | 3 turns | |
| PING | after 3 frame times without sending | |
| Alive window | 7.5 frame times | |
| Matrix capacity | 4 bits per 5 ticks = 0.8 × Hz bits/s | per direction |
| Useful data per frame | 8 bits per 50 ticks = 0.16 × Hz bits/s | per direction, ACK not counted |

At 1 Hz: a matrix takes 5 s, a frame 50 s, and a frame plus its ACK 100 s.

---

## 13. Verified results

### Blocked channels and lying bits

Brute force over all 16 half bytes. Script: `experiments/matrix_nibble.py`.

| Case | Recovered | Asked again | Wrong data accepted | Total |
|---|---|---|---|---|
| 1, 2 or 3 channels blocked for the whole matrix | all | 0 | 0 | 64 / 96 / 64 |
| 4 channels blocked | 0 | 16 | 0 | 16 |
| 1 alive and it loses 1 tick | 320 | 0 | 0 | 320 |
| 1 alive and it loses 2 ticks | 0 | 640 | 0 | 640 |
| 2 alive and each loses 1 tick | 2400 | 0 | 0 | 2400 |
| 2 alive and each loses 2 ticks | 8976 | 624 | 0 | 9600 |
| all 4 dark for 1, 2 or 3 ticks in a row | all | 0 | 0 | 80 / 64 / 48 |
| 1, 2 or 3 lying bits, nothing blocked | all | 0 | 0 | 320 / 3040 / 18240 |
| 1 channel lying in any way | 1984 | 0 | 0 | 1984 |
| 1 blocked + 1 channel lying | 5952 | 0 | 0 | 5952 |
| 2 blocked + 1 channel lying | 3072 | 2880 | 0 | 5952 |
| 2 channels lying, none blocked | 12000 | 80256 | 0 | 92256 |
| 3 blocked + the last one lying | 0 | 1024 | 960 | 1984 |

Minimum distance between matrices: 8.

**Weak spot:** with one channel alive, the only check on it is its own vertical bit. If that channel lies with a column that looks valid, the matrix accepts wrong data and only the frame CRC-8 catches it.

### Fast flicker

Each tick of the interfered channel is 4 random reads; 2 times in 16 it looks like a valid bit. 20000 matrices per case. Script: `experiments/flicker_nibble.py`.

| Case | Without the noise rule: recovered / wrong | With the noise rule: recovered / wrong |
|---|---|---|
| 2 flickering + 2 clean | 93.6% / 0% | 100% / 0% |
| 3 flickering + 1 clean | 80.6% / 2.9% | 100% / 0% |
| 2 flickering + 1 blocked + 1 clean | 91.7% / 0.68% | 100% / 0% |
| 1 flickering + 2 blocked + 1 clean | 99.9% / 0% | 100% / 0% |
| 4 flickering | 0.6% / 10.95% | 0% / 0.08% |

What is not recovered is asked again. "Wrong" is what the matrix accepts; the CRC-8 still catches 255 of every 256.

### The same reading on all 4 channels

Of the 32 possible readings that are the same on every channel: without inverting `D1`, 1 is a valid matrix (all zeros). With `D1` inverted none is, and the closest one is 5 cells away.

---

## 14. Implementation status

| Part | In the code today | Missing |
|---|---|---|
| Web chat, LOG, oscilloscope | yes | show the matrix and its validations |
| Presentation (UTF-8, Extended ASCII) | yes | |
| Message START / DATA / END | yes | |
| Frame, CRC-8 ×4, SEQ | yes | |
| ACK / NACK, stop-and-wait, timeout, 8 retries, duplicates | yes | |
| Priority queue | 2 levels (control, data) | 4 levels, aging |
| Link states, PING / PONG, HELLO with CRC-8 | yes (connected, RX only, no signal) | |
| Line coding | v2: Manchester + parity `P`, 3 channels + CLK | the v6b matrix with 5 channels |
| Three kinds of reading, `D1` inverted | no | all |
| Repair buffer | no | all |
| Channel report in ACK / PONG | no | all |
| PHY on the board (GPIO) | 1 read per tick | 4 reads per tick |
| Simulated medium (laptop) | yes, with block, IR and noise buttons | adapt to 5 channels |

---

## 15. Open points and pending optimizations

**Open (to decide while building):**

1. What each `CLK` signal means beyond "tick" and "matrix start": silence and frame start are only proposed ([section 7](#7-frame)).
2. Whether SYN and SFD travel inside matrices (as written here) or the `CLK` mark replaces them.
3. The format of a LOG line for the matrix: received row, validations passed, queue state.
4. The exact repair rule and the bit order of the channel report ([section 8](#8-link-ack-nack-and-retransmission)).
5. The physical media: the current parts make 3 channels per direction and the design needs 5.

**Time optimizations (left for later on purpose):**

1. Let an ACK interrupt a data frame between two matrices (5 s wait instead of 50 s).
2. Repeat only the failed matrix instead of the whole frame.
3. Take SYN and SFD out of the matrices (30 s frame instead of 50 s).
4. Go back to one byte per matrix (v6): half the time, but only 2 blocked channels survive.

**Pending reinforcements:**

1. Channel memory: a channel that was noisy stays distrusted for the next matrices. Not tested.
2. Spread the 4 data channels over at least 3 media, so one kind of interference cannot reach all of them.

---

## Annex: the 16 matrices

Each column shows the channel's 5 bits, tick 0 to tick 4. "D1 on the channel" is `D1` already inverted, as it travels.

| Hex | a b c d | D0 | D1 | D1 on the channel | P | Q |
|---|---|---|---|---|---|---|
| 0 | 0 0 0 0 | 0 0 0 0 0 | 0 0 0 0 0 | 1 1 1 1 1 | 0 0 0 0 0 | 0 0 0 0 0 |
| 1 | 0 0 0 1 | 0 0 0 1 1 | 0 0 1 0 1 | 1 1 0 1 0 | 0 0 1 1 0 | 0 1 1 1 1 |
| 2 | 0 0 1 0 | 0 0 1 0 1 | 0 1 0 0 1 | 1 0 1 1 0 | 0 1 1 0 0 | 1 1 1 1 0 |
| 3 | 0 0 1 1 | 0 0 1 1 0 | 0 1 1 0 0 | 1 0 0 1 1 | 0 1 0 1 0 | 1 0 0 0 1 |
| 4 | 0 1 0 0 | 0 1 0 0 1 | 1 0 0 1 0 | 0 1 1 0 1 | 1 1 0 1 1 | 1 1 1 0 1 |
| 5 | 0 1 0 1 | 0 1 0 1 0 | 1 0 1 1 1 | 0 1 0 0 0 | 1 1 1 0 1 | 1 0 0 1 0 |
| 6 | 0 1 1 0 | 0 1 1 0 0 | 1 1 0 1 1 | 0 0 1 0 0 | 1 0 1 1 1 | 0 0 0 1 1 |
| 7 | 0 1 1 1 | 0 1 1 1 1 | 1 1 1 1 0 | 0 0 0 0 1 | 1 0 0 0 1 | 0 1 1 0 0 |
| 8 | 1 0 0 0 | 1 0 0 0 1 | 0 0 0 1 1 | 1 1 1 0 0 | 1 0 0 1 0 | 1 0 1 1 1 |
| 9 | 1 0 0 1 | 1 0 0 1 0 | 0 0 1 1 0 | 1 1 0 0 1 | 1 0 1 0 0 | 1 1 0 0 0 |
| A | 1 0 1 0 | 1 0 1 0 0 | 0 1 0 1 0 | 1 0 1 0 1 | 1 1 1 1 0 | 0 1 0 0 1 |
| B | 1 0 1 1 | 1 0 1 1 1 | 0 1 1 1 1 | 1 0 0 0 0 | 1 1 0 0 0 | 0 0 1 1 0 |
| C | 1 1 0 0 | 1 1 0 0 0 | 1 0 0 0 1 | 0 1 1 1 0 | 0 1 0 0 1 | 0 1 0 1 0 |
| D | 1 1 0 1 | 1 1 0 1 1 | 1 0 1 0 0 | 0 1 0 1 1 | 0 1 1 1 1 | 0 0 1 0 1 |
| E | 1 1 1 0 | 1 1 1 0 1 | 1 1 0 0 0 | 0 0 1 1 1 | 0 0 1 0 1 | 1 0 1 0 0 |
| F | 1 1 1 1 | 1 1 1 1 0 | 1 1 1 0 1 | 0 0 0 1 0 | 0 0 0 1 1 | 1 1 0 1 1 |
