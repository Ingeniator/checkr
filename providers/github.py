import httpx
import yaml
import base64
from pathlib import Path, PurePosixPath
from core.config import settings
from providers.base import BaseValidatorProvider
from schemas.validators import ValidatorDetail, ValidatorType
from core.logging_config import setup_logging
from utils.frontmatter import extract_frontmatter
from utils.yaml import load_and_expand_yaml

logger = setup_logging()

class GithubValidatorProvider(BaseValidatorProvider):

    def __init__(self, config_path: str = settings.provider_config_path):
        self.source_prefix = "github"
        self.config = load_and_expand_yaml(config_path)[self.source_prefix]

        self.repo = self.config["repo"]  # e.g., "org/repo"
        self.ref = self.config.get("ref", "main")
        self.token = self.config.get("private_token")  # Optional
        self.base_path = self.config.get("path", "")
        self.base_validators = []
        self.non_base_validators = []
        self.content_dict: dict[str, str] = {}

        self.headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def _api_url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.repo}/{path}"

    def _raw_url(self, file_path: str) -> str:
        return f"https://raw.githubusercontent.com/{self.repo}/{self.ref}/{file_path}"

    async def _walk_tree(self) -> list[dict]:
        url = f"{self._api_url(f'git/trees/{self.ref}')}?recursive=1"
        async with httpx.AsyncClient(verify=settings.http_verify_ssl) as client:
            r = await client.get(url, headers=self.headers)
            r.raise_for_status()
            tree = r.json().get("tree", [])
            return [
                item
                for item in tree
                if item["type"] in ["blob", "symlink"] and item["path"].endswith(".py") and item["path"].startswith(self.base_path)
            ]

    async def _resolve_symlink(self, item: dict) -> str | None:
        """Resolve symlink target path from blob content."""
        blob_url = item.get("url")
        if not blob_url:
            return None
        async with httpx.AsyncClient(verify=settings.http_verify_ssl) as client:
            r = await client.get(blob_url, headers=self.headers)
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("encoding") == "base64":
                try:
                    # Resolve relative to the directory of the symlink
                    symlink_dir = Path(item["path"]).parent
                    target_rel = base64.b64decode(data["content"]).decode().strip()
                    target_path = (symlink_dir / target_rel).as_posix()
                    return self.normalize_github_path(target_path)
                except Exception as e:
                    logger.warning(f"Failed to decode symlink blob: {e}")
                    return None
            return None

    async def _fetch_file_content(self, file_path: str) -> str:
        raw_url = self._raw_url(file_path)
        async with httpx.AsyncClient(verify=settings.http_verify_ssl) as client:
            r = await client.get(raw_url)
            r.raise_for_status()
            return r.text

    def normalize_github_path(self, raw_path: str) -> str:
        parts = []
        for part in PurePosixPath(raw_path).parts:
            if part == "..":
                if parts:
                    parts.pop()
            elif part != ".":
                parts.append(part)
        return "/".join(parts)

    async def _fetch_validators(self, include_base_validator=False) -> list[ValidatorDetail]:
        self.base_validators = []
        self.non_base_validators = []

        items = await self._walk_tree()
        for item in items:
            file_path = item["path"]
            mode = item.get("mode")
            is_symlink = (mode == "120000")

            resolved_path = file_path
            if is_symlink:
                resolved_path = await self._resolve_symlink(item)
                if not resolved_path:
                    logger.warning(f"Skipping unresolved symlink: {item['path']}")
                    continue

            try:
                content = await self._fetch_file_content(resolved_path)
                
                self.content_dict[resolved_path] = content
                front = extract_frontmatter(content)

                if "title" in front and "description" in front:
                    raw_tags = front.get("tags", [])
                    tags = raw_tags if isinstance(raw_tags, list) else [raw_tags] if raw_tags else []
                    validator_type = front.get("type", ValidatorType.dataset_frontend)

                    detail = ValidatorDetail(
                        title=front.get("title", Path(resolved_path).stem),
                        type=ValidatorType(validator_type),
                        enabled=front.get("enabled", True),
                        stage=front.get("stage", "experimental"),
                        description=front.get("description", ""),
                        tags=tags,
                        options=front.get("options", {}),
                        source=f"{self.source_prefix}/{resolved_path}"
                    )

                    if validator_type != "base":
                        self.non_base_validators.append(detail)
                    else:
                        self.base_validators.append(detail)

            except Exception as e:
                logger.warning(f"Skipping file {resolved_path} due to error: {e}")
                continue

        return self.base_validators if include_base_validator else self.non_base_validators

    async def fetch_frontend_validator_source(self, file_path: str) -> str:
        if file_path.startswith(f"{self.source_prefix}/"):
            file_path = file_path[len(self.source_prefix) + 1:]
        return self.content_dict.get(file_path, "")

    async def fetch_frontend_validators(self) -> list[ValidatorDetail]:
        if self.non_base_validators:
            return self.non_base_validators
        return await self._fetch_validators()

    async def fetch_frontend_base_validators_source(self) -> dict[str, str]:
        if not self.base_validators:
            await self._fetch_validators(include_base_validator=True)

        result = {}
        for base_validator in self.base_validators:
            file_path = base_validator.source
            if file_path.startswith(self.source_prefix):
                file_path = file_path[len(self.source_prefix) + 1:]
            parent_path = str(Path(self.base_path).parent.as_posix())
            if file_path.startswith(parent_path):
                file_path = file_path[len(parent_path) + 1:]
            result[file_path] = self.content_dict.get(file_path, "")
        return result
