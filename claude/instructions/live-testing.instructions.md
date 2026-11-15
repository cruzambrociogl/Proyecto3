# Running nodes for tests

Cruz runs his own servers while he tests. Never take his ports and never kill by pattern.

- `run_sim.sh` uses web 8081/8082 and UDP 47001/47002. For Claude's own tests use other ports, e.g. web 18081/18082 and UDP 47101/47102:

  ```
  cd phy-chat
  python3 node.py --name A --web 18081 --phy sim --sim-rx 47101 --sim-tx 47102 & A=$!
  python3 node.py --name B --web 18082 --phy sim --sim-rx 47102 --sim-tx 47101 & B=$!
  ...
  kill $A $B
  ```

- Check a port before assuming it is free: `lsof -iTCP:18081` / `lsof -iUDP:47101`.
- Stop processes only by the PIDs you started. Never use `pkill -f node.py` or similar.
- Unit tests need no ports: `python3 -m unittest -v tests.test_stack tests.test_fec`.

## On the BeagleBone

- Default address over USB: `debian@192.168.7.2` (macOS may get `192.168.6.2`). Copy with `scp -r phy-chat debian@192.168.7.2:~/`.
- Over Ethernet (what Cruz uses, 2026-11-15; his Mac did not see the board over USB): `debian@beaglebone.local`, which resolved to `192.168.2.2`.
- Sync after every change in `phy-chat/` (CLAUDE.md rule 13), from `PROJECT03/`:

  ```
  rsync -a --exclude __pycache__ --exclude logs/ --exclude .DS_Store phy-chat/ debian@beaglebone.local:phy-chat/
  rsync -anci --exclude __pycache__ --exclude logs/ --exclude .DS_Store phy-chat/ debian@beaglebone.local:phy-chat/   # prints nothing when in sync
  ```

  `ssh` prints the Debian login banner on every call; filter it out of the output.
- Run `python3 tools/gpio_selftest.py config/<map>.json` before the chat after any wiring change.
- GPIO is 3.3 V and not 5 V tolerant.
