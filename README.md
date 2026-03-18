# checkr
Data Validation Service

Checkr – Validation Service Overview

Checkr is a backend service responsible for validating structured content (datasets) before they are accepted by other systems. It provides a uniform interface for executing different types of validations, each built around a well-defined base class.

🎯 Purpose
Validate datasets before storage or execution
Enforce consistency, quality, and policy through automated pipelines
Return standardized results and actionable status to the caller

🧱 Core Principles
Every validator is a Python class that inherits from a base interface defined in the codebase
Validators are dynamically loaded, configured, and executed
Validation logic is grouped into two types:

🧩 Validator Types
1. Dataset Validators

Used for validating JSON datasets, often chat-like or NLP-related

Organized into "gates", e.g.:
Gate 1: Structure & Required Fields
Gate 2: Deduplication
Gate 3: Toxicity / Content Filters
Gate 4: Language & Encoding
✅ These validators are chained and enforced in order.

2. Artifact Validators (TODO: Later)

Used to validate full artifact objects (e.g., plugins, Python scripts, prompts)
Can include:
SAST/static analysis
Schema validation
Sanity checks or dry runs
✅ These are triggered from external services via REST calls.

🔄 Key Differences from Generic Task Runners
Each validator is strictly typed and registered via a known base class (BaseValidator, etc.)
Validators are not arbitrary tasks — they follow strict lifecycle and interface contracts
Execution is observable and can be extended or audited easily

✅ Quality of gates are described in ./validators/README.md

🛠️ Checkr – REST API Design

## Health & Observability

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/livez` | Liveness probe — instant 200, no dependency checks |
| GET | `/ready` | Readiness probe — checks LLM backend (yallmp) reachability; returns 200 or 503 |
| GET | `/health` | Full health status — JSON with component details and version |
| GET | `/metrics` | Prometheus metrics (HTTP request counts/latency, validation results/errors/duration per gate) |

### Kubernetes probes

- `livenessProbe` → `/livez` (restarts pod if process is stuck)
- `readinessProbe` → `/ready` (removes pod from service if LLM backend is unreachable)

### Alerting

Prometheus alerting rules are in `devops/alerting/alert_rules.yml`:
- HTTP error rate spikes (overall and `/api/v0/validate` endpoint)
- Validation gate failure rate and error spikes
- Gate execution latency (P95/P99) — catches slow LLM backends for G-Eval/GABRIEL gates
- LLM backend (yallmp) availability
- Health check and service availability

## ✅ Base URL
All endpoints assume prefix: `/api/v1`

### 📁 Dataset Validation

| Method | Endpoint                      | Description                                        |
|--------|-------------------------------|----------------------------------------------------|
| POST   | `/validate/`                  | Validate a dataset JSON against enabled gates      |
| GET    | `/list`                       | List available dataset gate validators             |
| GET    | `/info/{name}`                | Get details about a specific gate                  |

Payload Example:
```json
{
  "name": "my_test_dataset",
  "content": [ ... ],
  "config": {
    "gates": ["structure", "toxicity"]
  }
}

📑 Validation Result Format
{
  "success": true,
  "summary": "Passed all checks",
  "details": {
    "structure": "ok",
    "toxicity": "ok",
    "language": "ok"
  }
}


🔐 Optional Enhancements (TODO)
Per-request Request-ID or Trace-ID header support
Webhook callback support for long-running validations
Support for fetching dataset from a URI (e.g., GitHub or S3)