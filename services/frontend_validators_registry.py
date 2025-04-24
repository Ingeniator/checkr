from schemas.validators import ValidatorDetail

async def fetch_frontend_validators() -> list[ValidatorDetail]:
    # Simulated fetch
    return [
        ValidatorDetail(
            id="summary-style-check",
            type="frontend",
            stage="experimental",
            description="Checks summary style and punctuation.",
            source="/frontend-validators/summary-style-check.py"
        )
    ]