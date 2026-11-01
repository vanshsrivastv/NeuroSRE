"""Stand-alone mock cloud log generator.

Prints the simulator's JSON log stream to the console and injects a random
fault every N seconds. Useful to show the "live cloud" on its own.

    python scripts/log_generator.py --fault-every 20
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neurosre.cloud import CloudSimulator  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between ticks")
    ap.add_argument("--fault-every", type=float, default=30.0, help="seconds between random faults (0 = never)")
    args = ap.parse_args()

    cloud = CloudSimulator()
    last_seq, last_fault = 0, time.time()
    try:
        while True:
            cloud.tick()
            if args.fault_every and time.time() - last_fault > args.fault_every:
                f = cloud.inject()
                last_fault = time.time()
                if f:
                    print(f"# injected fault: {f.spec.id} on {f.service}", file=sys.stderr)
            for rec in cloud.recent_logs(limit=100, since_seq=last_seq):
                print(json.dumps({k: rec[k] for k in ("ts", "service", "level", "message", "trace_id")}), flush=True)
                last_seq = rec["seq"]
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
