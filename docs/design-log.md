# PHY Chat: design log

This file holds the context for continuing the design. It records what the professor asked for, what we built, what we tried on paper, what we decided and why, and what is still open.

Last updated: 2026-11-15.

| | |
|---|---|
| **Layout** | `PROJECT03/docs/` holds all context: this log, the protocol spec, the CSVs for the professor, the experiment scripts. `PROJECT03/phy-chat/` holds only the implementation (code, tests, run scripts). |
| **Code** (`../phy-chat/`) | v2: Manchester symbols + XOR parity lane. Works in the simulator, 29 tests pass. |
| **Accepted design** | v6b matrix protocol, accepted by the professor on 2026-11-14. Full spec: [protocol.md](protocol.md) (Spanish translation: [protocolo.md](protocolo.md)). Not built yet. |
| **Next step** | Build v6b in the simulator, then on the BBB; build the circuits (section 22). |

---

## 1. The assignment

From `../Proyecto_-_Capa_Fisica_.pdf`:

- Two boards with a bidirectional chat in a web UI.
- **3–8 physical channels per direction; one of them must be the clock.**
- At least 3 different non-conventional media (light, sound, vibration, magnetic, air…). Each one ends as a GPIO 0/1.
- Frame: `SYN → SFD → CTRL (4 b) → DATA (8 b) → CRC-8 → [optional fields]`.
- Selectable CRC-8 variant: SMBUS, AUTOSAR, SAE-J1850, MAXIM-DOW.
- Selectable encoding: UTF-8 (1–4 bytes) or Extended ASCII.
- ACK/NACK with retransmission, plus a protocol LOG.
- A live demo: physical interference → CRC fails → NACK → retransmission.
- Delivery: a ZIP with the code and docs, including wiring per medium. **The grade comes only from the in-person defense.**

## 2. Hardware on hand

- BeagleBone Black. Its GPIO is **3.3 V and not 5 V tolerant**.
- Arduino Mega with a development shield.
- 2× MCP23017 I/O expanders.
- A cheap logic analyzer that works with the Logic software.

**Update 2026-11-14:** both nodes will be BeagleBone Black. Cruz has one board with him now; the second is not available yet, so development and circuit tests run both nodes on one BBB (as `run_bbb_loopback.sh` already does). Media parts on hand, inventory and plan in section 22.

---

## 3. Timeline

| Date | What happened |
|---|---|
| 2026-10-28/29 | **v1 built**: the full stack (sim PHY, GPIO PHY, link, web chat, LOG). Q&A on frames vs messages, SFD detection, IP-style fragmentation. |
| 2026-11-04 | **Review #1.** The professor said "you're thinking serial; think like IP / WiFi at bit level". A recording (professor + classmate + Cruz) set the direction: FEC, truth tables, and criticism of AI-steered standard designs. |
| 2026-11-04 | Interference model agreed: one channel at a time, clock included. **v2 designed in Excel and built** (`--coding fec`, channel panel, oscilloscope). |
| 2026-11-05 | Professor: **the CLK will not be interfered**, but **more than one data channel can be at the same time**. v2 is not enough. Proposed v2b (WiFi-style fallback) and v3 (GF(16) P+Q). |
| 2026-11-05 | Two more recordings analyzed (`Voice 261104_201320`, `Voice 261104_221056`). "Serial" means 2 channels carrying different bits; the base whiteboard test; the block-retransmission team; "what does WiFi do?". **v3 put on hold.** |
| 2026-11-05 | New hints: "not full serial nor full parallel", "frequency carries information". **v4**: blink-count FSK + line code mod 5. Extended to survive with 1 channel alive. |
| 2026-11-08 | Professor: **v4 is still serial, because every channel is tied to the CLK windows.** The clock can be ignored: each channel has its own frequency, so channels are independent. Led to **v5**. |

---

## 4. Everything the professor said

Several sources are garbled speech-to-text. Quotes are as transcribed; the English is our reading.

### Interference model
- He interferes **physically**:
  - a hand blocks the sensor, so it reads 0;
  - an IR pointer saturates it, so it reads 1;
  - noise;
  - a **very fast flicker that can still look valid**: *"si interrumpo muy rápido… y llegue eso y que sea válido, tampoco lo puedes comprobar"*.
- 2026-11-04 (Cruz's assumption): one channel at a time, the clock included.
- **2026-11-05: the CLK will not be interfered, but more than one data channel can be at the same time.**

### Recover, don't just retransmit
- *"…tiene que haber algo alrededor de todo eso que les valide, que se evite estar retransmitiendo. Y eso va a ser una ecuación matemática."* This means FEC: recovery by an equation.
- *"pueden transmitir 10 bits para solo 1 bit"*. This is an exaggeration; the point is to pay redundancy instead of retransmitting.
- *"[WiFi] lean de eso, van a ver que puede recuperarlo de una forma… increíble."* Later: *"¿Qué es lo que hace un Wi-Fi?"*
- **Majority vote rejected:** *"Tienen caso base de 3 líneas, 2 de data. Apago uno y ya se murió tu validación."*
- **The happy path is accepted:** *"No lo critico porque ese es el happy path."*

### What "serial" means (he called our design serial three times)
1. **2026-11-04:** the frame is designed as one bit stream, then chopped onto the lanes. The lanes are just a faster serial pipe.
2. **2026-11-04 (evening recording):** *"Eso [es] serial. Porque están mandando 4 y ustedes utilizando los 2 canales para enviar 2 [datos] diferentes."* So D0 and D1 carrying *different* bits of one stream is serial.
3. **2026-11-08:** v4 is serial because **all channels are locked to the CLK windows**. *The clock can be ignored; each channel has its own frequency, so they are independent.*

He also said:
- *"usualmente es serial porque en paralelo ya no se usa… siempre se va a ir por lo serial"*. He dislikes that every group defaults to serial.
- As Cruz relays it: it does **not have to be full serial nor full parallel**.

### Hints
- **Think in frequency: frequency carries information.**
- **The base whiteboard test**, which Cruz never delivered and doesn't remember the drawing of: *"en 2 canales mandar un bit matando 1"*.
  - 2 channels carry 1 bit. He kills one. The receiver detects **which** channel died and still gets the bit.
  - Then expand it: more bits, and parity across them, *"pero no mandándolo de una vez"*.
- **Validate every bit:** *"para validar un bit… lo mínimo"*.
- **Another team** splits the frame into **blocks** (not fields) and retransmits only the failed block, e.g. 25 + 5 bits, so 30 s instead of 50 s. **Our decision:** optional, use it only if needed.
- **Demo speed:** slow, around 1 Hz, *"el punto es poder ver el protocolo de transmisión"*. Tens of seconds per character is expected.
- Unclear (garbled): a mention of modulating over the **power grid** (*"red eléctrica… modula"*), and maybe Zigbee.
- If you mention a sequence number, it must actually be in the frame.

### How he wants us to work
- **Design with truth tables in Excel first** (cases → expected outputs), find the mathematical representation, *then* let AI implement against those expected outputs.
- AI pushes toward standard designs: *"va a intentar llevarlo al estándar"*. He wants ideas from **reading real protocols**, not from AI: *"hay un montón de ideas pero no son las de inteligencia artificial"*.

---

## 5. Design iterations at a glance

| # | Name | Core idea | Status | Survives | Verdict |
|---|---|---|---|---|---|
| v1 | plain lanes | CLK + N data lanes; a level per tick; frame bits dealt across lanes | built (`--coding plain`) | nothing: a blocked lane reads as a valid 0 | serial, no recovery |
| v2 | Manchester + XOR parity | 4 samples/tick, `0011`=1, `1100`=0, other patterns = erased; P = D0⊕D1; suspect history K=8 | **built** (default `--coding fec`), Excel | any **1** channel (CLK included), 0 retransmissions | not enough for >1 channel; D0/D1 carry different bits = serial |
| v2b | WiFi-style fallback (ARF) | FAST (2 b/tick) ↔ SAFE (same bit on D0, D1, P; take any lane that isn't erased); SFD announces the mode | paper | 2 of 3 data lanes; 1 retransmission at the switch | superseded |
| v2c | 5-light binary code | lights = a, b, a, b, a⊕b (a [5,2,3] code) | paper | any 2, 0 retransmissions | superseded (too many lights) |
| v3 | GF(16) P + Q (RAID-6) | each lane carries a nibble over 4 ticks; P = D0+D1, Q = D0+2·D1 | paper, verified (`experiments/raid6_gf16.py`) | any 2 of 4 | **on hold**: D0/D1 still carry different data |
| v4 | FSK + line mod 5 | blink count per CLK window = value; nibble → line y = a+bx+hop; any 2 points rebuild it; flat fallback | paper, verified (`experiments/line_mod5.py`) | 2 dead or 1 liar; flat mode: down to 1 alive | **serial**: channels locked to CLK windows |
| **v5** | **independent channels** | symbol = 2 cycles of the channel's *own* frequency; same line math, matched by symbol number; CLK = pilot | paper, timing script (`experiments/async_timeline.py`) | same as v4; a slow medium no longer sets the pace | **current direction**, not confirmed |
| side | time × frequency grid | M-FSK with permutation codes (power-line communication, Vinck ~2000): each frequency once, each moment once | lead only | – | not explored |

---

## 6. What is built (v1 + v2)

### Stack (v1, 2026-10-28)
```
App (web chat + LOG)  ->  Presentation (UTF-8 1–4 bytes / Extended ASCII)
                      ->  Link (CRC-8, ACK/NACK, stop-and-wait, SEQ)
                      ->  Physical (frame SYN|SFD|CTRL|DATA|CRC|SEQ over N lanes per tick)
                      ->  Line coding: fec | plain
                      ->  Simulated PHY (UDP)  |  GPIO PHY (BeagleBone)
```

**Frame:**
- SYN: 4 ticks of 1010.
- SFD: `0xB3`.
- CTRL (4 bits): 1 DATA, 2 ACK, 3 NACK, 4 START, 5 END, 6 PING, 7 PONG.
- DATA: 8 bits.
- CRC-8: over `[CTRL<<4 | SEQ, DATA]`.
- SEQ: 4 bits.

With CLK + 2 lanes, a frame is 20 ticks.

**Messages:** `START(encoding) → one DATA frame per byte → END(length mod 256)`.
- One byte per frame (the spec fixes DATA at 8 bits), so an error costs one frame, not the whole message. That's link-layer ARQ, not IP fragmentation.
- Efficiency is about 10%: an 80-bit frame + ACK carries 8 useful bits.

**Link:**
- Stop-and-wait, giving up after 8 retries.
- The ACK timeout adapts to the peer's clock as measured from its edges.

**Heartbeat:**
- PING/PONG every ~1 s.
- They carry the sender's CRC variant and are always checked with SMBUS, so mismatched settings get reported.
- UI status: 🟢 connected, 🟡 receive only, 🔴 no signal.

**Known v1 weaknesses (still open):**
- **SYN/SFD false lock.** With 2 lanes, junk ending in `11 00 10` right before a SYN can lock early (about 1 in 64). ARQ recovers it. The test uses a seeded random generator (`tests/test_stack.py`). Changing the SFD is a design choice that was left open.
- **Pause-and-resume** (proposed 2026-10-29, not built): after 8 failed retries the message is dropped instead of waiting for the link to come back.
- **GPIO PHY never tested on a real BeagleBone.**

### v2: Manchester + XOR parity (2026-11-04)
Code: `phychat/linecode.py` (`FecCode`, `CodedPhy`). Design: `docs/diseno_canales.xlsx`.

- **Channels per direction:** CLK, D0, D1, P.
- **Symbol** (4 samples per tick):
  - bit 1 = `0011`, bit 0 = `1100` (a flip in the middle of the tick);
  - CLK = `1100`;
  - **any other pattern = erased (E)**. A hand gives `0000` and IR gives `1111`, so the receiver knows *which* lane is broken.
- **Parity:** P = D0 ⊕ D1, so the 1s across the three lanes always add up to an even number. One E is rebuilt as the XOR of the other two lanes (like RAID-5).
- **History:** a lane erased within the last K=8 ticks is a *suspect*. If parity fails with nothing erased and there is exactly one suspect, that lane is flipped. This handles noise that happens to look like a valid symbol (2 of 16 patterns).
- **Clock loss:** the mid-tick flips on the data lanes still give timing. In the simulator, timing is free (one datagram per tick).
- **CRC-8 + ACK/NACK** checks the frame after correction. Two lanes erased at once → LOST → NACK → retransmission.

**Excel sheets** (`diseno_canales.xlsx`):
- Léeme;
- 1 Símbolo: 16 patterns → decode;
- 2 Paridad: encode, rebuild, ambiguity;
- 3 Casos: 25 hand-written cases vs formulas, 25/25 match;
- 4 Trama: 'h' = 0x68, CRC 0x48, 20 ticks, configurable interference;
- 5 Señal: logic-analyzer view;
- 6 Exhaustivo: 576 single-channel cases.
  - CLK: 72/72 delivered with an ACK.
  - D0, D1, P: 68 ACK + 4 NACK without history, 72/72 with history.
  - **Accepted with wrong bits: 0.**

It was verified with the Python `formulas` library: 13,645 formulas, 0 errors.

⚠️ **The generator scripts (`build_xlsx.py`, `verify_xlsx.py`) lived in a temporary scratchpad and are gone.** The .xlsx is the only copy: edit it in Excel, or build v5's workbook from scratch.

**Simulator results:** D1 blocked for the whole of "hola mundo ñ😀".
- `fec`: delivered, 0 retransmissions, 380 ticks rebuilt.
- `plain`: failed after 8 retries.

**UI:**
- Channel panel with ✋ block / 🔦 IR / 〰 noise buttons per channel, and a health dot (ok / flaky / down).
- 🔬 Oscilloscope: sent vs received waveform, the 4 read points, and the decoded `1` / `0` / `E→x` per tick. It works only in the simulator, which knows the clean signal.

**v2 limits:**
- 2 lanes erased at once → retransmission.
- GPIO stays `plain`: it would need 4× sampling and timing recovery.
- Skew between media must be well under a quarter tick. For example, sound travels about 3 ms per metre.

---

## 7. Designs on paper (v2b → v4)

### v2b and v2c (2026-11-05): after "more than one channel at once"
- **Why one P can't fix two:** with `D0 = E, D1 = E, P = 1`, both (0,1) and (1,0) fit. One equation can find only one unknown.
- **v2b, ARF fallback (WiFi):**
  - FAST mode: D0 = a, D1 = b, P = a⊕b.
  - SAFE mode: D0 = D1 = P = a; take any lane that isn't E. That is *not* a vote, because Manchester already says which lanes are broken.
  - Every frame's SYN/SFD is always sent SAFE, and **the SFD value announces the mode**, like WiFi's SIGNAL field.
  - Switch to SAFE on a NACK, a timeout, or a report of "2 lanes down"; return to FAST after 10 good frames.
- **v2c:** five lights `a, b, a, b, a⊕b` survive any 2 broken.

### v3: GF(16) "RAID-6" (2026-11-05)
- The idea came from "we validate horizontally (across lanes) but not vertically (over time)".
- **Adding a vertical parity row doesn't help:** a dead lane kills its own column, check bit included.
- **Vertical:** group 4 ticks, so each lane carries a number from 0 to 15. **Horizontal:** two equations, `P = D0 + D1`, `Q = D0 + 2·D1`, in GF(16).
- GF(16) arithmetic:
  - `+` is XOR;
  - `×2` = shift left, and if a bit falls off the top, XOR with `0011`;
  - ÷2 = ×9, ÷3 = ×14.
- 'h' → D0=6, D1=8, P=14, Q=5. With D0 and D1 both lost: `P+Q = 3·D1 = 11 → D1 = 8, D0 = 6`.
- Verified: 1536/1536 recoveries correct.
- **On hold:** D0 and D1 still carry different data, which is the professor's serial critique #2.

### v4: FSK + line mod 5 (2026-11-05)
**Frequency carries the value.**
- In each CLK window, a channel blinks 1–5 times, which means value 0–4.
- 0 blinks (hand, IR) or uneven spacing (flicker) means dead.

**The data is a line.**
- A nibble becomes `a = nibble // 4`, `b = nibble % 4` (2 bits each).
- Channel x ∈ {1,2,3,4} shows `y = a + b·x + hop(k, x)` (mod 5).
- No channel carries "a bit"; each one carries a view of the whole nibble.

**Decode:** any 2 points give the line.
- `b = (y2 − y1)/(x2 − x1)`, `a = y1 − b·x1` (mod 5).
- Division mod 5 is a 4-entry table: ÷2 = ×3, ÷3 = ×2, ÷4 = ×4.
- The other points must lie on the line. If one doesn't, it is the lying channel and gets corrected.

**Hop offset:** `hop(k, x) = x² + k·x + 2k (mod 5)` changes with every symbol k.
- The x² term means **the same reading on every channel is never valid** (verified). That blocks a lamp flickering on all the sensors.
- Like WiFi's scrambler, and like Bluetooth frequency hopping.
- ⚠️ **Correction:** the chat examples on 2026-11-05/08 used a second-window offset row `(3,0,2,4)`. That row is itself a line, which breaks this guarantee. Use the formula above.

**Worked example: 'h' = 0x68.** Values come from `experiments/line_mod5.py`.

| symbol | sends | ch1 | ch2 | ch3 | ch4 |
|---|---|---|---|---|---|
| k=0 | 6 (a=1, b=2) | 4 | 4 | 1 | 0 |
| k=1 | 8 (a=2, b=0) | 1 | 0 | 1 | 4 |

**Budget:** `dead + 2·lying ≤ channels − points the shape needs`.
- A line needs 2 points: with 4 data channels it survives 2 dead or 1 liar.
- Mod 5 allows up to 5 channels (x = 0..4). For 6–7 channels, use mod 7 (7 frequencies).

**Shape = coding rate (like WiFi):**

| Shape | Points needed | Bits per symbol | With 4 channels, can die |
|---|---|---|---|
| flat `y = a` (= the base test) | 1 | 2 | 3 |
| line `y = a + bx` | 2 | 4 | 2 |
| parabola `y = a + bx + cx²` | 3 | 6 | 1 |

**Surviving with 1 channel alive:**
- **Dead channels:** possible with flat mode (half speed), guaranteed by the math.
- **Lying channels:** counting alone can't do it. If 3 channels agree on a wrong value, nothing tells you they are the liars. The fix is to **make lies look like deaths**:
  1. a strict frequency check (evenly spaced edges);
  2. hop offsets, so random liars don't agree with each other;
  3. **CRC-aided decoding** (as in 5G): try the candidates and keep the one whose CRC passes.

  This is a probability, not a guarantee, and it doesn't stop an attacker who knows the hop sequence.
- The receiver reports in its ACK how many channels are alive, and the sender picks line or flat. This is rate adaptation, not block retransmission.

**Decoder policy, measured** (`line_mod5.py`): with **2 lying channels and none dead**:
- the "fix 1 liar" decoder accepts wrong data in **2160 of 7680 cases (28%)**;
- a **detect-only** decoder accepts **0**.

So it's a choice: correct 1 liar, or detect 2 liars and send a NACK. Correction is only safe if the frequency check turns most lies into deaths.

**Timing at a 1 Hz CLK:**
- Windows are 1 s, so blinks run at 1–5 Hz: the fastest is 0.1 s on, 0.1 s off.
- The receiver reads each sensor about 40 times per second.
- **A vibration motor at 5 Hz needs testing.**
- One character takes about 15 s including the ACK. The fastest blink is 5 × CLK.

**If the CLK is lost:** every channel starts each window ON, so all alive channels rise together at the window start.
- With ≥2 alive channels, that works as backup timing.
- With 1 alive, it's fragile.

**Another idea:** a CLK window with **2 blinks marks the start of a frame**, because the CLK is safe.

---

## 8. v5: the current direction (2026-11-08)

**Professor's point:** the frequency already carries its own timing, so channels don't need the CLK to delimit symbols. **Each channel runs on its own.**

### Rules
- **Symbol:** `CYCLES` (currently 2) cycles of the channel's own frequency. A high value is fast and short; a low value is slow and long.
- **Value → frequency:** a table **per channel**, so each medium gets a band it can handle. For example, LED 10–50 Hz, buzzer 5–25 Hz, vibration 1–5 Hz.
- **Math across channels:** unchanged from v4 (line + hop offsets), but points are matched by **symbol number k** (1st, 2nd, …), not by time window.
- **Receiver, per channel:**
  1. timestamp the turn-ons;
  2. two equal periods at an allowed frequency make a valid symbol;
  3. uneven periods, or no edge for longer than the slowest allowed period, mean dead;
  4. number the symbols.
- **Receiver, across channels:** solve symbol k **as soon as any 2 channels have delivered it**. Later points confirm it, or reveal a liar. The CRC is the final check.
- **CLK becomes a pilot,** like WiFi's pilot subcarriers or FM stereo's 19 kHz pilot tone. Frequencies are measured relative to it, which cancels timer drift between the boards. The receiver *can* ignore it and use its own timer. It stays because the spec requires a clock channel.
- **Frame start:** each channel announces its own start, e.g. with a reserved frequency held for 2 cycles.

### 'h' with all 4 channels at 1–5 Hz
From `python3 docs/experiments/async_timeline.py`:
```
ch1      ‾‾__‾‾__‾‾‾‾‾_____‾‾‾‾‾_____
ch2      ‾‾__‾‾__‾‾‾‾‾‾‾‾‾‾__________‾‾‾‾‾‾‾‾‾‾__________
ch3      ‾‾‾‾‾_____‾‾‾‾‾_____‾‾‾‾‾_____‾‾‾‾‾_____
ch4      ‾‾‾‾‾‾‾‾‾‾__________‾‾‾‾‾‾‾‾‾‾__________‾‾__‾‾__
         (1 character = 50 ms)

symbol 0: solved 0.40s, confirmed 1.00s   ch1=4 (0.40s)  ch2=4 (0.40s)  ch3=1 (1.00s)  ch4=0 (2.00s)
symbol 1: solved 2.00s, confirmed 2.40s   ch1=1 (1.40s)  ch2=0 (2.40s)  ch3=1 (2.00s)  ch4=4 (2.40s)
all symbols solved at 2.00s; if every channel waited for the slowest one: 4.00s
```

- With channels 2 and 3 dead (`--dead 2,3`), it is solved at 2.40 s, with no confirmation point.
- With two fast channels (`--hz 1:10-50 2:10-50`), "hi" is solved at 0.51 s; lockstep would take 6.0 s. **The fastest 2 channels set the pace.**

The chat on 2026-11-08 showed 'h' solved at 1.4 s. That number used the flawed linear offset row (see §7); the corrected value is 2.0 s.

### Known costs of v5
- A channel interrupted **mid-frame** loses its place (which symbol number it is on). For now it sits out until the next frame and counts as dead.
- Speed depends on the data, because low values are slow frequencies. The hop offsets mix values, so it averages out.
- Each channel needs its own start marker.

---

## 9. Decisions

| # | Decision | Why | Date |
|---|---|---|---|
| D1 | FEC **adds to** CRC-8 + ACK/NACK; it doesn't replace them | the spec's demo requires the CRC → NACK → retransmit path | 11-04 |
| D2 | A broken channel must read as **dead (erasure)**, never as valid data | a known-dead channel costs 1 spare; an unknown lie costs 2. Achieved by self-validating symbols: Manchester (v2), clean frequency (v4/v5) | 11-04 |
| D3 | **No majority vote.** Redundancy comes from equations (parity, polynomials); copies are used only as "take any channel that isn't dead" | the professor rejected voting | 11-04 |
| D4 | Interference model: **CLK safe; any number of data channels** blocked, saturated, noisy or flickered at once | the professor | 11-05 |
| D5 | Block retransmission (the other team's idea): **only if needed** | Cruz | 11-05 |
| D6 | GF(16) / RAID-6 **on hold** | it still splits different data across lanes | 11-05 |
| D7 | Keep the math school-level for Excel: **mod 5** rather than GF(16) | Excel `MOD()`, easy to explain and defend | 11-05 |
| D8 | **Design in Excel first** (truth tables, expected outputs), code after | the professor's workflow | 11-04 |
| D9 | Changing the code (line or flat) as channels die is OK; it's adaptation, not retransmission | survive down to 1 alive | 11-05 |
| D10 | **The CLK channel stays** (the spec requires it), but in v5 it is a **pilot reference, not a gate** | the professor: the clock can be ignored, channels are independent | 11-08 |
| D11 | v2 stays in the code as the working baseline until v5 is confirmed | always have something that runs | 11-08 |
| D12 | Cite real protocols when defending: Manchester/802.3, RAID-5/6, Reed–Solomon, FSK, WiFi (ARF, pilots, scrambler, Block ACK), Bluetooth hopping, JT65 (MFSK + RS), 5G CRC-aided decoding | the professor wants ideas from real protocols | 11-05 |

---

## 10. Open questions and next experiments

1. **Confirm v5 with the professor.** Is "CLK = pilot, channels independent" what he meant? Is matching symbols by number OK?
2. **Symbol definition.** How many cycles per symbol (2?) and what duty cycle? How does a lost or extra edge affect the cycle count and symbol boundaries?
3. **Mid-frame dropout.** Options: sit out until the next frame; a per-channel resync marker; estimating the symbol number from pilot time.
4. **Measure each medium.** Find the fastest clean on/off rate of each one (LED → phototransistor, buzzer → mic module, vibration motor → sensor), then derive each channel's frequency table.
5. **Frame mapping.** The 24-bit body is 6 nibbles: 6 symbols per channel in line mode, 12 in flat mode. Where does SYN/SFD go: a per-channel tone, or a CLK pattern?
6. **Feedback.** How does the ACK report "N channels alive", and how does the sender pick line vs flat?
7. **Fake-valid probability** under fast flicker. Needs a simulator with per-channel edges.
8. **Decoder policy.** Correct 1 liar or detect 2 (see §7)?
9. **Simulator for v5.** `SimPhy` / `CodedPhy` assume lockstep ticks (one datagram per tick for all channels). v5 needs a per-channel, timestamped edge stream and assembly by symbol number. Link, presentation and app can stay as they are.
10. **Excel for v5:** per-channel frequency tables, the line/flat encode tables, "2 points → line" for every pair, liar cases, the symbol-number timeline, a full frame.
11. **Hardware:** edge timestamping (Arduino interrupts, or BeagleBone GPIO), 3.3 V level shifting, and the never-tested GPIO path.
12. **Still open from v1/v2,** if v2 stays as a fallback: the SFD overlap, and skew between media.
13. **Unexplored lead:** the time × frequency permutation grid (power-line M-FSK). It checks rows and columns.

---

## 11. Files and how to run

Paths are relative to `PROJECT03/`. Code lives in `phy-chat/`, context in `docs/`.

| Path | What |
|---|---|
| `phy-chat/phychat/linecode.py` | v2 line coding (`FecCode`, `PlainCode`, `CodedPhy`) |
| `phy-chat/phychat/phy_sim.py` | UDP simulated medium + interference (`block`, `saturate`, `noise`) |
| `phy-chat/phychat/frame.py`, `link.py`, `crc8.py`, `presentation.py`, `app.py`, `web.py` | frame, ARQ, CRC, encodings, app glue, web server |
| `phy-chat/phychat/static/index.html` | chat, LOG, channel panel, oscilloscope |
| `phy-chat/tests/test_stack.py`, `test_fec.py` | 29 tests |
| `docs/diseno_canales.xlsx` | v2 design workbook (generator lost) |
| `docs/experiments/raid6_gf16.py` | v3 check |
| `docs/experiments/line_mod5.py` | v4/v5 math: erasures, liars, the same-reading guard, flat mode, decoder policy |
| `docs/experiments/async_timeline.py` | v5 timing: per-channel schedule, when each symbol is solved; options `--dead`, `--hz`, text |
| `docs/experiments/matrix_code.py` | v6 check (one byte per matrix) |
| `docs/experiments/matrix_nibble.py` | v6b check (one half byte per matrix): the accepted design |
| `docs/experiments/flicker_nibble.py` | v6b against fast flicker; three kinds of reading; D1 inverted |
| `docs/protocol.md` | full spec of the accepted protocol (the original; `docs/protocolo.md` is its Spanish translation) |
| `docs/matrix_v6b_es.csv`, `docs/matrix_v6b.csv` | the tables shown to the professor (Spanish / English) |

```
cd phy-chat
./run_sim.sh                         # A → http://localhost:8081, B → :8082 (UDP 47001/47002)
./run_sim.sh --coding plain          # v1, for comparison
python3 -m unittest -v tests.test_stack tests.test_fec
cd ..
python3 docs/experiments/matrix_nibble.py
python3 docs/experiments/line_mod5.py
python3 docs/experiments/async_timeline.py hi --dead 2,3 --hz 1:10-50
```

For live tests, use other ports (e.g. web 18081/18082, UDP 47101/47102) and stop the processes by PID. Cruz runs his own servers.

---

## 12. Glossary

- **Erasure / dead:** a channel that the receiver *knows* is broken. It costs 1 spare.
- **Error / lying:** a channel that looks valid but is wrong. It costs 2 spares: one to notice, one to locate.
- **FEC:** forward error correction, recovering data by an equation without retransmitting.
- **ARQ:** retransmission (ACK/NACK).
- **Manchester:** a bit is a transition in the middle of the symbol; no transition means the channel is broken.
- **FSK / M-FSK:** the value is a frequency (with M possible frequencies).
- **mod 5:** clock arithmetic with 5 hours (5 → 0, −1 → 4). Division uses the inverse table.
- **GF(16):** 4-bit arithmetic where + is XOR. Used by Reed–Solomon and RAID-6.
- **MDS:** with k data points and n channels, *any* k channels are enough. Best possible.
- **Coding rate:** useful / sent. Flat 1/4, line 2/4, parabola 3/4 (with 4 channels).
- **Pilot:** a known reference signal for timing and frequency (WiFi pilot subcarriers).
- **ARF:** Auto Rate Fallback, WiFi's slow-down-when-bad rule.
- **Block ACK:** WiFi 802.11n acknowledges many subframes with one bitmap and resends only the missing ones.

---

## 13. Professor's written feedback on v4 (received 2026-11-11)

Email after reviewing the "window + mod 5 + blink rate" proposal. Key points:

- The project is **not a serial protocol**. It must be a **hybrid of parallel and serial processing**. A design that only serializes gets **no grade**, even if it works for the user.
- "Multiplying serial processes, or presenting a serial solution dressed up as parallel, is not parallel processing." AI tools keep proposing serial designs.
- The design initiative must come from the student. Give the AI the context, conditions and criteria (e.g. in Excel); don't let it decide what to implement.
- **The frame in the PDF is not the physical-layer protocol.** It is only the bit structure to transmit. The CRC validates after the whole frame arrives. The protocol must **validate bits during transmission**, like the class example.
- **The base case from class (last three weeks): "validación de canales y recuperación de bits mediante matrices"**, at an initial **1 Hz**, configurable up to the project's calculated maximum capacity. The LOG is shown at 1 Hz "because we are humans".
- Implement the base case first, understand it, then strengthen it with our own mathematically justified proposal. No need to start from zero.
- The email had an image of another group's (wrong) approach, which we don't have.

Consequences:
- v4 and v5 over-read "frequency carries information". In the email, frequency is the **tick rate** (1 Hz, adjustable). The FSK direction is dropped unless the base case says otherwise.
- **We still don't have the base case itself.** Cruz doesn't remember the whiteboard example. Recovering it (notes, classmates, recordings) is the first step.
- Candidate readings of the base case and three directions built on matrices are in the chat of 2026-11-11: a per-tick check matrix (syndrome names the bad channel), a time × channel matrix with row + diagonal checks, and a channel-state matrix over time.

---

## 14. v6: one byte = one matrix (2026-11-11)

Cruz confirmed two things: the professor described the base case as XOR with **horizontal and vertical validation** (v2 had only the horizontal one), and the image in his email was a screenshot of our own v4 proposal. Nobody has the base case in writing, so v6 is our reading of it plus our own strengthening (the diagonal).

**The matrix.** Rows are ticks (serial), columns are channels (parallel). Channels per direction: CLK + D0 + D1 + P + Q.

```
            D0   D1   P    Q
  tick 0    d    d    p    q
  tick 1    d    d    p    q
  tick 2    d    d    p    q
  tick 3    d    d    p    q
  tick 4    v    v    v    v      vertical-check tick
```

**Three families of XOR equations** (each must come out even):
- horizontal: `P[i] = D0[i] ^ D1[i]`, checked at every tick (bit validation during transmission);
- vertical: `V[c]` = XOR of that channel's 4 bits, checked when the block ends (channel validation);
- diagonal: `Q[0] = D0[0]^P[1]`, `Q[1] = D0[1]^D1[0]^P[2]`, `Q[2] = D0[2]^D1[1]^P[3]`, `Q[3] = D0[3]^D1[2]`. Row + diagonal is RDP, the RAID-6 scheme.

**Decoding:** a cell the receiver knows is dead is an unknown. Any equation with exactly one unknown gives that bit; repeat. If equations fail with nothing dead, the crossing of the failing horizontal and vertical checks is the lying bit.

**Verified by brute force** (`experiments/matrix_code.py`):

| Case | Result |
|---|---|
| any 2 of the 4 channels dead for the whole byte | rebuilt, 1536/1536 |
| 1 lying bit, nothing dead | located and fixed, always |
| 1 whole channel lying in any way (not flagged dead) | found and fixed, 4588/4588 |
| 1 channel dead + 1 lying bit elsewhere | fixed, 3120/3120 |
| 2 channels dead + 1 lying bit | never accepted as wrong data (detected) |
| 3 channels dead | lost (expected: not enough equations) |
| minimum distance | 6 |

**Cost:** 5 ticks per byte (20 bits on the channels for 8 data bits). At 1 Hz, 5 s per byte.

**Open:**
- How the receiver knows a cell is dead. Current plan: keep v2's Manchester symbol (4 reads per tick). Without it, the matrix alone still fixes 1 lying channel, but not 2 dead ones.
- How the receiver finds the start of a matrix. Idea: the CLK marks it, since the CLK is never interfered.
- Whether SYN/SFD also travel inside matrices.
- Not yet shown to the professor.

## 15. v6b: one nibble = one matrix, one surviving channel is enough (2026-11-11)

**Why:** Cruz's reading of the professor is that he will block more than one channel, and the design should hold until only one data channel is left alive, with the damage limited when that last one is interrupted too. v6 stops at 2 dead.

**The rule that forces the cost:** if one channel alone must be enough, that channel alone must carry everything. So the same 5×4 matrix now carries 4 bits instead of 8. More channels would not make it faster, only add cross-checks.

**The matrix** for a nibble `a b c d` (every cell is one XOR equation in a, b, c, d):

```
            D0        D1       P        Q
  tick 0    a         b        a^b      a^b^c
  tick 1    b         c        b^c      b^c^d
  tick 2    c         d        c^d      a^b^c^d
  tick 3    d         a^b      a^b^d    a^c^d
  tick 4    a^b^c^d   a^c^d    b        a^b^d     vertical check (XOR of the 4 cells above)
```

- horizontal: `P[t] = D0[t] ^ D1[t]`, every tick, tick 4 included;
- diagonal: `D1[t] = D0[t+1]` and `Q[t] = D0[t] ^ P[t+1]`, for t = 0..2;
- vertical: `V[c]` = XOR of that channel's 4 cells.

The columns are windows of one sequence `s[k+4] = s[k] ^ s[k+1]` starting a, b, c, d (D0 at 0, D1 at 1, P at 4, Q at 10). The receiver keeps the cells that arrived and solves for a, b, c, d.

**Verified by brute force** (`experiments/matrix_nibble.py`, all 16 nibbles):

| Case | Result |
|---|---|
| any 1, 2 or 3 channels dead for the whole matrix | rebuilt, always |
| 1 channel alive and it loses 1 tick | rebuilt, 320/320 |
| 1 channel alive and it loses 2 ticks | lost, known to be lost (640/640 asked again) |
| 2 channels alive, each loses 1 tick | rebuilt, 2400/2400 |
| 2 channels alive, each loses 2 ticks | rebuilt 8976/9600, rest asked again |
| all 4 channels dark for 1, 2 or 3 ticks in a row | rebuilt, always |
| 1, 2 or 3 lying bits anywhere, nothing dead | fixed, always |
| 1 whole channel lying any way | fixed, 1984/1984 |
| 1 dead + 1 channel lying any way | fixed, 5952/5952 |
| 2 dead + 1 channel lying any way | fixed 3072, asked again 2880, wrong 0 |
| 2 channels lying any way, nothing dead | fixed 12000, asked again 80256, wrong 0 |
| 3 dead + the last one lying any way | wrong nibble accepted 960/1984: only the frame CRC-8 catches it |
| minimum distance | 8 |

**Cost:** 10 ticks per byte (v6: 5). A 40-bit frame is 10 matrices = 50 ticks = 50 s at 1 Hz.

**Mitigation when the last channel is hit too (proposed, not built):**
- The CLK is never interfered, so the receiver never loses its place and knows exactly which matrices of the frame were lost.
- It keeps every cell that did arrive. A repeat of the matrix fills the holes; the two copies are combined, not replaced.
- The NACK names the lost matrices and only those are repeated (5 s each at 1 Hz instead of 50 s). This is the "block retransmission" the professor called optional.
- The frame CRC-8 stays as the last check for the one case the matrix cannot see (last channel lying with a valid-looking column).

**Open:** v6 (fast, 2 dead) and v6b (safe, 3 dead) use the same matrix shape, so a FAST/SAFE switch is possible later. Not decided, not built, not shown to the professor.

## 16. Professor's feedback on v6b (WhatsApp, 2026-11-12)

Cruz showed him the v6b matrix (the CSV in `docs/matrix_v6b_es.csv`). The feedback was positive.

- "si esta bien / pero esto es para un sentido, verdad no existe congestion de ambas vias enviando al mismo tiempo verdad?" Reading: he accepts the matrix and asks about both directions sending at once. Our answer: each direction has its own 5 channels and its own CLK, so the medium has no collisions; what is shared is that each direction carries its own data plus the ACK/NACK for the other side.
- "listas de espera necesita el protocolo / como CC7 / priority etc". Reading: the protocol must have explicit queues with priorities, in the style of the operating systems course (ready queue, waiting list, priority, starvation).
- "no lo haremos a velocidades ultra altas / toda la evaluación a 1Hz". The whole evaluation runs at 1 Hz.

**Consequences:**
- The queue design is now part of the protocol, not an implementation detail. The code already has a 2-level priority queue (ACK/NACK/PONG ahead of data) in `phychat/link.py`; it needs to be made explicit and extended (retransmissions, heartbeat, the list of frames waiting for an ACK).
- At 1 Hz a v6b frame is 50 s and its ACK another 50 s. A one-character message is START + DATA + END = 3 frames = about 5 minutes. Time per frame is now the main design pressure, not the Hz limit of the board.
- Open idea: a frame-start mark on the CLK would let a short high-priority frame (ACK/NACK) interrupt a data frame at a matrix boundary (wait of 5 s instead of up to 50 s). Not decided.

## 17. Queues added to the proposal (2026-11-13)

Cruz's decision: add the queues to the proposal ignoring the 1 Hz time cost; optimise later if the professor accepts the complete picture. Still description only, no code.

Sections 13–17 of `docs/matrix_v6b_es.csv` (and the English `matrix_v6b.csv`) now hold:
- the queues on each board (outbox, ready, transmitter, waiting, repair, inbox) with their operating-systems equivalents;
- ready-queue priorities: 0 ACK/NACK, 1 retransmission, 2 START/DATA/END, 3 PING/PONG;
- frame states NEW → READY → RUNNING → WAITING → DONE, back to READY level 1 on NACK or timeout, FAILED after 8 retries;
- rules: no preemption, stop-and-wait, timeout = 2 frame times, whole-frame repeat with the receiver keeping good cells, SEQ for duplicates, aging after 3 turns, PING only when idle;
- an 8-turn trace of A sending 'h' and B sending 'k' at once with one interfered frame.

Already in `phychat/link.py`: the 2-level priority queue, stop-and-wait, the timeout, 8 retries, SEQ duplicates. New on paper: the retransmission and heartbeat levels, aging, the repair buffer.

**Deferred as optimisations:** an ACK interrupting a data frame at a matrix boundary; repeating only the failed matrix; dropping SYN/SFD from the matrices.

## 18. Improvement candidates for v6b, time aside (2026-11-13)

Tested with `experiments/flicker_nibble.py` (flicker = 4 random reads per tick, 20000 matrices per case). Nothing here is decided or shown to the professor.

**Finding:** the v6b receiver as described believes every valid-looking cell, and a flickering channel produces a valid-looking random bit in 2 ticks out of 16.

| Channels | Receiver as described | "Strict" receiver |
|---|---|---|
| 2 flickering, 2 clean | 93.6% recovered, 0 wrong | 100% recovered |
| 3 flickering, 1 clean | 80.6% recovered, 2.90% wrong | 100% recovered |
| 2 flickering, 1 dead, 1 clean | 91.7% recovered, 0.68% wrong | 100% recovered |
| 4 flickering | 10.95% wrong | 0.08% wrong, rest asked again |

Wrong = accepted at matrix level; the frame CRC-8 then catches 255 of 256.

**Candidates, in the order I would add them:**
1. **Three kinds of reading** (strict receiver): valid (`0011`/`1100`), blocked (`0000` hand, `1111` IR), noisy (any other pattern). A channel that showed noise in a matrix is not believed for that matrix; a channel that was only blocked keeps its good ticks, so the "last channel loses one tick" repair still works.
2. **D1 sent inverted.** Without it the all-zero matrix is valid, so the same reading on all four sensors can pass as half byte 0000 (1 of 32 patterns). With D1 inverted none passes and the closest is 5 cells away.
3. **Channel report to the sender:** ACK/PONG carry which channels the receiver sees blocked or noisy (4 free bits in DATA). For the LOG now, for adapting later.
4. **Channel memory across matrices:** a channel that was noisy stays distrusted for the next few matrices. Not tested.
5. **Media per channel:** spread the 4 data channels over at least 3 media so one kind of interference cannot reach all of them. Hardware choice, not protocol.

**Decision (Cruz, 2026-11-13):** candidates 1–3 of this section go into the proposal now (three kinds of reading, D1 inverted, channel report in ACK/PONG); 4 and 5 later. They are in sections 18–19 of the CSVs, and the D1 row of the signal table (section 3) now shows the inverted waveform.

## 19. Protocol shape added to the proposal (2026-11-13)

Sections 20–22 of the CSVs: the life of the link (NO SIGNAL → HELLO → RX ONLY → IDLE ⇄ TRANSFER, with the PING/PONG content), the message (START / DATA per byte / END and its rules), and units and constants (read < tick < matrix < frame < message; timeouts, retries, capacity formula).

These describe what `link.py` and `app.py` already do (states connected / rx_only / down, hello with the CRC-8 id, alive window = 2.5 × ping interval, START/DATA/END). New on paper only: the IDLE/TRANSFER names, the channel-report bits, aging.

Still missing from the proposal: what the CLK signals mean beyond tick and matrix start (silence, frame start), and the LOG line format for the matrix.

## 20. Professor accepts the complete proposal (2026-11-14)

His verdict on the CSV with queues, reinforcements and protocol shape (sections 1–22): "even too complex, but it is ok". The design phase is closed; next is development and building the circuits.

Plan agreed with Cruz (see chat of 2026-11-14): software first in the simulator (matrix coding, then queues), then the 4-reads-per-tick GPIO PHY on the BBB with wires, then swap wires for real media one channel at a time. Open: what the second board is, and which media/parts.

## 21. Full protocol specification written (2026-11-14)

`docs/protocol.md` (English original; `protocolo.md` is the Spanish translation) is now the single reference for the protocol as accepted: channels, symbol, matrix, receiver decision rules, cases, frame, link, queues, message, link life, constants, verified results, implementation status, open points, and an annex with the 16 matrices. Build from that file. Details not yet confirmed with anyone are marked "(proposed)" in it: frame start from CLK silence, the repair-merge rule, the bit order of the channel report, NACK carrying the report.

## 22. Hardware: parts on hand and build plan (2026-11-14)

**Boards:** two BeagleBone Black (one with Cruz now, the second later). Until then both nodes run on one BBB, each with its own pins; moving to two boards only changes the pin config file. Light and sound need no shared ground between boards.

**Media parts on hand (Cruz's list):**

| Part | Count | What it is | Notes |
|---|---|---|---|
| KY-008 | 2 | laser emitter module | 5 V module: drive through a transistor from the 5 V supply, never straight from a GPIO pin |
| DL-591 IR 5mm LED | 4 | **unconfirmed**: probably IR receivers (phototransistors) | no datasheet found by that name; check lens colour (receivers usually dark) or phone camera (an emitter glows purple, a receiver shows nothing) |
| IR 5mm LED emitter | 2 | IR emitter | needs a transistor and a resistor |
| KY-038 | 2 | microphone module, LM393 comparator, digital out (DO) | power from 3.3 V so DO is BBB-safe; measure DO first; its DO may pulse with the sound instead of holding a level |
| Buzzer | 2 | sound emitter | **unconfirmed** active or passive: apply 3.3 V; a beep = active (board only switches it), a click = passive (board must make the tone) |

**Shortfall:** the parts make 3 channels per direction (1 laser, 1 IR, 1 sound); the accepted design (`protocol.md`) needs 5 per direction (CLK, D0, D1, P, Q). To buy: 2 more KY-008, 2 more IR emitters, 4 more light receivers like the DL-591 (if they are receivers), plus about 10 NPN transistors (2N2222 or similar) and resistors; maybe an LM393 for the light receivers. Fallback without buying: CLK + D0 + D1 only, which survives just 1 blocked channel and is a different design the professor would have to see again (not recommended).

**Proposed media layout per direction:** CLK and D0 on laser, D1 and P on IR, Q on sound, so a hand over all the light still leaves Q alive. Open risk: laser and IR are both light; ask the professor whether they count as two media.

**Circuit rules:**
- 3.3 V only into the BBB; every sensor output at 3.3 V or through a divider.
- Never power an emitter from a GPIO pin: a transistor and its own supply for each.
- A diode across any motor or coil (none planned now).
- Sound both ways at once: each buzzer close to its microphone (foam or a tube), sensitivity turned down, so a board does not hear its own buzzer.
- At 1 Hz each medium must follow a change every 250 ms (a quarter tick).

**Build order:**
1. Matrix in the simulator (5 channels, three kinds of reading, D1 inverted, CLK mark, LOG/oscilloscope). 
2. Queues (4 levels, aging, repair buffer, channel report).
3. GPIO PHY with 4 reads per tick.
4. Both nodes on the BBB over 10 plain wires: the checkpoint that separates code bugs from circuit bugs.
5. Replace one wire at a time with a real channel; test each with a blink script and the logic analyzer.
6. Rehearse the demo (hand, IR pointer, flicker) and write the per-medium wiring document for the ZIP.

Meanwhile Cruz builds and tests one channel of each medium on a breadboard.

**Waiting on Cruz:** what the DL-591 is, whether the buzzers are active, whether the extra parts can be bought.

## 23. Language of the docs (2026-11-15)

Cruz's rule: documentation is written in English. Spanish only when he asks for it. Existing Spanish files: `matrix_v6b_es.csv` (shown to the professor) and `protocolo.md` (translation of `protocol.md`, which is the original). If the spec changes, change `protocol.md` first and then the translation.

## 24. Claude context versioned with the project (2026-11-15)

Cruz wants all the context Claude kept outside the project (its memory folder) versioned here, so the work moves to another machine with the folder. Modelled on the IOValence repo: a root `CLAUDE.md` (auto-loaded: overview, quick reference, index of context files, rules, status tracker, decision log) and a `claude/` folder (`context.md`, `analysis.md`, `conventions.md`, `instructions/`). The project-relevant rules from Claude's memory (commit authorship, live-test ports, English docs, keep scripts in the project, build over theory, describe before building) are now rules in `CLAUDE.md`. Added `.gitignore`. Same day: `git init` (branch `main`, repo-local author `cruzambrociogl`, the Galileo account used for PROJECT02) and five first commits: assignment, phy-chat v2 stack, design history + experiments, v6b spec + CSVs, Claude context. Remote added the same day: `git@github-edu:cruzambrociogl/Proyecto3.git` (GitHub `cruzambrociogl/Proyecto3`, through the `github-edu` SSH alias).

## 25. First real channel: laser blinks from the BBB (2026-11-15)

DL-591 confirmed by Cruz as **IR receivers**. First hardware test: one KY-008 laser driven from the BBB, to prove the control path before the receiver.

- **Connection:** the Mac did not see the BBB over USB (no USB network, 192.168.7.2 and 192.168.6.2 silent). Ethernet to the router works: `debian@beaglebone.local` (192.168.2.2), with Cruz's SSH key already on the board. Image: Debian 10 Buster IoT 2020-04-06, kernel 4.19.94-ti-r42, Python 3.7.3; user `debian` is in the `gpio` group.
- **Circuit:** P8_7 → 1 kΩ → base of an NPN; KY-008 `S` to the Elegoo MB v2 5 V rail, KY-008 `-` to the collector, emitter to GND; Elegoo GND tied to BBB GND. The 5 V never touches a BBB pin.
- **Tool:** `phy-chat/tools/blink.py <tx> [--hz N] [--rx PIN]` blinks a pin and can print what a receiver pin sees.
- **Finding:** with P8_7 in `config-pin` mode `default`, the sysfs GPIO value toggled but the laser stayed off. After `config-pin P8_07 gpio` it lit and blinked at 1 Hz. So every pin we use must be set to `gpio` (outputs) or `gpio_input` / `gpio_pd` (inputs) first. The mode is lost on reboot, so `Pin` in `phychat/phy_gpio.py` now sets it when it opens a pin (outputs `gpio`, inputs `gpio_pd` so a loose input reads 0 like a blocked channel). Checked on the board: P8_7 reset to `default`, then `blink.py` switched it to `gpio` and the laser blinked; P8_17 opened as input became `gpio_pd`.
- **Next:** wire a DL-591 receiver to a 3.3 V input and run `blink.py P8_7 --rx <pin>`.

## 26. First light channel works: laser → DL-591 at 1 Hz (2026-11-15)

Test: `blink.py P8_7 --rx P8_17` (laser on P8_7 as in §25, receiver on P8_17), 1 Hz, read in the middle of each half period.

- **DL-591 alone is too weak for the red laser.** Wired as phototransistor + resistor to GND (output at the emitter), RX stayed 0. With 100 kΩ the output went from 0 V (laser off) to only 0.3 V (laser on), about 3 µA; the BBB needs > 2 V for a 1. The dark IR filter passes only a little of the 650 nm red. Answer to "can the IR receiver see the laser": yes, weakly, so it needs a gain stage.
- **Receiver circuit that works** (all from the BBB 3.3 V, so P8_17 can never see more than 3.3 V):

  ```
  P9_3 (3.3 V) ──┬──────────── DL-591 short leg
                 │             DL-591 long leg ──┬── base, NPN #2
              [10 kΩ]                            │
                 │                        [470 kΩ] (220 kΩ–1 MΩ works)
                 ├──── P8_17                     │
                 │                               │
           collector, NPN #2                     │
           emitter ──────────── P9_1 (GND) ──────┘
  ```

  The second NPN multiplies the DL-591 current about 100–200 times. Output is **inverted**: laser on → P8_17 = 0, laser off → P8_17 = 1. The code must invert this channel (the protocol already inverts D1, `protocol.md` §3).
- **First version without the base resistor:** laser-on reads were always right, but 7 of 28 laser-off reads came back 0. Likely room-light flicker amplified by the bare base (the errors came in a regular rhythm). Fix: a base-to-GND resistor (220 kΩ–1 MΩ) and a dark tube around the sensor, which blocks room light but lets the beam in. Cruz fitted both.
- **Result with both fixes:** a full minute at 1 Hz, every reading correct (inverted), no errors.
- **Speed:** `--hz 2` (a change every 250 ms, read 125 ms after it, the quarter tick the protocol needs at 1 Hz): about 85 s, every reading correct. `--hz 4` (read 62 ms after each change): about half the readings showed the previous state, so the receiver settles in roughly 60–125 ms. Enough for 1 Hz, not much margin beyond it.
- **Hand block:** with the beam blocked the receiver reads 1 (dark) whatever the laser does, which is the "blocked" case. A hand leaks between the fingers; use a card or book for a clean demo.
- **Room light:** in a later 1 Hz run, laser-off reads came back 0 ("lit") in short bursts about every 4 s, independent of the laser and of the hand. With the tube end fully covered, a whole run read 1 with no bursts, so the circuit is electrically clean and the bursts were light from the room getting into the tube (source not identified: something blinking or moving nearby). For the demo: longer tube, aim away from screens and lamps. The protocol's reading classifier would mark such bursts as noisy, but the channel should be clean before the matrix goes on top.
- **Next:** the IR LED → DL-591 channel; later, the receiver inversion in the GPIO PHY config.

## 27. Last protocol details closed; plan for the protocol document (2026-11-16)

Cruz wants a protocol document like the one made for PROJECT02 (`PROJECT02/splat-pyramid/protocolo-sp.pdf`: markdown → HTML → PDF with headless Chrome, Spanish, requirement table, diagrams, decisions, results, references). A document for the professor cannot carry "(proposed)" items, so the open ones were settled first. Cruz agreed:

1. **Frame start:** the `CLK` is silent between frames; the first tick after a silence is tick 0 of matrix 0.
2. **SYN and SFD stay inside the matrices** (matrices 0 to 3). The assignment requires the `SYN → SFD → CTRL → DATA → CRC` structure; taking them out is only a time optimization, left for later.
3. **Repair rule** (spec §8.7) and **channel-report bit order** (`D0 D1 P Q` = bits 3..0, also carried by NACK) as written.

Still open: the LOG line format (the document describes what a line contains, the exact format comes with the code) and the physical media.

**Risk found in the assignment PDF:** its table of suggested media lists "Luz / infrarrojo" as one row, so laser and IR may count as one medium (light). With the parts on hand that would be 2 media (light, sound) against a minimum of 3. A third medium (vibration, magnetic, mechanical) or the professor's answer settles it.

**Document plan:**
- Part 1, the protocol: complete now, from `docs/protocol.md`, with only script-produced numbers and the matrix called a design (not yet running).
- Part 2, the physical implementation (media, circuits, GPIO pins, wiring per medium, measured results): filled as channels are built; the final PDF for the ZIP comes after the hardware checkpoint (build step 4/5).
- English original first, then the Spanish version and the PDF from it.

**Same day, change of plan:** Cruz asked for one complete document instead of two parts. `docs/protocol-document.md` now holds the protocol plus the physical implementation as it stands (§15: boards, media, circuit rules, wiring of the built laser channel and of the planned IR and sound channels, GPIO, hardware measurements) and the demo plan (§16). Unbuilt parts are marked planned; it is updated as channels are built. Authors: Rosangela Rodriguez (22000127) and Cruz Ambrocio (20005588).

## 28. Five media and the P8 pin map (2026-11-16)

Cruz set the media: **laser, sound, IR, Hall (magnetic) and light** (light is a placeholder, the exact medium still to be chosen). Five channels per direction, five media, one each.

**Channel assignment (proposed by Claude, not yet confirmed by Cruz):** `CLK` laser (the only measured channel, fastest to settle, and the CLK is never interfered), `D0` IR, `D1` sound, `P` Hall, `Q` light. The data channels then have two light media and two that are not light: a hand or IR pointer over the light leaves sound and magnetism; noise at the microphone leaves the rest. Even if laser, IR and light count as one medium, light + sound + magnetism are three, which settles the risk in §27.

**Pins: P8 only, the same map on both boards** (Cruz's idea, checked): P8_3–6 and P8_20–25 are eMMC, P8_27–46 HDMI/LCD and boot pins, P8_1–2 GND; 14 GPIO stay free (P8_7–P8_19, P8_26) for the 10 needed.

| Channel | TX | RX |
|---|---|---|
| CLK laser | P8_7 | P8_17 |
| D0 IR | P8_8 | P8_18 |
| D1 sound | P8_13 (EHRPWM2B, for a passive buzzer) | P8_15 |
| P Hall | P8_9 | P8_16 |
| Q light | P8_10 | P8_26 |
| spare | P8_11, P8_12, P8_14, P8_19 (EHRPWM2A) | |

P8 has no power pins: 3.3 V from P9_3/4, 5 V from P9_7/8 or the external rail. P8_7/P8_17 keep the built laser channel. On one board (until the second BBB), node B goes on P9; that map comes with build step 3. The current `config/bbb_loopback.json` (v2) is unchanged.

**Hall circuit (planned):** coil from 5 V through an NPN with a flyback diode; a digital Hall sensor such as the A3144 needs ≥ 4.5 V, so it runs on 5 V, but its open-collector output is pulled up to 3.3 V (10 kΩ), never 5 V. Parts to buy: Hall sensors, coils (or electromagnet modules), diodes.

Written into `protocol.md` §2 (and `protocolo.md`), and `protocol-document.md` §15–§16.

**PDFs (same day):** `docs/build_pdf.py` (markdown → HTML → headless Chrome, needs `pip install --user markdown`) builds `protocol-document.pdf` (21 pages) and the Spanish twin `documento-protocolo.md` → `documento-protocolo.pdf` (22 pages). The Spanish keeps protocol terms in English where a translation would change their meaning (tick, frame, CLK, stop-and-wait, aging, timeout, buffer, pull-down, frame types and states), following `protocolo.md`. Left open on purpose: the channel → medium assignment (proposed) and the fifth medium (light, placeholder).

**Edits (same day, Cruz):** the submission documents no longer mention the professor (his rules are stated as design conditions, "someone interferes") and the R1–R17 requirements table in §2 was removed as redundant. Both PDFs rebuilt.
