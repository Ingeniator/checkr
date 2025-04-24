from schemas.validators import ValidatorDetail

BACKEND_VALIDATORS = [
    {"id": "task-schema-check", "stage": "stable", "description": "Validates schema."},
    {"id": "toxicity-check", "stage": "experimental", "description": "Detects toxic content."}
]

async def build_backend_proxy_entries() -> list[ValidatorDetail]:
    return [
         ValidatorDetail(
            id=v["id"],
            type="backend",
            stage=v.get("stage", "unknown"),
            description=v.get("description", ""),
            source=f"/proxy-frontend-wrapper/{v['id']}.py"
        )
        for v in BACKEND_VALIDATORS
    ]
