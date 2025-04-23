# checkr
Data Validation Service

Checkr – Validation Service Overview

Checkr is a backend service responsible for validating structured content and artifacts before they are accepted by systems like Keepr(Trustbox). It provides a uniform interface for executing different types of validations, each built around a well-defined base class.

🎯 Purpose
Validate artifacts and datasets before storage or execution
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

2. Artifact Validators

Used to validate full artifact objects (e.g., plugins, Python scripts, prompts)
Can include:
SAST/static analysis
Schema validation
Sanity checks or dry runs
✅ These are triggered from external services (like Trustbox) via REST calls.

🔄 Key Differences from Generic Task Runners
Each validator is strictly typed and registered via a known base class (BaseValidator, DatasetGate, etc.)
Validators are not arbitrary tasks — they follow strict lifecycle and interface contracts
Execution is observable and can be extended or audited easily


🛠️ Checkr – REST API Design

## ✅ Base URL
All endpoints assume prefix: `/api/v1`

### 📁 Dataset Validation

| Method | Endpoint                      | Description                                        |
|--------|-------------------------------|----------------------------------------------------|
| POST   | `/validate/dataset`           | Validate a dataset JSON against enabled gates      |
| GET    | `/validators/dataset`         | List available dataset gate validators             |
| GET    | `/validators/dataset/{name}`  | Get details about a specific gate                  |

Payload Example:
```json
{
  "name": "my_test_dataset",
  "content": [ ... ],
  "config": {
    "gates": ["structure", "toxicity"]
  }
}

📦 Artifact Validation
Method	Endpoint	Description
POST	/validate/artifact	Validate artifact payload (e.g., prompt, plugin)
GET	/validators/artifact	List available artifact validators
GET	/validators/artifact/{name}	Get details about a specific validator

Payload Example:
{
  "type": "python_script",
  "version": "v1.0.0",
  "metadata": {...},
  "content": "base64 or raw json",
  "config": {
    "strict_mode": true
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


🗂️ Suggested Project Structure
checkr/
├── main.py                   # FastAPI entrypoint
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── dataset.py        # Routes for dataset validation
│   │   ├── artifact.py       # Routes for artifact validation
│   └── dependencies.py       # JWT/auth/context injection (optional)
├── validators/
│   ├── __init__.py
│   ├── base.py               # BaseValidator, DatasetGate, etc.
│   ├── dataset/
│   │   ├── structure.py
│   │   ├── toxicity.py
│   │   ├── deduplication.py
│   ├── artifact/
│   │   ├── python_linter.py
│   │   ├── sast_checker.py
│   │   ├── prompt_sanity.py
├── core/
│   ├── loader.py             # Dynamic validator loader from registry
│   ├── pipeline.py           # Gate chaining logic
│   └── registry.py           # Maps validator names to classes
├── schemas/
│   ├── dataset.py
│   ├── artifact.py
│   └── result.py
├── config/
│   └── validator_config.yaml # Optionally declarative config of gates
├── tests/
│   ├── test_datasets/
│   ├── test_artifacts/
├── utils/
│   └── hash.py, io.py        # Optional helpers
├── logging_config.py
└── requirements.txt


🔐 Optional Enhancements
Per-request Request-ID or Trace-ID header support
Webhook callback support for long-running validations
Support for submitting inline content or fetching from a URI (e.g., GitHub or S3)