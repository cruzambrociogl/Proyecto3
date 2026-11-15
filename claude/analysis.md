# Code map: `phy-chat/`

State: v2 (Manchester + parity), 2026-11-15. Python 3, stdlib only. About 2,200 lines.

## Layers and files

```
web.py        HTTP server: static page, JSON API, live LOG over Server-Sent Events
app.py        ChatNode: message <-> presentation <-> link; START/DATA/END; LOG events (EventBus)
presentation.py  UTF-8 (byte-by-byte decoder) and single-byte Extended ASCII (CP437, ISO-8859-1)
link.py       Link: CRC check, ACK/NACK, stop-and-wait, SEQ duplicates, PING/PONG health, priority TX queue
frame.py      Frame (SYN/SFD/CTRL/DATA/CRC/SEQ, bits <-> ticks) and Deframer (hunts SYN + SFD)
crc8.py       Crc8 + the 4 variants; MGMT = SMBUS for PING/PONG
linecode.py   PlainCode (level), FecCode (Manchester + parity P), CodedPhy (wraps a PHY with a line code)
phy_sim.py    SimPhy: one UDP datagram per tick; Impairments (block / saturate / noise per channel)
phy_gpio.py   GpioPhy: sysfs GPIO on the BBB; TX drives data then a CLK edge; RX samples on CLK rising edge
static/index.html  chat, LOG, channel panel (interference buttons), oscilloscope
node.py       one node: CLI flags -> builds PHY + coding + Link + ChatNode + web server
tools/gpio_selftest.py  checks every TX -> RX wire in a pin map
config/bbb_loopback.json  pin map for both nodes on one BBB (P8 header)
run_sim.sh    A on :8081, B on :8082, UDP 47001/47002
run_bbb_loopback.sh  both nodes on one BBB with the GPIO PHY
tests/test_stack.py (15), tests/test_fec.py (14)
```

## Data flow

**Sending:** UI → `ChatNode.send` → outbox → `_send_loop` builds `START, DATA×n, END` → `Link.send_reliable` (blocks per frame until ACK, 8 retries) → `txq` (PriorityQueue: `PRIO_CONTROL=0` for ACK/NACK/PONG, `PRIO_DATA=1` for the rest) → `_tx_loop` → `phy.send_ticks(frame.ticks(lanes))`.

**Receiving:** the PHY calls `on_tick(bits, t)` once per tick → `Link._on_tick` → `Deframer.push` → `Link._on_frame` → CRC check → NACK, or ACK + duplicate check → `ChatNode._on_payload` → UI.

**Timing:** the receiver measures the peer's clock (median CLK interval) and derives the ACK timeout (`2 × peer frame time + 0.2 s`) and the PING interval (`max(1 s, 3 frame times)`). The alive window is 2.5 × the PING interval.

## Where v6b plugs in

| v6b piece | Where | Notes |
|---|---|---|
| Matrix encode/decode | new `phychat/matrixcode.py` | port `docs/experiments/matrix_nibble.py`; must keep its verified results |
| Three kinds of reading, D1 inverted | same module | symbol classifier on 4 reads |
| 5 channels CLK D0 D1 P Q, CLK matrix mark | a `MatrixPhy` like `CodedPhy` in `linecode.py` | link sees half bytes / frame bits, not channels |
| Frame = 10 matrices | `frame.py` + the coding | `Link.frame_time` uses `ticks_per_frame(lanes)`; needs a hook so it becomes 50 ticks |
| 4 priority levels, aging, waiting list | `link.py` | today 2 levels; `send_reliable` already does stop-and-wait |
| Repair buffer | coding/link boundary | keep good cells of a failed frame, merge with the repeat |
| Channel report | `link.py` | 4 bits in DATA of ACK/NACK/PING/PONG |
| IDLE / TRANSFER names | `link.py` `status()` | today: connected / rx_only / down |
| 4 reads per tick on the board | `phy_gpio.py` | today 1 read per CLK edge |
| `--coding matrix` | `node.py` | choices today: fec, plain |
| Scope / LOG | `static/index.html` | show the 5×4 matrix, failing checks, queue state |

## Known quirks

- With 2 lanes, junk ending in `11 00 10` before a SYN can lock the deframer early (about 1 in 64); ARQ recovers it. The test uses a seeded random generator.
- `GpioPhy` uses sysfs GPIO and falls back to polling if edge interrupts fail.
- `Pin` writes the pinmux state (`gpio` out, `gpio_pd` in) before exporting: in mode `default` a pin's sysfs value toggled but the header pin did not (P8_7, 2026-11-15).
- The GPIO PHY still runs `--coding plain`; FEC needs 4 samples per tick.
