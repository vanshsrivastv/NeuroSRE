"""Safety Guard: the policy layer between the LLM and the infrastructure.

Every command proposed by the Planner is checked against an allow-list. Each
allowed action carries a risk level and parameter limits. Anything not on the
list, aimed at an unknown service, or outside its limits is BLOCKED.

Policy:  low / medium  -> executed automatically
         high          -> needs human approval
         blocked       -> never executed, incident escalated
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..cloud.simulator import BASELINE

SERVICES = set(BASELINE)
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "blocked": 3}


@dataclass(frozen=True)
class ActionPolicy:
    risk: str
    description: str
    params: dict[str, tuple[int, int]] | None = None   # name -> (min, max)
    kinds: tuple[str, ...] | None = None                # service kinds the action applies to


ALLOWLIST: dict[str, ActionPolicy] = {
    "restart_service":       ActionPolicy("low", "Restart all replicas of a service"),
    "scale_service":         ActionPolicy("medium", "Change replica count", {"replicas": (1, 10)}),
    "rotate_logs":           ActionPolicy("low", "Rotate and compress log files"),
    "clear_tmp":             ActionPolicy("low", "Delete temporary files in /tmp"),
    "kill_idle_connections": ActionPolicy("low", "Terminate idle DB connections", kinds=("database",)),
    "increase_pool":         ActionPolicy("medium", "Raise DB connection pool size", {"size": (50, 500)}, ("database",)),
    "kill_long_queries":     ActionPolicy("medium", "Terminate queries running > 30 s", kinds=("database",)),
    "renew_certificate":     ActionPolicy("low", "Renew the TLS certificate", kinds=("gateway",)),
    "flush_cache":           ActionPolicy("medium", "Flush all cache keys", kinds=("cache",)),
    "flush_dns_cache":       ActionPolicy("low", "Flush the DNS resolver cache"),
    "rollback_deployment":   ActionPolicy("high", "Roll back to the previous release"),
    "failover_database":     ActionPolicy("high", "Promote replica to primary", kinds=("database",)),
}

# Patterns that are always refused, even if someone renames an action.
DENY_PATTERNS = [r"drop", r"delete", r"truncate", r"rm\s+-rf", r"shutdown", r"format", r"wipe", r"destroy",
                 r"chmod", r"sudo", r"disable_(auth|firewall|monitoring)", r"exfil"]


@dataclass
class Verdict:
    action: str
    target: str
    params: dict
    risk: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.risk != "blocked"

    def as_dict(self) -> dict:
        return {"action": self.action, "target": self.target, "params": self.params, "risk": self.risk,
                "reason": self.reason}


def check_step(step: dict) -> Verdict:
    action = str(step.get("action", "")).strip()
    target = str(step.get("target", "")).strip()
    params = step.get("params") or {}
    raw = f"{action} {target} {params}".lower()

    for pat in DENY_PATTERNS:
        if re.search(pat, raw):
            return Verdict(action, target, params, "blocked", f"matches deny pattern '{pat}'")
    policy = ALLOWLIST.get(action)
    if policy is None:
        return Verdict(action, target, params, "blocked", "action is not on the allow-list")
    if target not in SERVICES:
        return Verdict(action, target, params, "blocked", f"unknown target service '{target}'")
    if policy.kinds and BASELINE[target]["kind"] not in policy.kinds:
        return Verdict(action, target, params, "blocked", f"'{action}' does not apply to a {BASELINE[target]['kind']}")
    for name, value in params.items():
        if not policy.params or name not in policy.params:
            return Verdict(action, target, params, "blocked", f"unexpected parameter '{name}'")
        lo, hi = policy.params[name]
        try:
            v = int(value)
        except (TypeError, ValueError):
            return Verdict(action, target, params, "blocked", f"parameter '{name}' must be an integer")
        if not lo <= v <= hi:
            return Verdict(action, target, params, "blocked", f"{name}={v} outside safe range {lo}-{hi}")
    return Verdict(action, target, params, policy.risk, policy.description)


def assess_plan(steps: list[dict], runbook_actions: set[str] | None = None,
                service: str | None = None) -> tuple[str, list[Verdict]]:
    """Return the overall risk of a plan (the worst step) and per-step verdicts.

    With incident context, an allowed action that is *not* in the selected runbook, or that
    targets a different service than the one in trouble, is raised to HIGH risk so a human
    must approve it. This stops "allowed but wrong" actions, e.g. a prompt-injected
    `failover_database` during an unrelated incident.
    """
    if not steps:
        return "blocked", [Verdict("", "", {}, "blocked", "empty plan")]
    verdicts = [check_step(s) for s in steps]
    for v in verdicts:
        if not v.allowed:
            continue
        issues = []
        if runbook_actions is not None and v.action not in runbook_actions:
            issues.append(f"'{v.action}' is not part of the selected runbook")
        if service and v.target != service:
            issues.append(f"targets {v.target} but the incident is on {service}")
        if issues:
            v.risk, v.reason = "high", "; ".join(issues) + " -> needs human approval"
    overall = max((v.risk for v in verdicts), key=RISK_ORDER.__getitem__)
    return overall, verdicts


def may_execute(steps: list[dict], runbook_actions: set[str] | None, service: str | None,
                approval: str | None) -> tuple[bool, str]:
    """Final check run by the Executor itself, immediately before touching the infrastructure.

    Re-applies the full policy so that nothing can reach execution by bypassing the Safety
    Guard node (defence in depth).
    """
    risk, verdicts = assess_plan(steps, runbook_actions, service)
    if risk == "blocked":
        bad = next(v for v in verdicts if not v.allowed)
        return False, f"blocked step '{bad.action}': {bad.reason}"
    if risk == "high" and approval != "approved":
        return False, "high-risk plan has no human approval"
    return True, ""


def allowlist_text() -> str:
    lines = []
    for name, p in ALLOWLIST.items():
        extra = f" params={ {k: f'{a}-{b}' for k, (a, b) in p.params.items()} }" if p.params else ""
        kinds = f" (only for: {', '.join(p.kinds)})" if p.kinds else ""
        lines.append(f"- {name}: {p.description}; risk={p.risk}{extra}{kinds}")
    return "\n".join(lines)
