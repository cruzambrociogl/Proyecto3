# PHY Chat Protocol — Protocol document (v6b)

Rosangela Rodriguez (22000127) · Cruz Ambrocio (20005588) · Ciencias de la Computación VIII · November 2026

## 1. Summary

The PHY Chat Protocol carries a bidirectional text chat between two BeagleBone Black boards over five non-conventional physical channels, each on a different medium: laser, infrared, sound, magnetic and light. Each direction has its own 5 channels: `CLK`, `D0`, `D1`, `P` and `Q`.

The protocol is neither serial nor fully parallel. The basic unit is a **matrix of 5 ticks × 4 channels** that carries half a byte:

- the **rows** are ticks sent one after another: the serial part;
- the **columns** are channels sent at the same time: the parallel part;
- every data channel carries all 4 bits in a different XOR mix, so **one channel that survives is enough** to recover them;
- the bits are validated **during** transmission, tick by tick, with three families of XOR equations: **horizontal** (between channels), **diagonal** (between consecutive ticks) and **vertical** (along each channel).

Above the matrix sits the frame of the assignment (`SYN → SFD → CTRL → DATA → CRC`, plus `SEQ`). CRC-8 in four selectable variants, ACK/NACK, retransmission and priority queues remain as the last safety net, for what the equations cannot solve.

Main mechanisms:

- **Symbol with three kinds of reading:** each tick is read 4 times, so the receiver tells a valid bit, a blocked channel (hand, IR pointer) and a noisy channel (flicker) apart.
- **Recovery by equations, not by vote:** the matrix survives 1, 2 or 3 blocked channels for the whole matrix, and up to 3 lying bits, with no retransmission.
- **Repair across retransmissions:** the receiver keeps the good cells of a failed frame and merges them with the repeat.
- **Priority queues with aging**, as in operating-system scheduling: ACK/NACK first, then retransmissions, then data, then link checks.
- **Channel report:** every ACK, NACK, PING and PONG tells the sender which of its channels arrived damaged.

The whole evaluation runs at **1 Hz** (configurable). The chat, the frame, CRC-8, ACK/NACK and the link already run in an earlier version of the program; the matrix described here is the design being built now (section 18). The first real channel, laser to infrared receiver, works on the board at the speed the protocol needs (15.6).

## 2. The problem

The assignment asks for a physical layer of 3 to 8 lines that carries bytes of 8 bits without being a conventional 8-line parallel port. The design also follows these conditions: it must be a hybrid of parallel and serial, it must validate bits during transmission and not only with the CRC after the frame, recovery must be by equations (matrices), and it must keep working while any number of data channels are interfered with at once. The `CLK` is never interfered.

## 3. Architecture

Each board runs **one program** with the four layers of the assignment kept as separate modules. The layers are a logical division, not separate programs.

```
  Board A                                               Board B
 ┌───────────────────────────────┐                   ┌───────────────────────────────┐
 │ Application   web chat + LOG  │                   │ Application   web chat + LOG  │
 │ Presentation  UTF-8/Ext.ASCII │                   │ Presentation  UTF-8/Ext.ASCII │
 │ Link          queues, ACK/NACK│                   │ Link          queues, ACK/NACK│
 │               SEQ, CRC-8      │                   │               SEQ, CRC-8      │
 │ Physical      frame, matrix,  │  CLK D0 D1 P Q    │ Physical      frame, matrix,  │
 │               symbol          │ ────────────────> │               symbol          │
 │               (GPIO)          │ <──────────────── │               (GPIO)          │
 └───────────────────────────────┘  CLK D0 D1 P Q    └───────────────────────────────┘
     browser (HTTP)                                         browser (HTTP)
```

| Layer | Unit | What it does |
| --- | --- | --- |
| Application | text message | Web server: chat page, live LOG, view of the received matrices |
| Presentation | byte | Text ↔ bytes in UTF-8 (1 to 4 bytes per character) or Extended ASCII (CP437, ISO-8859-1) |
| Message | frames | `START`, one `DATA` per byte, `END` |
| Link | frame | Priority queues, stop-and-wait, ACK/NACK, SEQ, CRC-8, link state |
| Frame | 40 bits | `SYN · SFD · CTRL · DATA · CRC · SEQ`, cut into 10 half bytes |
| Matrix | half byte | 4 bits → 5 ticks × 4 channels, with horizontal, diagonal and vertical validation |
| Symbol | tick | 4 reads per tick: valid, blocked or noisy |
| Medium | level | Each channel ends as a 0/1 on a GPIO pin (15) |

The same program also runs on a laptop with a simulated medium, where buttons block, saturate or add noise to each channel. This is how the protocol is tested before the circuits exist.

## 4. Units and channels

```
read  <  tick (4 reads)  <  matrix (5 ticks)  <  frame (10 matrices)  <  message (bytes + 2 frames)
```

| Unit | Contains | Duration at 1 Hz |
| --- | --- | --- |
| Read | one sample of the sensor (0 or 1) | 0.25 s |
| Tick | 4 reads per channel = one row of the matrix | 1 s |
| Matrix | 5 ticks × 4 channels = 20 cells = 4 data bits | 5 s |
| Frame | 10 matrices = 40 bits | 50 s |
| Message | START + one DATA per byte + END | (bytes + 2) frames |

| Channel | Role | Interference |
| --- | --- | --- |
| `CLK` | marks every tick and the start of every matrix | never interfered |
| `D0` | the 4 bits in order | can be blocked or noisy |
| `D1` | the 4 bits shifted by one tick; travels **inverted** | same |
| `P` | `D0 ^ D1` at every tick | same |
| `Q` | a diagonal mix of `D0` and `P` | same |

The two directions share nothing in the medium. At rest every emitter is off (level 0) and the `CLK` is silent.

## 5. Symbol and clock

### 5.1 Three kinds of reading

Each tick is split into 4 quarters. The sender holds one level per quarter, and the receiver reads each channel once in the middle of each quarter.

| 4 reads | Meaning | Typical cause |
| --- | --- | --- |
| `0 0 1 1` | bit 1 | |
| `1 1 0 0` | bit 0 | |
| `0 0 0 0` | **blocked** | a hand between emitter and sensor |
| `1 1 1 1` | **blocked** | a saturated sensor, an IR pointer |
| anything else | **noisy** | flicker, noise |

A bit is a transition, as in Manchester coding, so a channel stuck at one level can never pass for data. The rules:

1. A blocked or noisy tick is an unknown cell (`E`).
2. If a channel showed **noise** on any tick of a matrix, it is not believed for that whole matrix: all its cells become unknown, even those that looked valid. Fast flicker can imitate a valid pattern by chance (2 times in 16); this rule removes those false cells.
3. A channel that was only **blocked** keeps its good ticks.
4. **`D1` travels inverted.** The sender inverts it and the receiver inverts it back. Without this, the all-zero matrix is valid, and the same interference on all four sensors (all dark or all lit) could pass as data. With `D1` inverted, no uniform reading is a valid matrix (19.3).

### 5.2 The clock

| `CLK` pattern | Meaning |
| --- | --- |
| `1 1 0 0` | normal tick |
| `1 0 1 0` | tick 0: start of a matrix (double blink) |
| silence | between frames, or no transmission |

The receiver follows the rhythm of the `CLK` it receives, not its own clock, so each direction can run at its own rate. Since the `CLK` is never interfered, the first tick after a silence is tick 0 of matrix 0 of a new frame; SYN and SFD confirm it when they can be solved.

## 6. The matrix

### 6.1 Recipes

The 4 bits are `a b c d`, with `a` the most significant. Each cell has a fixed recipe:

```
            D0        D1       P        Q
  tick 0    a         b        a^b      a^b^c
  tick 1    b         c        b^c      b^c^d
  tick 2    c         d        c^d      a^b^c^d
  tick 3    d         a^b      a^b^d    a^c^d
  tick 4    a^b^c^d   a^c^d    b        a^b^d      <- vertical validation
```

The columns are not chosen by hand. They are windows of one sequence, `s[k+4] = s[k] ^ s[k+1]`, that starts with `a, b, c, d` (a maximum-length shift-register sequence, period 15):

```
s0=a  s1=b  s2=c  s3=d  s4=a^b  s5=b^c  s6=c^d  s7=a^b^d  s8=a^c  s9=b^d
s10=a^b^c  s11=b^c^d  s12=a^b^c^d  s13=a^c^d  s14=a^d
```

`D0` starts at `s0`, `D1` at `s1`, `P` at `s4` and `Q` at `s10`. Each column is 4 consecutive terms plus their XOR. **Any 4 consecutive terms of this sequence determine `a b c d`**, which is why a single surviving channel is enough. The offsets were chosen by searching all options for the largest distance between valid matrices when 4, 3, 2 and 1 channels are alive.

### 6.2 The three validations

All are XOR equations that must come out even.

| Validation | Rule | When |
| --- | --- | --- |
| Horizontal | `P[t] = D0[t] ^ D1[t]` | every tick, tick 4 included |
| Diagonal | `D1[t] = D0[t+1]` and `Q[t] = D0[t] ^ P[t+1]`, for t = 0, 1, 2 | every tick from tick 1 |
| Vertical | tick-4 cell = XOR of the 4 cells above it in the same channel | at tick 4 |

A horizontal failure names the tick; a vertical failure names the channel; their crossing is the wrong cell. This is the same idea as row-diagonal parity in RAID-6 storage, applied to channels instead of disks.

### 6.3 Example: 'h' = `0110 1000`

A byte is two matrices, high half first.

```
  0110          D0  D1  P   Q          1000          D0  D1  P   Q
  tick 0        0   1   1   0          tick 0        1   0   1   1
  tick 1        1   1   0   0          tick 1        0   0   0   0
  tick 2        1   0   1   0          tick 2        0   0   0   1
  tick 3        0   1   1   1          tick 3        0   1   1   1
  tick 4        0   1   1   1          tick 4        1   1   0   1
```

What travels on the channels for `0110` (4 reads per tick, `D1` already inverted):

| Channel | Tick 0 | Tick 1 | Tick 2 | Tick 3 | Tick 4 | Matrix bits |
| --- | --- | --- | --- | --- | --- | --- |
| `CLK` | `1 0 1 0` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | matrix start on tick 0 |
| `D0` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | `1 1 0 0` | `1 1 0 0` | 0 1 1 0 0 |
| `D1` | `1 1 0 0` | `1 1 0 0` | `0 0 1 1` | `1 1 0 0` | `1 1 0 0` | 1 1 0 1 1 (travels as 0 0 1 0 0) |
| `P` | `0 0 1 1` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | `0 0 1 1` | 1 0 1 1 1 |
| `Q` | `1 1 0 0` | `1 1 0 0` | `1 1 0 0` | `0 0 1 1` | `0 0 1 1` | 0 0 0 1 1 |

All 16 matrices are in the annex.

## 7. How the receiver decides

### 7.1 Decision rule

After tick 4 the receiver has 20 cells, each 0, 1 or unknown.

1. **Mark the unknowns:** blocked or noisy ticks, and every cell of a channel that showed noise.
2. **Solve.** Each known cell is an XOR equation in `a, b, c, d`; the known cells are compared with the 16 valid matrices.
   - Exactly one matches everywhere: accept it. If cells were unknown, it was **rebuilt**.
   - More than one matches: not enough arrived. The matrix is **lost**, and the receiver knows it.
   - None matches: some channel lies; go to step 3.
3. **Correct lies.**
   - *A few lying bits:* take the nearest valid matrix only inside the safe radius. With `gap` = the smallest number of known cells in which two valid matrices differ, and `e` = the differences to the nearest one, accept it if `2·e < gap` and it is the only one at that distance.
   - *One whole channel lying:* drop each channel in turn; accept if what remains matches exactly one matrix and the same matrix appears in every try that matches.
   - *Otherwise:* the matrix is **detected as bad** and treated as lost.
4. **Lost matrix:** the frame cannot be completed. The receiver keeps the good cells (section 9, item 5) and answers NACK.

The receiver never guesses. A matrix is either solved by the equations or declared lost.

With all 4 channels alive, tick 0 already gives `a, b, c` and tick 1 gives `d`: the half byte is known after 2 ticks and the rest only confirms it. With one channel alive it is known after 4 ticks. More channels alive means the data is known sooner; that is the parallel part working.

### 7.2 Cases for the defense

**A. One lying bit** (flicker on `D1`, tick 2: reads 1 instead of 0)

```
            D0  D1  P   Q
  tick 0    0   1   1   0
  tick 1    1   1   0   0
  tick 2    1  [1]  1   0    horizontal fails: 1^1 = 0 but P = 1         -> names the row
  tick 3    0   1   1   1    diagonal fails:   D1[2] = 1 but D0[3] = 0
  tick 4    0   1   1   1    vertical of D1 fails: 1^1^1^1 = 0 but V = 1 -> names the column
```

The crossing of row and column is the liar; it is flipped back to 0.

**B. A hand over `D0`, `D1` and `P` for the whole matrix** (only `Q` alive)

```
            D0  D1  P   Q
  tick 0    E   E   E   0     a^b^c   = 0
  tick 1    E   E   E   0     b^c^d   = 0
  tick 2    E   E   E   0     a^b^c^d = 0    with tick 0: d = 0; with tick 1: a = 0
  tick 3    E   E   E   1     a^c^d   = 1    c = 1; then tick 1 gives b = 1
  tick 4    E   E   E   1     validation
```

Result `0 1 1 0`, correct, with no retransmission.

**C. The last channel also loses one tick.** `Q` reads `0 E 0 1 1`. The lost cell is the XOR of the other four: `0^0^1^1 = 0`. Then it is solved as in B.

**D. The last channel loses two ticks.** `Q` reads `0 E E 1 1`. Three equations remain for 4 bits, and both `0110` and `0001` fit. The receiver keeps the 3 good cells and answers NACK. One more good cell from the repeat decides (`Q` on tick 1 is 0 for `0110` and 1 for `0001`). This is the demo path CRC/validation → NACK → retransmission.

## 8. Frame

The frame of the assignment, unchanged. The matrix is only how its bits travel.

| Field | Bits | Content |
| --- | --- | --- |
| SYN | 8 | `1010 1010`: lets the medium and the receiver settle |
| SFD | 8 | `B3` = `1011 0011`: start of frame |
| CTRL | 4 | frame type |
| DATA | 8 | one byte |
| CRC | 8 | CRC-8 over two bytes: `(CTRL << 4) | SEQ` and `DATA` |
| SEQ | 4 | sequence number, 0 to 15 |

The 40 bits go most significant first, 4 bits per matrix:

```
  matrix   0    1    2    3    4     5    6    7    8    9
  field    SYN  SYN  SFD  SFD  CTRL  DATA DATA CRC  CRC  SEQ
```

Example: DATA with 'h' (`68`), SEQ 1, CRC-8/SMBUS (`5D`) is the half bytes `A A B 3 1 6 8 5 D 1`.

| CTRL | Name | DATA field |
| --- | --- | --- |
| 1 | DATA | one byte of the text |
| 2 | ACK | channel report (bits 3 to 0) |
| 3 | NACK | channel report (bits 3 to 0) |
| 4 | START | encoding id |
| 5 | END | bytes in the message mod 256 |
| 6 | PING | CRC-8 variant id (bits 7 and 6) + channel report (bits 3 to 0) |
| 7 | PONG | same as PING |

**Selectable CRC-8:** SMBUS (id 0), AUTOSAR (1), SAE-J1850 (2), MAXIM-DOW (3). The CRC covers CTRL and SEQ as well as DATA, so a wrong type or sequence number is also detected. PING and PONG are always checked with SMBUS, so two boards with different settings can still read each other's announcement.

**Start of frame:** the `CLK` is silent between frames; the first tick after a silence is tick 0 of matrix 0. SYN and SFD travel inside matrices 0 to 3 as the assignment requires and confirm the start.

## 9. Link: ACK, NACK and retransmission

1. **Stop-and-wait.** Each START, DATA and END frame waits for its ACK before the next one goes out.
2. **ACK.** Sent with the same SEQ when the frame is complete and the CRC-8 passes.
3. **NACK.** Sent when a matrix was lost or the CRC-8 fails.
4. **Timeout.** If neither ACK nor NACK arrives within 2 frame times, the frame is repeated (the other board may be in the middle of its own frame before it can answer).
5. **Repair.** The receiver keeps the good cells of a frame that failed. When the repeat arrives:
   - a matrix of the repeat that solves on its own is used as is;
   - otherwise the known cells of both copies are merged and solved again; if the copies contradict each other in any cell, the kept cells are dropped;
   - the frame CRC-8 decides at the end. Kept cells are cleared when a frame is accepted.
6. **Retries.** The whole frame is repeated, at most 8 times; then it is FAILED.
7. **Duplicates.** If an ACK is lost and a repeat arrives with the same SEQ, the receiver drops it and sends the ACK again. START always opens a new message and is never a duplicate.
8. **Channel report.** ACK, NACK, PING and PONG carry 4 bits: bit 3 = `D0`, bit 2 = `D1`, bit 1 = `P`, bit 0 = `Q`. A 1 means "in the last frame I received, that channel had blocked or noisy ticks". The sender shows it in its LOG, so both sides see which channel is being attacked.

## 10. Queues

Each direction carries one frame at a time and a frame takes 50 s at 1 Hz, so both boards need wait queues. They follow CPU scheduling from operating systems.

### 10.1 The queues

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

| Queue | Holds | Order | Operating-system equivalent |
| --- | --- | --- | --- |
| Outbox | messages typed by the user | FIFO | new job queue |
| Ready | frames ready to send | by priority, FIFO within a level | ready queue |
| Transmitter | the frame on the channels | one at a time, not interrupted | running process |
| Waiting | frame sent, waiting for its ACK | one at a time, with timeout | process blocked on I/O |
| Repair | good cells of a frame that failed | until the repeat arrives | buffer |
| Inbox | bytes received and validated until END | FIFO | delivery buffer |

### 10.2 Priorities and aging

| Level | Frames | Why |
| --- | --- | --- |
| 0 | ACK / NACK | the other board is stopped waiting for it |
| 1 | retransmission | it is already late |
| 2 | START / DATA / END | normal work |
| 3 | PING / PONG | only when there is nothing else |

**Aging:** a frame that waits more than 3 turns in the ready queue moves up one level, so nothing waits forever. One turn is the time of one frame.

### 10.3 States of a frame

```
  NEW --> READY --> RUNNING --> WAITING --> DONE
            ^                      │
            └── NACK or timeout ───┘      (after 8 retries: FAILED)
```

| State | Meaning | Next | When |
| --- | --- | --- | --- |
| NEW | its message is in the outbox | READY | the previous frame of the message got its ACK |
| READY | waits its turn | RUNNING | the transmitter is free and it has the highest priority |
| RUNNING | its 10 matrices are on the channels | WAITING | the last matrix ends (ACK, NACK, PING and PONG go straight to DONE) |
| WAITING | waits for its ACK | DONE | the ACK with its SEQ arrives |
| WAITING | waits for its ACK | READY, level 1 | a NACK arrives or the timeout runs out |
| READY, level 1 | retransmission | FAILED | 8 retries with no ACK |

### 10.4 Example: both boards send at the same time

A sends 'h', B sends 'k', and someone interferes with A's DATA. `[n]` is the priority level.

| Turn | A ready | A sends | B ready | B sends | End of the turn |
| --- | --- | --- | --- | --- | --- |
| 1 | `[2]` START(h) | START(h) | empty | nothing | B receives START and queues ACK; B's user types 'k' |
| 2 | empty | nothing | `[0]` ACK, `[2]` START(k) | ACK | The ACK goes before B's own START; DATA(h) enters ready |
| 3 | `[2]` DATA(h) | DATA(h) | `[2]` START(k) | START(k) | Interference: B cannot solve matrix 5, keeps the good cells, queues NACK; A queues ACK |
| 4 | `[0]` ACK | ACK | `[0]` NACK | NACK | DATA(h) goes back to ready, level 1; DATA(k) enters ready |
| 5 | `[1]` DATA(h) retx | DATA(h) | `[2]` DATA(k) | DATA(k) | B fills the holes and the CRC-8 passes; both queue ACK |
| 6 | `[0]` ACK | ACK | `[0]` ACK | ACK | Both DATA frames are DONE; END enters ready |
| 7 | `[2]` END | END | `[2]` END | END | Both receive END and queue ACK |
| 8 | `[0]` ACK | ACK | `[0]` ACK | ACK | A shows 'k' and B shows 'h' |

## 11. Message and presentation

A chat message is several frames, each with its own ACK.

| Frame | DATA | How many |
| --- | --- | --- |
| START | encoding: 0 = UTF-8, 1 = Extended ASCII (CP437), 2 = Extended ASCII (ISO-8859-1) | 1 |
| DATA | one byte of the text | one per byte (UTF-8 uses 1 to 4 per character) |
| END | number of bytes sent mod 256 | 1 |

Examples:

- 'h' in UTF-8: `START(0) DATA(68) END(1)`
- 'ñ' in UTF-8: `START(0) DATA(C3) DATA(B1) END(2)`
- 'ñ' in ISO-8859-1: `START(2) DATA(F1) END(1)`
- '😀' in UTF-8: `START(0) DATA(F0) DATA(9F) DATA(98) DATA(80) END(4)`

Rules:

1. The message is shown as complete only when END arrives and its count matches the bytes received.
2. If the count does not match, the message is marked incomplete.
3. A START while a message is open drops the previous one as incomplete.
4. A DATA or END outside a message is logged as an error and ignored.
5. If a frame ends FAILED, the sender stops the message and marks it as not delivered.

## 12. Life of the link

```
  NO SIGNAL ──power on──> HELLO ──hear a frame──> RX ONLY ──PONG or ACK──> IDLE <────────┐
      ^                                              ^                      │            │
      │                                              │               message│            │ END + ACK
      │                                no ACK or PONG│                      v            │
      └──────── nothing heard ───────────────────────┴────────────────── TRANSFER ───────┘
```

| State | Meaning | Next | When |
| --- | --- | --- | --- |
| NO SIGNAL | no valid frame heard | HELLO | at power on the board sends a PING |
| HELLO | each board announces its settings with PING; the other answers PONG | RX ONLY | a valid frame arrives |
| RX ONLY | I hear the other board, but nothing confirms mine reach it | IDLE | a PONG or an ACK arrives |
| IDLE | connected, no messages | TRANSFER | a message in the outbox, or a START arrives |
| TRANSFER | a message in progress | IDLE | END and its ACK |
| IDLE or TRANSFER | connected | RX ONLY | 7.5 frame times with no ACK and no PONG |
| any | | NO SIGNAL | 7.5 frame times without a valid frame |

- A PING is sent after 3 frame times without sending anything. Any received frame counts as a sign of life.
- If the other board announces a different CRC-8 variant, the user is warned and offered to adopt it.
- In the chat page: green = connected (IDLE or TRANSFER), yellow = RX only, red = no signal.

## 13. LOG

Every board keeps a live LOG, shown in the chat page and saved to a file. The matrix runs at 1 Hz on purpose, so a person can follow it. Each entry has a time stamp and the direction (TX or RX).

| Event | What it records |
| --- | --- |
| Tick | the 4 reads of each channel and its class: valid, blocked or noisy |
| Matrix | the 20 cells, which validations failed (horizontal, diagonal, vertical), and the result: ok, rebuilt, corrected, lost |
| Frame | CTRL, SEQ, DATA, the CRC-8 variant, CRC ok or failed |
| ACK / NACK | sent or received, its SEQ, the channel report |
| Retransmission | which frame, retry number, cause (NACK or timeout), cells kept and repaired |
| Queues | frame state changes (NEW → … → DONE / FAILED), priority level, aging |
| Link | state changes (NO SIGNAL, HELLO, RX ONLY, IDLE, TRANSFER) and the peer's settings |
| Message | START with its encoding, END with its count, complete / incomplete / not delivered |

The page also draws each received matrix as a 5 × 4 grid, marking unknown cells, failing checks and rebuilt cells.

## 14. Constants

| Constant | Value | Purpose |
| --- | --- | --- |
| Channels per direction | 5: `CLK`, `D0`, `D1`, `P`, `Q` | |
| Reads per tick | 4 | tell valid, blocked and noisy apart |
| Frequency | 1 Hz (configurable) | the evaluation speed |
| Ticks per matrix | 5 | 4 data + 1 vertical validation |
| Matrices per frame | 10 | 40 bits |
| SYN | `1010 1010` | settle |
| SFD | `B3` | start of frame |
| SEQ | 0 to 15 | detect repeats |
| ACK timeout | 2 frame times | |
| Retries | 8 | then FAILED |
| Aging | 3 turns | |
| PING | after 3 frame times without sending | |
| Alive window | 7.5 frame times | |
| Matrix capacity | 4 bits per 5 ticks = 0.8 × Hz bit/s | per direction |
| Useful data | 8 bits per 50 ticks = 0.16 × Hz bit/s | per direction, ACK not counted |

At 1 Hz a matrix takes 5 s, a frame 50 s, and a frame with its ACK 100 s. The design ignores speed on purpose; the faster variants are listed in section 20.

## 15. Physical implementation

### 15.1 Boards

- Two BeagleBone Black boards, one program each (Debian 10, Python 3.7, standard library only).
- The GPIO works at **3.3 V and is not 5 V tolerant**. Every sensor output reaches the board at 3.3 V at most, and no emitter is powered from a GPIO pin.
- Until the second board arrives, both nodes run on one BBB, each with its own pins. Moving to two boards only changes the pin configuration file.
- Light and sound need no shared ground between the two boards.

### 15.2 Media and channels

Each of the 5 channels of a direction uses a different medium.

| Channel | Medium | Emitter | Receiver | 0 / 1 | Status |
| --- | --- | --- | --- | --- | --- |
| `CLK` | laser, red 650 nm | KY-008 module | DL-591 IR phototransistor + NPN gain stage | beam off / on | built and measured, one direction (15.6) |
| `D0` | infrared | 5 mm IR LED | DL-591 IR phototransistor | off / on | planned |
| `D1` | sound | buzzer | KY-038 microphone module (LM393 comparator, digital output) | silence / tone | planned |
| `P` | magnetic | electromagnet (coil) | Hall-effect sensor, digital output | no field / field | planned |
| `Q` | light | to define (placeholder) | to define | dark / lit | to define |

**Why this assignment:**

- The `CLK` goes on the laser, the only channel already measured and the one that settles fastest. The `CLK` is never interfered.
- The four data channels use four different media, two of light (`D0`, `Q`) and two that are not light (`D1`, `P`). A hand or an IR pointer over the light leaves sound and magnetism alive; noise near the microphone leaves the other three alive. One kind of interference never reaches all four, and one channel is enough (7.2, case B).
- Even if laser, infrared and light count as one medium (the assignment's table lists "light / infrared" in one row), light, sound and magnetism are three different media.

**Open points:** the parts on hand cover the laser, infrared and sound channels in both directions (2 lasers, 2 IR LEDs, 4 IR receivers, 2 buzzers, 2 microphones). The Hall sensors, coils and diodes still have to be bought, and the fifth medium chosen.

### 15.3 Circuit rules

- 3.3 V only into the BBB: every receiver is powered from the board's 3.3 V (P9_3) or goes through a divider.
- Every emitter is switched by an NPN transistor from its own supply; the GPIO pin only drives the base through a resistor.
- The grounds of the board and of the emitter supply are tied together.
- A diode across every coil (the electromagnet), so its turn-off spike never reaches the transistor.
- Each light receiver sits inside a dark tube that lets the beam in and keeps room light out.
- Sound in both directions at once: each microphone faces the other board's buzzer and is shielded from its own board's buzzer (foam or a tube), with the sensitivity turned down.
- At 1 Hz every medium must follow a change every 250 ms (a quarter tick).

### 15.4 Wiring per medium

**Laser emitter (built).** The KY-008 runs at 5 V; the transistor keeps the 5 V away from the board.

```
  BBB P8_7 ──[1 kΩ]──── base     NPN
                        collector ──── KY-008 (−)
  5 V supply ─────────────────────────── KY-008 (S)
                        emitter ─────── GND  (tied to BBB GND, P9_1)
```

**Light receiver (built).** The DL-591 alone gives about 3 µA under the red laser (0.3 V on 100 kΩ), far from the 2 V the board needs for a 1. A second NPN multiplies that current about 100 to 200 times.

```
  P9_3 (3.3 V) ──┬──────────── DL-591 short leg
                 │             DL-591 long leg ──┬── base, NPN
              [10 kΩ]                            │
                 │                        [470 kΩ]  (220 kΩ to 1 MΩ works)
                 ├──── P8_17 (input)             │
                 │                               │
           collector, NPN                        │
           emitter ──────────── P9_1 (GND) ──────┘
```

The output is **inverted**: beam on → 0 on the pin, beam off → 1. The program undoes this per pin, in the pin configuration, before the symbol layer sees the reads. The base-to-ground resistor drains small leak currents; without it, room-light flicker turned 7 of 28 "off" reads into "on".

**Infrared emitter (planned).** Same driver as the laser, with the LED and its series resistor from the 5 V supply to the collector (about 180 Ω for about 20 mA). The receiver is the same circuit as the light receiver.

**Sound (planned).** The buzzer is switched by an NPN from 5 V like the other emitters. An active buzzer only needs on/off; a passive one needs the board to generate the tone, which changes the driver (this is still to be checked on the parts). The KY-038 is powered from 3.3 V so its digital output is safe for the board; its potentiometer sets the threshold. Its output may pulse with the tone instead of holding a level, so it may need a hold stage (an RC filter) so that it reads as a steady 1 for a quarter tick. The sound transmitter uses P8_13, a pin with hardware PWM, in case the buzzer turns out to be passive (15.5).

**Magnetic (planned).** The emitter is a coil switched by an NPN (or a small MOSFET) from 5 V, with a diode across the coil. The receiver is a digital Hall-effect sensor. A common one, the A3144, needs at least 4.5 V, so it is powered from 5 V, but its output is open collector: it is pulled up to **3.3 V** with a 10 kΩ resistor, never to 5 V, so the pin only ever sees 3.3 V. The sensor's output is low when the field is present (inverted, like the light receiver).

```
  Emitter (board A)                              Receiver (board B)

  5 V ──┬─────────┐                              5 V ─────────── Hall VCC
        │       diode (cathode to 5 V)           GND ─────────── Hall GND
      coil        │                              P9_3 (3.3 V) ──[10 kΩ]──┬── Hall OUT
        ├─────────┘                                                      └── P8_16 (input)
        │
     collector
  P8_9 ──[1 kΩ]── base   NPN
     emitter ── GND
```

**Light (placeholder).** The fifth medium is not chosen yet. It keeps the `Q` pins of the map below, and its circuit follows the same rules: emitter through a transistor, receiver output at 3.3 V at most.

### 15.5 GPIO

- Each pin is set to GPIO mode before use: outputs as `gpio`, inputs as `gpio_pd` (with pull-down, so a loose input reads 0, like a blocked channel). The mode is lost on reboot, so the program sets it every time it opens a pin. In the default mode the pin's value changed in software but not on the header.
- The pins are driven through the Linux GPIO interface (sysfs).
- **Transmitter:** each channel holds one level per quarter tick (4 per tick); the `CLK` drives the timing.
- **Receiver:** 4 reads per channel per tick, one in the middle of each quarter, timed from the received `CLK` edge.

**Pin map: P8 header only, the same on both boards.** Each board needs 5 outputs and 5 inputs. The P8 header has 46 pins, but P8_3–P8_6 and P8_20–P8_25 belong to the internal memory (eMMC), P8_27–P8_46 to the HDMI output and the boot configuration, and P8_1–P8_2 are ground. That leaves 14 free GPIO pins (P8_7 to P8_19 and P8_26), enough for the 10 needed with 4 spare.

| Channel | Medium | Output (TX) | Input (RX) |
| --- | --- | --- | --- |
| `CLK` | laser | P8_7 | P8_17 |
| `D0` | infrared | P8_8 | P8_18 |
| `D1` | sound | P8_13 (hardware PWM) | P8_15 |
| `P` | magnetic | P8_9 | P8_16 |
| `Q` | light | P8_10 | P8_26 |
| spare | | P8_11, P8_12, P8_14, P8_19 (hardware PWM) | |

- Board A's output for a channel faces board B's input for the same channel, and the other way round, so both boards run the same pin configuration.
- P8 has no power pins. Power comes from P9: 3.3 V on P9_3 / P9_4 (receivers and pull-ups), 5 V on P9_7 / P9_8 or an external 5 V supply (emitters), ground on P9_1 / P9_2 or P8_1 / P8_2.
- P8_7 and P8_17 are the pins of the laser channel already built and measured.
- While the second board is not available, both nodes run on one board: node A uses this map on P8 and node B uses free pins of P9.

### 15.6 Measured on the hardware

Laser → DL-591 with the gain stage, one BBB, a test program that blinks the laser and reads the receiver in the middle of each half period.

| Test | Result |
| --- | --- |
| 1 Hz for one minute | every reading correct (inverted) |
| 2 Hz for about 85 s: a change every 250 ms, read 125 ms after it (the quarter tick of 1 Hz) | every reading correct |
| 4 Hz: read 62 ms after each change | about half the reads showed the previous level: the receiver settles in 60 to 125 ms. Enough for 1 Hz, with little margin beyond it |
| Beam blocked | the receiver reads "dark" whatever the laser does: the blocked case |
| Without the base-to-ground resistor | 7 of 28 "off" reads came back "on" |
| Room light | short bursts of false "on" about every 4 s; with the tube end covered, a whole run was clean. For the demo: a longer tube, aimed away from screens and lamps |

A hand leaks light between the fingers; a card or a book blocks the beam cleanly.

## 16. Demo: intentional physical errors

The assignment asks for a fully physical error test showing CRC → NACK → retransmission. Each action below is done by hand on the real channels while the chat runs; the LOG shows each step (13).

| Action | What the receiver reads | What the protocol does |
| --- | --- | --- |
| Card over one channel | the same level on all 4 reads: blocked | rebuilt from the other channels, no retransmission |
| Hand or card over all the light (`D0`, `Q`) | two data channels blocked | rebuilt from sound and magnetism (`D1`, `P`) |
| Light covered and a sound near the microphone | only `P` (magnetic) clean | rebuilt from one channel alone (case B) |
| IR pointer on a receiver | saturated, `1 1 1 1`: blocked | rebuilt, as with the card |
| Fast flicker (fingers waving through a beam) | patterns that are not valid: noisy | the channel is distrusted for the whole matrix; rebuilt if one channel is clean |
| Block all four data channels for a whole matrix (5 s at 1 Hz) | nothing but blocked cells | matrix lost → NACK → retransmission; the cells kept from the failed copy help the repeat (9, item 5) |
| Leave one channel and take two of its ticks | 3 good cells | matrix lost → NACK; one more cell from the repeat decides (case D) |
| Block three channels and disturb the last one | a column that may look valid | the matrix may accept it; the frame CRC-8 fails → NACK → retransmission |

The last row is the CRC → NACK → retransmission path of the assignment; the two before it are the same path started by the matrix validation. Blocking all four data channels for up to 3 ticks in a row is still rebuilt (19.1), so the blocks have to be long to force a NACK.

## 17. Design decisions

| Decision | Alternatives considered | Why |
| --- | --- | --- |
| Matrix: rows serial, columns parallel | Splitting one bit stream across the channels; frequency per channel; blink-count symbols | The others are serial in disguise or tie all channels to one shared window. In the matrix every channel is independent and complete |
| Half a byte per matrix | One byte per 5 × 4 matrix (twice as fast) | One byte per matrix survives only 2 blocked channels; half a byte survives until one channel is left |
| XOR equations to recover | Majority vote; retransmission only | Vote needs most channels healthy and cannot locate a liar. The equations rebuild data from any one channel and point to the wrong cell |
| Columns from one shift-register sequence | Hand-made parity columns | Any 4 consecutive terms determine the half byte, and the offsets give the largest distance between matrices |
| 4 reads per tick | 1 read per tick | With 1 read a blocked channel looks like a valid 0 or 1. With 4, blocked and noisy are seen and dropped |
| Noisy channel distrusted for the whole matrix | Trust its valid-looking ticks | Flicker imitates valid ticks by chance; with this rule no flicker case accepted wrong data while one channel was clean (19.2) |
| `D1` inverted | All channels with the same polarity | Removes the only uniform reading that was a valid matrix |
| SYN and SFD inside the matrices | The `CLK` mark replacing them | The assignment requires the `SYN → SFD → CTRL → DATA → CRC` structure; removing them is kept as a speed option |
| Frame start from `CLK` silence | Hunting SYN in the data | The `CLK` is never interfered, so its silence is a reliable separator even when the data channels are blocked |
| Stop-and-wait | Sliding window | One frame per direction at a time and 50 s per frame; a window would add state without gaining time at 1 Hz |
| Whole-frame repeat with repair | Repeat only the failed matrix | Simpler and keeps the assignment's frame intact; the kept cells already make the repeat count. Per-matrix repeat is a speed option |
| Four priority levels with aging | One FIFO | An ACK must not wait behind 50-second data frames, and aging prevents starvation |
| CRC over CTRL, SEQ and DATA | CRC over DATA only | A damaged type or sequence number would otherwise pass unnoticed |

## 18. Implementation status

| Part | Status |
| --- | --- |
| Web chat, LOG, view of the signals | running (earlier version) |
| UTF-8 and Extended ASCII; START / DATA / END | running |
| Frame, CRC-8 × 4, SEQ, ACK/NACK, stop-and-wait, timeout, retries, duplicates | running |
| PING/PONG and link states | running |
| Simulated medium with interference buttons | running |
| First real channel (laser → IR receiver on the BBB) | working; correct at 1 and 2 Hz (15.6) |
| Infrared, sound and magnetic channels; the fifth medium | planned |
| Matrix, three kinds of reading, `D1` inverted, `CLK` matrix mark | design, being built |
| Four priority levels, aging, repair, channel report | design, being built |
| 4 reads per tick on the GPIO | design |

## 19. Verified results

The design was checked by brute force over every case, with the scripts in `docs/experiments/`. These are results of the design; the measurements on the hardware are in 15.6.

### 19.1 Blocked channels and lying bits

All 16 half bytes in every combination. Script: `matrix_nibble.py`.

| Case | Recovered | Asked again | Wrong data accepted | Total |
| --- | --- | --- | --- | --- |
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

Minimum distance between two valid matrices: 8 cells.

### 19.2 Fast flicker

Each tick of an interfered channel is 4 random reads (2 times in 16 it looks like a valid bit). 20,000 matrices per case. Script: `flicker_nibble.py`.

| Case | Without the noise rule: recovered / wrong | With the noise rule: recovered / wrong |
| --- | --- | --- |
| 2 flickering + 2 clean | 93.6% / 0% | 100% / 0% |
| 3 flickering + 1 clean | 80.6% / 2.9% | 100% / 0% |
| 2 flickering + 1 blocked + 1 clean | 91.7% / 0.68% | 100% / 0% |
| 1 flickering + 2 blocked + 1 clean | 99.9% / 0% | 100% / 0% |
| 4 flickering | 0.6% / 10.95% | 0% / 0.08% |

What is not recovered is asked again. "Wrong" is what the matrix accepts; the frame CRC-8 still rejects 255 of every 256 of those.

### 19.3 The same reading on all channels

Of the 32 readings that are equal on every channel, without inverting `D1` one is a valid matrix (all zeros). With `D1` inverted none is, and the nearest valid matrix is 5 cells away.

## 20. Limits and pending work

- **Weak spot:** with three channels blocked, the only check on the last one is its own vertical bit. If that channel lies with a column that looks valid, the matrix accepts wrong data (960 of 1984 cases in 19.1) and only the frame CRC-8 catches it.
- **Speed options, left for later on purpose:** let an ACK go between two matrices of a data frame (5 s instead of 50 s); repeat only the failed matrix; take SYN and SFD out of the matrices (30 s frames instead of 50 s); return to one byte per matrix (half the time, but only 2 blocked channels survive).
- **Reinforcement:** remember a channel that was noisy and keep distrusting it for the next matrices (not tested yet).
- **Physical media:** the infrared, sound and magnetic channels are still to be built, the fifth medium (light) is still to be chosen, and the Hall sensors and coils are still to be bought (15.2).

## 21. References

**Standards and specifications**

- F. Yergeau, "UTF-8, a transformation format of ISO 10646", [RFC 3629](https://www.rfc-editor.org/rfc/rfc3629), November 2003.
- ISO/IEC 8859-1:1998, *8-bit single-byte coded graphic character sets — Part 1: Latin alphabet No. 1*.
- IBM, *Code page 437* (the original PC character set).
- IEEE Std 802.3, clause 7: Manchester encoding of the 10 Mb/s Ethernet physical layer.
- *System Management Bus (SMBus) Specification*, version 3, SBS Implementers Forum: packet error checking with CRC-8.
- AUTOSAR, *Specification of CRC Routines* (Classic Platform).
- SAE J1850, *Class B Data Communications Network Interface*.
- Maxim Integrated, Application Note 27, "Understanding and Using Cyclic Redundancy Checks with Maxim 1-Wire and iButton Products".

**Publications and books**

- R. W. Hamming, "Error detecting and error correcting codes", *Bell System Technical Journal* 29(2), 147–160, 1950.
- S. W. Golomb, *Shift Register Sequences*, Holden-Day, 1967.
- P. Corbett, B. English, A. Goel, T. Grcanac, S. Kleiman, J. Leong, S. Sankar, "Row-Diagonal Parity for Double Disk Failure Correction", *USENIX FAST*, 2004.
- H. P. Anvin, ["The mathematics of RAID-6"](https://www.kernel.org/pub/linux/kernel/people/hpa/raid6.pdf), kernel.org.
- R. N. Williams, "A Painless Guide to CRC Error Detection Algorithms", 1993.
- G. Ewing, ["Catalogue of parametrised CRC algorithms"](https://reveng.sourceforge.io/crc-catalogue/).
- A. S. Tanenbaum, D. J. Wetherall, *Computer Networks*, 5th ed., Pearson, 2011 (physical layer, framing, stop-and-wait).
- J. F. Kurose, K. W. Ross, *Computer Networking: A Top-Down Approach*, 8th ed., Pearson, 2021 (reliable data transfer).
- A. Silberschatz, P. B. Galvin, G. Gagne, *Operating System Concepts*, 10th ed., Wiley, 2018 (priority scheduling and aging).

## Annex: the 16 matrices

Each column shows the channel's 5 bits, tick 0 to tick 4. "D1 on the channel" is `D1` already inverted, as it travels.

| Hex | a b c d | D0 | D1 | D1 on the channel | P | Q |
| --- | --- | --- | --- | --- | --- | --- |
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
