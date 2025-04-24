import pytest
from services.backend_validators_registry import build_backend_proxy_entries

@pytest.mark.asyncio
async def test_backend_proxy_entries_structure():
    entries = await build_backend_proxy_entries()
    assert isinstance(entries, list)
    assert all(hasattr(e, "id") and e.type == "backend" for e in entries)
