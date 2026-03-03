"""Generate a large-payload scenario for Artillery performance testing.

Creates scenarios/20_large_validate_generated.yml with a synthetic ~10MB
dataset targeting POST /api/v0/validate with gate1_structural_validation.
Uses string concatenation (not yaml.dump) for speed at 10MB scale.

Env vars:
    LARGE_PAYLOAD_ENABLED   – set to '0' to skip (default: '1')
    LARGE_PAYLOAD_SIZE_MB   – target JSON body size in MB (default: 10)
    LARGE_PAYLOAD_ITEMS     – number of DataItems (default: 200)
    LARGE_PAYLOAD_MSGS      – messages per DataItem, must be even (default: 10)
    LARGE_PAYLOAD_RATE      – arrivalRate, must be unique (default: 1)

Prints the generated file path to stdout; diagnostics go to stderr.
"""

import os
import string
import sys
from pathlib import Path

PERF_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = PERF_DIR / "scenarios"
OUTPUT_FILE = SCENARIOS_DIR / "20_large_validate_generated.yml"

TARGET_SIZE_MB = int(os.environ.get("LARGE_PAYLOAD_SIZE_MB", "10"))
NUM_ITEMS = int(os.environ.get("LARGE_PAYLOAD_ITEMS", "200"))
MSGS_PER_ITEM = int(os.environ.get("LARGE_PAYLOAD_MSGS", "10"))
ARRIVAL_RATE = int(os.environ.get("LARGE_PAYLOAD_RATE", "1"))

# Characters safe for inline YAML values (no quotes/escaping needed)
SAFE_CHARS = string.ascii_letters + string.digits


def _fill_string(length: int, seed: int) -> str:
    """Return a deterministic alphanumeric string of the given length."""
    base = SAFE_CHARS
    base_len = len(base)
    # Build via repetition + trim
    repeats = (length // base_len) + 1
    return (base * repeats)[seed % base_len : seed % base_len + length]


def generate() -> None:
    if os.environ.get("LARGE_PAYLOAD_ENABLED", "1") == "0":
        print("Large-payload generation disabled (LARGE_PAYLOAD_ENABLED=0)",
              file=sys.stderr)
        return

    target_bytes = TARGET_SIZE_MB * 1024 * 1024

    # Calculate overhead per message to figure out content_length.
    # Each message line looks like:
    #   12 spaces + '- { role: "user", content: "XXXXX" }\n'    (~40 bytes overhead)
    #   12 spaces + '- { role: "assistant", content: "XXXXX" }\n'
    # Per-item overhead: "        - messages:\n" = ~20 bytes
    # Header overhead: metadata doc + post header + dataset key = ~300 bytes
    msg_overhead = 45  # average overhead per message line
    item_overhead = 22  # "        - messages:\n"
    header_overhead = 300

    total_messages = NUM_ITEMS * MSGS_PER_ITEM
    total_overhead = header_overhead + (NUM_ITEMS * item_overhead) + (total_messages * msg_overhead)
    content_budget = max(target_bytes - total_overhead, total_messages)
    content_length = content_budget // total_messages

    print(f"Generating large payload: {TARGET_SIZE_MB}MB target, "
          f"{NUM_ITEMS} items, {MSGS_PER_ITEM} msgs/item, "
          f"{content_length} chars/msg, rate={ARRIVAL_RATE}rps",
          file=sys.stderr)

    parts: list[str] = []

    # Metadata document
    parts.append(f"arrivalRate: {ARRIVAL_RATE}\n---\n")

    # Flow step header
    parts.append(
        "- post:\n"
        '    url: "/api/v0/validate/backend/gate1_structural_validation/chat_struct_validator.py"\n'
        "    headers:\n"
        '      Content-Type: "application/json"\n'
        "    json:\n"
        "      dataset:\n"
    )

    roles = ("user", "assistant")
    seed = 0
    for item_idx in range(NUM_ITEMS):
        parts.append("        - messages:\n")
        for msg_idx in range(MSGS_PER_ITEM):
            role = roles[msg_idx % 2]
            content = _fill_string(content_length, seed)
            parts.append(
                f'            - {{ role: "{role}", content: "{content}" }}\n'
            )
            seed += 1

    yaml_text = "".join(parts)
    actual_size = len(yaml_text.encode())
    print(f"Generated YAML size: {actual_size / 1024 / 1024:.2f}MB", file=sys.stderr)

    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(yaml_text)
    # stdout: file path for run.sh consumption
    print(OUTPUT_FILE)


if __name__ == "__main__":
    generate()
