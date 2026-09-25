from app.models import CheckRequest


def test_request_defaults():
    req = CheckRequest(cards=["Lightning Bolt"])
    assert req.finish == "all"
    assert req.output == "cheapest"


def test_request_both_output():
    req = CheckRequest(cards=["Lightning Bolt"], output="both")
    assert req.output == "both"


def test_job_status_preserves_output_mode():
    from app.models import JobStatus

    status = JobStatus(
        job_id="test",
        status="complete",
        completed=1,
        total=1,
        results=[],
        output="both",
    )
    assert status.output == "both"


def test_yen_to_eur():
    from decimal import Decimal
    from app.currency import yen_to_eur

    assert yen_to_eur(10000, Decimal("180")) == Decimal("55.55555555555555555555555556")


def test_request_allows_110_cards():
    req = CheckRequest(cards=[f"Card {i}" for i in range(110)])
    assert len(req.cards) == 110


def test_request_rejects_111_cards():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CheckRequest(cards=[f"Card {i}" for i in range(111)])
