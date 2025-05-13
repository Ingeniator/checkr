import gitlab
import yaml
from pathlib import Path
from core.config import settings
from providers.base import BaseValidatorProvider
from schemas.validators import ValidatorDetail, ValidatorType
from core.logging_config import setup_logging
from utils.frontmatter import extract_frontmatter

logger = setup_logging()

class GitlabValidatorProvider(BaseValidatorProvider):
    source_prefix = "gitlab"
    base_validators: list[ValidatorDetail]
    non_base_validators: list[ValidatorDetail]

    def __init__(self, config_path: str = settings.provider_config_path):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)[self.source_prefix]

        self.gl = gitlab.Gitlab(self.config["url"], private_token=self.config["private_token"])
        self.project = self.gl.projects.get(self.config["project_id"])
        self.ref = self.config.get("ref", "main")
        self.base_path = self.config.get("path", "")
        self.base_validators = []
        self.non_base_validators = []

    def _walk_tree(self) -> list[str]:
        all_files = []
        stack = [self.base_path]

        while stack:
            current_path = stack.pop()
            items = self.project.repository_tree(path=current_path, ref=self.ref)
            for item in items:
                if item["type"] == "tree":
                    stack.append(item["path"])
                elif item["type"] == "blob" and item["path"].endswith(".py"):
                    all_files.append(item["path"])
        return all_files

    async def _fetch_validators(self, include_base_validator = False) -> list[ValidatorDetail]:
        self.non_base_validators = []
        self.base_validators = []
        for file_path in self._walk_tree():
            try:
                f = self.project.files.get(file_path=file_path, ref=self.ref)
                content = f.decode().decode("utf-8")
                front = extract_frontmatter(content)
                if "title" in front \
                    and "description" in front:
                    raw_tags = front.get("tags", [])
                    tags = raw_tags if isinstance(raw_tags, list) else [raw_tags] if raw_tags else []
                    validator_type = front.get("type", ValidatorType.dataset_frontend)
                    if validator_type != "base":
                        self.non_base_validators.append(
                            ValidatorDetail(
                                title=front.get("title", Path(file_path).stem),
                                type=ValidatorType(validator_type),
                                enabled=front.get("enabled", True),
                                stage=front.get("stage", "experimental"),
                                description=front.get("description", ""),
                                tags=tags,
                                options=front.get("options", {}),
                                source=f"{self.source_prefix}/{file_path}"
                            )
                        )
                    else:
                        self.base_validators.append(
                            ValidatorDetail(
                                title=front.get("title", Path(file_path).stem),
                                type=ValidatorType(validator_type),
                                enabled=front.get("enabled", True),
                                stage=front.get("stage", "experimental"),
                                description=front.get("description", ""),
                                tags=tags,
                                options=front.get("options", {}),
                                source=f"{self.source_prefix}/{file_path}"
                            )
                        )
            except Exception as e:
                logger.warning(f"Skipping file {file_path} due to error: {e}")
                continue
        if include_base_validator:
            return self.base_validators
        else:
            return self.non_base_validators
    
    async def fetch_frontend_validator_source(self, file_path: str) -> str:
        # Remove the SOURCE_PREFIX only if it exists
        if file_path.startswith(f"{self.source_prefix}/"):
            file_path = file_path[len(self.source_prefix) + 1:]
        try:
            f = self.project.files.get(file_path=file_path, ref=self.ref)
            return f.decode().decode('utf-8')
        except Exception as e:
            logger.error(f"[WARN] Failed to fetch source for {file_path}: {e}")
            return ""

    async def fetch_frontend_validators(self) -> list[ValidatorDetail]:
        if len(self.non_base_validators) > 0:
            return self.non_base_validators
        else:
            return await self._fetch_validators()

    async def fetch_frontend_base_validators_source(self) -> dict[str, str]:
        logger.info("fetch_frontend_base_validators_source")
        if len(self.base_validators) > 0:
            base_validators = self.base_validators
        else:
            base_validators = await self._fetch_validators(base=True)
        result = {}
        for base_validator in base_validators:
            file_path = base_validator.source
            if file_path.startswith(f"{self.source_prefix}/"):
                file_path = file_path[len(self.source_prefix) + 1:]
            result[file_path] = await self.fetch_frontend_validator_source(base_validator.source)
        return result