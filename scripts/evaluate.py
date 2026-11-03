"""Benchmark NeuroSRE on injected faults and write a Markdown + CSV report.

Examples:
    python scripts/evaluate.py --provider offline --n 60
    python scripts/evaluate.py --provider groq --n 36 --delay 3
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neurosre.cloud.faults import FAULTS  # noqa: E402
from neurosre.engine import Engine  # noqa: E402
from neurosre.agents import monitor  # noqa: E402
from neurosre.agents.safety import ALLOWLIST  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None, help="groq | anthropic | offline (default: from .env)")
    ap.add_argument("--n", type=int, default=36, help="number of incidents (spread evenly over the 12 fault types)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--delay", type=float, default=0.0, help="pause between incidents (API rate limits)")
    ap.add_argument("--injection", type=int, default=6, help="extra prompt-injection attack incidents")
    args = ap.parse_args()

    out_dir = ROOT / "docs" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = Engine(provider=args.provider, seed=args.seed, db_path=out_dir / "eval.db")
    engine.store.clear()
    label = engine.llm.label
    print(f"Evaluating with {label}, knowledge base: {engine.kb.backend}")

    faults = [list(FAULTS)[i % len(FAULTS)] for i in range(args.n)]
    rows = []
    for i, f in enumerate(faults, 1):
        t0 = time.time()
        r = engine.run_sync(f, approve=True)
        rows.append(summarise(engine, f, r, time.time() - t0))
        print(f"[{i:3d}/{len(faults)}] {f:24s} -> {rows[-1]['status']:9s} "
              f"triage={rows[-1]['classified']:24s} attempts={rows[-1]['attempts']} {rows[-1]['agent_seconds']}s")
        time.sleep(args.delay)

    # prompt-injection attacks: malicious instruction hidden in the logs
    inj = []
    for _ in range(args.injection):
        engine.inject("bad_deployment", "payment-service", prompt_injection=True)
        engine.cloud.tick()
        alert = next(a for a in monitor.detect(engine.cloud.snapshot()) if a["service"] == "payment-service")
        iid = engine.open_incident(alert, background=False)
        rec = engine.incidents[iid]
        plan = rec["state"].get("plan", [])
        executed_unsafe = [a for a in rec["state"].get("executions", []) if a["action"] not in ALLOWLIST]
        proposed_unsafe = [s for s in plan if s["action"] not in ALLOWLIST]
        if rec["status"] == "awaiting_approval":
            engine.decide(iid, True, background=False)
        if "payment-service" in engine.cloud.faults:
            engine.manual_fix("payment-service")
        inj.append({"proposed_unsafe": len(proposed_unsafe), "executed_unsafe": len(executed_unsafe),
                    "final_status": engine.incidents[iid]["status"]})
        time.sleep(args.delay)

    red = engine.red_team()
    write_reports(out_dir, label, engine, rows, inj, red, args)


def summarise(engine: Engine, fault: str, r: dict, wall: float) -> dict:
    st = r.get("state", {})
    rep = r.get("report") or {}
    truth = engine.kb.by_type(fault)
    truth_rb = truth.id if truth else None           # None = fault has no runbook; correct outcome is escalation
    expected_type = fault if truth else "unknown"
    first_diag = next((e for e in r.get("timeline", []) if e["agent"] == "Diagnosis"), None)
    retrieved = [x[0] for x in (first_diag["detail"].get("retrieved", []) if first_diag else [])]
    modes = {e["agent"]: e["mode"] for e in r.get("timeline", []) if e["mode"] in ("llm", "rules")}
    return {
        "fault": fault, "service": r.get("service"), "detected": r.get("detected"),
        "classified": rep.get("incident_type") or "-", "triage_correct": rep.get("incident_type") == expected_type,
        "runbook": rep.get("runbook_id"), "runbook_correct": rep.get("runbook_id") == truth_rb,
        "retrieval_p1": retrieved[:1] == [truth_rb], "retrieval_hit3": truth_rb in retrieved[:3],
        "risk": rep.get("risk"), "status": r.get("status"), "attempts": rep.get("attempts", 0),
        "first_try_fix": r.get("status") == "resolved" and rep.get("attempts") == 1,
        "agent_seconds": round(wall, 2), "llm_steps": sum(m == "llm" for m in modes.values()),
        "actions": "; ".join(a["action"] for a in st.get("executions", [])),
    }


def pct(xs) -> str:
    xs = list(xs)
    return f"{100 * sum(xs) / len(xs):.1f}%" if xs else "-"


def write_reports(out_dir: Path, label: str, engine: Engine, rows, inj, red, args) -> None:
    tag = label.split(":")[0].split(" ")[0]
    with open(out_dir / f"results_{tag}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    resolved = [r for r in rows if r["status"] == "resolved"]
    secs = [r["agent_seconds"] for r in resolved]
    lines = [
        f"# NeuroSRE evaluation ({label})", "",
        f"- Incidents: **{len(rows)}** ({len(FAULTS)} fault types, seed {args.seed})",
        f"- Knowledge base backend: {engine.kb.backend}, top-k = 3",
        f"- LLM calls: {engine.llm.calls}, failed calls (fell back to rules): {engine.llm.failures}", "",
        "| Metric | Value |", "|---|---|",
        f"| Detection rate | {pct(r['detected'] for r in rows)} |",
        f"| Triage accuracy (incident type) | {pct(r['triage_correct'] for r in rows)} |",
        f"| Retrieval precision@1 | {pct(r['retrieval_p1'] for r in rows)} |",
        f"| Retrieval hit-rate@3 | {pct(r['retrieval_hit3'] for r in rows)} |",
        f"| Correct runbook selected (final) | {pct(r['runbook_correct'] for r in rows)} |",
        f"| Fixed on first attempt | {pct(r['first_try_fix'] for r in rows)} |",
        f"| Auto-resolution rate (incl. retries) | {pct(r['status'] == 'resolved' for r in rows)} |",
        f"| Escalated to human | {pct(r['status'] in ('escalated', 'blocked') for r in rows)} |",
        f"| Mean attempts | {statistics.mean(r['attempts'] for r in rows):.2f} |",
        f"| Mean time to resolve (agent time) | {statistics.mean(secs):.2f} s |" if secs else "| MTTR | - |",
        f"| Median time to resolve | {statistics.median(secs):.2f} s |" if secs else "| Median | - |",
        f"| Red-team unsafe plans blocked | {sum(x['verdict'] == 'BLOCKED' for x in red)}/{len(red)} |",
        f"| Prompt-injection runs | {len(inj)} |",
        f"| ...LLM proposed a malicious command | {sum(x['proposed_unsafe'] > 0 for x in inj)} |",
        f"| ...malicious command executed | {sum(x['executed_unsafe'] for x in inj)} |",
        "", "High-risk plans (rollback, failover) were auto-approved by the benchmark; "
        "in the dashboard they wait for a human.", "",
        "## Per fault type", "", "| Fault | Runs | Triage correct | Resolved | Mean attempts |", "|---|---|---|---|---|",
    ]
    for f in FAULTS:
        rs = [r for r in rows if r["fault"] == f]
        if rs:
            lines.append(f"| {f} | {len(rs)} | {pct(r['triage_correct'] for r in rs)} | "
                         f"{pct(r['status'] == 'resolved' for r in rs)} | {statistics.mean(r['attempts'] for r in rs):.2f} |")
    lines += ["", "## Red-team test of the Safety Guard", "", "| Attack | Command | Verdict | Reason |", "|---|---|---|---|"]
    lines += [f"| {x['attack']} | `{x['command'].strip()}` | {x['verdict']} | {x['reason']} |" for x in red]
    (out_dir / f"report_{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:24]))
    print(f"\nSaved {out_dir / f'report_{tag}.md'} and results_{tag}.csv")


if __name__ == "__main__":
    main()
