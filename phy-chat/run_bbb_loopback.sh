#!/usr/bin/env bash
# Both nodes on one BeagleBone, A's TX pins jumpered to B's RX pins and back
# (see config/bbb_loopback.json and README). Extra args go to both nodes.
cd "$(dirname "$0")"
for p in P8_7 P8_8 P8_9 P8_10 P8_11 P8_12 P8_14 P8_15 P8_16 P8_17 P8_18 P8_26; do
  command -v config-pin >/dev/null && config-pin "$p" gpio >/dev/null 2>&1
done
python3 node.py --name A --web 8081 --phy gpio --pins config/bbb_loopback.json "$@" & A=$!
python3 node.py --name B --web 8082 --phy gpio --pins config/bbb_loopback.json "$@" & B=$!
trap 'kill $A $B 2>/dev/null' INT TERM EXIT
wait
