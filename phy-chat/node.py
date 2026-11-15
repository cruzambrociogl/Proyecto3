#!/usr/bin/env python3
"""One chat node (one "equipo").

  Simulated medium (laptop, two nodes):
    python3 node.py --name A --web 8081 --phy sim --sim-rx 47001 --sim-tx 47002
    python3 node.py --name B --web 8082 --phy sim --sim-rx 47002 --sim-tx 47001
    (add --coding plain on both to compare with the original level scheme)

  BeagleBone GPIO (pins from a JSON file, one section per side):
    python3 node.py --name A --web 8081 --phy gpio --pins config/bbb_loopback.json
"""
import argparse
import json
import os

from phychat.app import ChatNode
from phychat.crc8 import VARIANTS
from phychat.presentation import ENCODING_IDS
from phychat.web import serve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--web", type=int, required=True, help="HTTP port for the chat UI")
    ap.add_argument("--phy", choices=["sim", "gpio"], default="sim")
    ap.add_argument("--hz", type=float, default=100.0, help="clock ticks per second")
    ap.add_argument("--crc", choices=list(VARIANTS), default="SMBUS")
    ap.add_argument("--encoding", choices=list(ENCODING_IDS), default="utf-8")
    ap.add_argument("--lanes", type=int, default=2, help="data lanes (sim only; gpio uses the pin file)")
    ap.add_argument("--coding", choices=["fec", "plain"],
                    help="fec: Manchester + parity lane P (default in sim); plain: level per lane (gpio, for now)")
    ap.add_argument("--sim-rx", type=int, default=47001)
    ap.add_argument("--sim-tx", type=int, default=47002)
    ap.add_argument("--pins", help="JSON pin map (gpio)")
    ap.add_argument("--sample-delay-ms", type=float, default=0.0,
                    help="wait after the CLK edge before reading lanes (slow media)")
    ap.add_argument("--log", help="append the protocol LOG as JSON lines to this file")
    args = ap.parse_args()

    if args.phy == "sim":
        from phychat.linecode import CODES, CodedPhy
        from phychat.phy_sim import SimPhy
        code = CODES[args.coding or "fec"](args.lanes)
        medium = SimPhy(len(code.channels), code.samples, args.hz, args.sim_rx, args.sim_tx)
        phy = CodedPhy(medium, code)
    else:
        if args.coding == "fec":
            ap.error("--coding fec todavía no está en GPIO (falta el muestreo x4 en el receptor); use --coding plain")
        from phychat.phy_gpio import GpioPhy
        with open(args.pins) as f:
            side = json.load(f)[args.name]
        phy = GpioPhy(side["tx"], side["rx"], args.hz, args.sample_delay_ms / 1000.0)

    logfile = args.log or os.path.join("logs", "node-%s.jsonl" % args.name)
    os.makedirs(os.path.dirname(logfile) or ".", exist_ok=True)
    node = ChatNode(args.name, phy, args.crc, args.encoding, logfile)
    node.start()
    print("Nodo %s -> http://localhost:%d  (LOG: %s)" % (args.name, args.web, logfile), flush=True)
    serve(node, args.web)


if __name__ == "__main__":
    main()
