#!/usr/bin/env bash
# Two nodes on this machine joined by the simulated medium.
# Extra args go to both nodes, e.g.: ./run_sim.sh --lanes 4 --hz 30
cd "$(dirname "$0")"
python3 node.py --name A --web 8081 --phy sim --sim-rx 47001 --sim-tx 47002 "$@" & A=$!
python3 node.py --name B --web 8082 --phy sim --sim-rx 47002 --sim-tx 47001 "$@" & B=$!
trap 'kill $A $B 2>/dev/null' INT TERM EXIT
wait
