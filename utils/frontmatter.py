import re
import yaml
from pathlib import Path
from typing import Any
from core.logging_config import setup_logging

logger = setup_logging()

# FRONTMATTER_PATTERN = re.compile(r'^"""\n---(.*?)---\n"""', re.DOTALL | re.MULTILINE)

FRONTMATTER_REGEX = re.compile(r"^\s*---\s*\n(.*?)\n---", re.DOTALL | re.MULTILINE)

def extract_frontmatter_from_file(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    return extract_frontmatter(content)

def extract_frontmatter(content: str) -> dict:
        match = FRONTMATTER_REGEX.search(content)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                logger.warning(f"Failed to load frontmatter for {module_name}: {e}")
                return {}
        return {}