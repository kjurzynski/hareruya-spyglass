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
