import os
import re
import yaml

def load_and_expand_yaml(path: str) -> dict:
    with open(path) as f:
        raw = f.read()

    # Replace ${VAR} with actual env var values
    expanded = re.sub(r"\${(\w+)}", lambda m: os.environ.get(m.group(1), ""), raw)

    return yaml.safe_load(expanded)
