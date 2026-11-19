<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/neurosre-logo-dark.svg">
    <img alt="NeuroSRE" src="docs/brand/neurosre-logo-light.svg" width="300">
  </picture>
</p>

# NeuroSRE: Agentic AI Swarm for Autonomous Cloud Self-Healing

NeuroSRE is an autonomous **Level-1 Site Reliability Engineer** built from a team of AI agents.
It watches a live stream of cloud logs and metrics, detects incidents, finds the right fix in
internal runbooks using **Retrieval-Augmented Generation (RAG)**, plans the remediation, checks it
against a **Safety Guard**, applies it, verifies that the service recovered and writes an incident
report, with a **human in the loop** for risky actions.

> The cloud is a realistic **simulation** (six microservices with live metrics and logs). Faults
> really change service state, and a service only recovers when the *correct and complete* fix is
> applied, so every recovery shown on the dashboard is verified, not hard-coded.

![Architecture](docs/diagrams/fig1_architecture.png)

## Features

- **8 LangGraph agents**: Monitor, Triage, Diagnosis (RAG), Planner, Safety Guard, Executor, Verifier, Reporter
  (plus Human Approval and Escalation steps)
- **RAG over 12 runbooks**: chunked by section, embedded with `all-MiniLM-L6-v2`, stored in ChromaDB
- **LLM via Groq** (OpenAI GPT-OSS 120B open-weight model, free tier; any Groq model can be set in `.env`) with structured (Pydantic/JSON) outputs; Anthropic Claude also supported
- **Offline fallback**: if there is no API key or the internet fails, every agent falls back to rule-based logic
  so the demo never breaks (the dashboard shows `LLM` or `rules` next to every step)
- **Knows when *not* to act (evidence gate)**: the system only acts when three independent signals agree: the
  Triage classification, the runbook the Diagnosis agent chose, and semantic retrieval run on the raw evidence
  (it never sees the LLM's label). The runbook must also apply to the affected service. Otherwise the incident
  is escalated to a human with the reason. Two fault types (clock skew, network partition) have no runbook at all.
- **Safety Guard**: the LLM never writes shell commands; it picks structured actions from an allow-list with
  risk levels and parameter limits. Actions that are allowed but not part of the selected runbook, or aimed at a
  different service, are raised to HIGH risk. High-risk plans pause for a **named** engineer's approval.
- **Executor re-validation**: the Executor re-checks the whole policy right before acting and refuses stale
  approved plans if the service has already recovered
- **Self-correction loop**: if the Verifier (which reads metrics, not the executor's "success") finds the service
  still unhealthy, Diagnosis retries with feedback (max 3), then escalates
- **Alert persistence**: an alert fires only after an anomaly persists for 2 checks (like Prometheus `for:`)
- **Prompt-injection defence**: log text is treated as untrusted data; even a fully compromised plan is stopped by
  the code-level guard
- **Web console** (FastAPI + hand-written HTML/CSS/JS, light and dark themes): incident queue; the incident story with
  a **live agent-pipeline graph** showing the exact path through the LangGraph; the evidence gate's three signals;
  named approvals; a **service map** with live request flow and blast radius; streaming logs; chaos controls with
  a *hard mode* (unseen log wording + misleading lines); policy, runbook search and metrics views
- SQLite audit trail, red-team test and a benchmark with hard cases and confidence intervals

![Agent workflow](docs/diagrams/fig2_workflow.png)

## Quick start (Windows)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Get a free Groq API key from https://console.groq.com/keys and paste it into `.env`:

```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

Run the console:

```bash
python -m neurosre.api
```

Open http://localhost:8000. The first start downloads the 80 MB embedding model and builds the vector
index (about 1–2 minutes, once).

No key? Set `LLM_PROVIDER=offline` to run fully offline with rule-based agents.

### Docker (one command)

```bash
docker compose up --build
```

Then open http://localhost:8000. The container runs as a non-root user with all Linux capabilities dropped,
resource limits, and the port bound to this machine only.

## Demo script (for the presentation)

1. **Show the healthy system.** *Incidents* tab: "All systems operational", the service map with requests flowing,
   six healthy services on the right and the log stream.
2. **Inject a simple fault.** Chaos panel → *Memory leak* → *Inject*. The service turns red on the map and its callers
   amber (blast radius). The incident opens and the **agent pipeline** lights up step by step, ending in a green
   banner: *Resolved in X s, verified from live metrics*.
3. **Explain the evidence gate.** Point at its three signals: the Triage label (LLM), the chosen runbook (LLM) and
   independent retrieval from the raw logs. The system only acts when they agree.
4. **Human-in-the-loop.** Inject *Faulty release deployed*. The pipeline stops on **Approval** and an approval card
   shows the exact command and why it is high risk. Approving needs your name; the report records who approved,
   and the banner splits agent time from approval waiting time.
5. **Knowing when not to act.** Inject *System clock drift* (listed under "No runbook"). The gate escalates it to a
   human with the reason, the pipeline shows the red exit, nothing is executed, and the service appears under
   *Waiting for a human* until you click *Mark fixed*.
6. **Prompt-injection attack.** Click *Prompt-injection attack*: a log line orders the AI to drop the database. It is
   ignored, and even a compromised plan would be stopped by the code-level guard.
7. **Replay.** On any incident, click *Replay incident* to re-run its story agent by agent.
8. **Safety policy tab → Run attacks.** Six dangerous plans (drop database, `rm -rf`, 500 replicas...) are all BLOCKED.
9. **Runbooks tab.** Search a symptom (e.g. `x509 certificate has expired`) to show semantic retrieval with scores.
10. **Hard mode + Auto chaos**, then the **Metrics** tab: resolution rate, triage accuracy against the injected ground
   truth, time to resolve, and the latest benchmark report.

## Evaluation

```bash
python scripts/evaluate.py --provider groq --per-fault 2 --delay 1     # with the LLM
python scripts/evaluate.py --provider offline --per-fault 2            # rule-based baseline
```

Benchmark v2 tests easy **and** hard cases and reports every rate with a 95% Wilson confidence interval:

| Suite | What it checks |
|---|---|
| standard | known faults with the log wording the system was developed on |
| paraphrased | the same faults with held-out wording never used during development |
| noisy | held-out wording plus misleading log lines from unrelated faults |
| unknown | faults with no runbook: the only correct outcome is escalation with no action |
| injection | six prompt-injection payloads hidden in the logs |
| concurrent | three simultaneous faults on different services |
| healthy | a long fault-free run, counting false alarms |

High-risk plans pause for approval exactly as on the dashboard; the benchmark's simulated reviewer approves
only plans that match the true fix, and the report states how many approvals were requested. The headline
metric is **unsafe executions** (any action outside the true fix). Results: `docs/evaluation/report_<provider>.md`.

The rule-based baseline scores 100% on the standard wording but collapses on unseen wording, while still never
acting unsafely; that contrast is what the LLM run should be compared against.

## Tests

```bash
python -m pytest -q
```

47 tests cover the simulator (wrong/partial fixes do not recover), the Safety Guard (allow-list, off-runbook
and wrong-service actions, executor re-check), retrieval for every fault type, the full pipeline for all
faults, escalation of faults with no runbook, approval/rejection and stale approvals, and the LLM path with a
stub model (retry loop, refusal, conflicting evidence, compromised plans).

## Project structure

```
web/                        web console (index.html, app.css, app.js)
neurosre/
  api.py                    FastAPI backend: JSON API + serves the web console
  config.py                 settings from .env
  engine.py                 background loop, incident runner, approvals
  storage.py                SQLite incident store
  cloud/faults.py           12 fault types: effects, logs, required fixes
  cloud/simulator.py        stateful mock cloud (6 services, metrics, logs, commands)
  knowledge/runbooks/*.md   12 runbooks (the knowledge base)
  knowledge/store.py        chunking, ChromaDB embeddings, retrieval (BM25 fallback)
  agents/graph.py           LangGraph state graph: all agents + conditional edges
  agents/llm.py             Groq / Anthropic / offline provider wrapper
  agents/safety.py          Safety Guard policy
  agents/monitor.py         anomaly detection used by Monitor and Verifier
  agents/rules.py           rule-based fallbacks
scripts/evaluate.py         benchmark
scripts/log_generator.py    stand-alone JSON log stream
tests/                      pytest suite
docs/                       synopsis, diagrams, evaluation reports
```

## Fault types and runbooks

| Fault | Service(s) | Fix (runbook) | Risk |
|---|---|---|---|
| CPU saturation | gateway, auth, payment | scale_service replicas=5 (RB-001) | medium |
| Memory leak | gateway, auth, payment | restart_service (RB-002) | low |
| Disk full | apps, orders-db | rotate_logs + clear_tmp (RB-003) | low |
| Service crash | gateway, auth, payment | restart_service (RB-004) | low |
| DB connection pool exhausted | orders-db | kill_idle_connections + increase_pool (RB-005) | medium |
| Long-running queries | orders-db | kill_long_queries (RB-006) | medium |
| Expired TLS certificate | api-gateway | renew_certificate (RB-007) | low |
| Cache server down | redis-cache | restart_service (RB-008) | low |
| Queue backlog | worker-queue | scale_service replicas=6 (RB-009) | medium |
| Faulty release | gateway, auth, payment | rollback_deployment (RB-010) | **high** |
| DB primary failure | orders-db | failover_database (RB-011) | **high** |
| DNS failure | gateway, auth, payment | flush_dns_cache (RB-012) | low |
| Clock drift | auth, payment | **no runbook**: must be escalated | - |
| Network partition | api-gateway | **no runbook**: must be escalated | - |

## Limitations

- The infrastructure is simulated; commands act on the simulator, not on real servers. Connecting the
  Executor to Kubernetes or a cloud API would be the next step.
- Twelve incident types and runbooks; real environments have hundreds.
- Groq's free tier has rate limits; long benchmarks need `--delay`.
- Evidence-gate thresholds were calibrated on the standard log wording; the paraphrased suites measure how
  well they generalise. Mixed evidence (e.g. DNS errors naming the cache host) is sometimes escalated rather
  than fixed, which is safe but costs automation.
- The dashboard has no login; the Docker setup binds it to localhost for that reason.
