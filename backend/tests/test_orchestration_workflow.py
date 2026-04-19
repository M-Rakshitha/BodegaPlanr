from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_orchestration_full_workflow_dc_address() -> None:
    """Runs Agent 1 -> Agent 2+3 -> Agent 4 through orchestration on a real address."""
    client = TestClient(app)

    response = client.post(
        "/orchestration/run",
        json={
            "address": "2121 I St NW, Washington, DC 20052",
            "include_religion": True,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body.get("agent1"), "Missing agent1 output"
    assert body.get("agent2"), "Missing agent2 output"
    assert body.get("agent3"), "Missing agent3 output"
    assert body.get("agent4"), "Missing agent4 output"

    agent2 = body["agent2"]
    agent3 = body["agent3"]
    agent4 = body["agent4"]

    assert isinstance(agent2.get("top_items"), list)
    assert isinstance(agent3.get("top_items"), list)
    assert isinstance(body.get("combined_top_suggestions"), list)

    # Combined suggestions should include at least one item from either agent2 or agent3.
    assert len(body["combined_top_suggestions"]) > 0

    # Agent 4 should return a structured list even if some lookups fail.
    assert isinstance(agent4.get("recommendations"), list)

    # Basic schema sanity checks for top recommendation shape when available.
    if agent4["recommendations"]:
        first = agent4["recommendations"][0]
        assert "product" in first
        assert "suggested_vendor" in first
