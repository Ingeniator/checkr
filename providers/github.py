import httpx
import yaml
from pathlib import Path
from core.config import settings
from providers.base import BaseValidatorProvider
from schemas.validators import ValidatorDetail, ValidatorType
from core.logging_config import setup_logging
from utils.frontmatter import extract_frontmatter

logger = setup_logging()

class GithubValidatorProvider(BaseValidatorProvider):
    source_prefix = "github"
    base_validators: list[ValidatorDetail]
    non_base_validators: list[ValidatorDetail]

    def __init__(self, config_path: str = settings.provider_config_path):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)[self.source_prefix]

        self.repo = self.config["repo"]  # e.g., "org/repo"
        self.ref = self.config.get("ref", "main")
        self.token = self.config.get("private_token")  # <-- Optional
        self.base_path = self.config.get("path", "")
        self.base_validators = []
        self.non_base_validators = []

        self.headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def _get_github_api_url(self) -> str:
        return f"https://api.github.com/repos/{self.repo}/git/trees/{self.ref}?recursive=1"

    async def _walk_tree(self) -> list[str]:
        url = self._get_github_api_url()
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=self.headers)
            r.raise_for_status()
            tree = r.json().get("tree", [])
            return [
                item["path"]
                for item in tree
                if item["type"] == "blob" and item["path"].endswith(".py") and item["path"].startswith(self.base_path)
            ]

    async def _fetch_file_content(self, path: str) -> str:
        raw_url = f"https://raw.githubusercontent.com/{self.repo}/{self.ref}/{path}"
        async with httpx.AsyncClient() as client:
            r = await client.get(raw_url)
            r.raise_for_status()
            return r.text

    async def _fetch_validators(self, include_base_validator=False) -> list[ValidatorDetail]:
        self.base_validators = []
        self.non_base_validators = []

        for file_path in await self._walk_tree():
            try:
                content = await self._fetch_file_content(file_path)
                front = extract_frontmatter(content)

                if "title" in front and "description" in front:
                    raw_tags = front.get("tags", [])
                    tags = raw_tags if isinstance(raw_tags, list) else [raw_tags] if raw_tags else []
                    validator_type = front.get("type", ValidatorType.dataset_frontend)

                    detail = ValidatorDetail(
                        title=front.get("title", Path(file_path).stem),
                        type=ValidatorType(validator_type),
                        enabled=front.get("enabled", True),
                        stage=front.get("stage", "experimental"),
                        description=front.get("description", ""),
                        tags=tags,
                        options=front.get("options", {}),
                        source=f"{self.source_prefix}/{file_path}"
                    )

                    if validator_type != "base":
                        self.non_base_validators.append(detail)
                    else:
                        self.base_validators.append(detail)

            except Exception as e:
                logger.warning(f"Skipping file {file_path} due to error: {e}")
                continue

        return self.base_validators if include_base_validator else self.non_base_validators

    async def fetch_frontend_validator_source(self, file_path: str) -> str:
        if file_path.startswith(f"{self.source_prefix}/"):
            file_path = file_path[len(self.source_prefix) + 1:]
        try:
            return await self._fetch_file_content(file_path)
        except Exception as e:
            logger.error(f"[WARN] Failed to fetch source for {file_path}: {e}")
            return ""

    async def fetch_frontend_validators(self) -> list[ValidatorDetail]:
        if self.non_base_validators:
            return self.non_base_validators
        return await self._fetch_validators()

    async def fetch_frontend_base_validators_source(self) -> dict[str, str]:
        logger.info("fetch_frontend_base_validators_source")
        if not self.base_validators:
            await self._fetch_validators(include_base_validator=True)

        result = {}
        for base_validator in self.base_validators:
            file_path = base_validator.source
            parent_path = str(Path(self.base_path).parent.as_posix())
            prefix_path=f"{self.source_prefix}/{parent_path}"
            if file_path.startswith(prefix_path):
                file_path = file_path[len(prefix_path) + 1:]
            result[file_path] = await self.fetch_frontend_validator_source(base_validator.source)
        return result
