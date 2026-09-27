from app.models import CheckRequest


def test_request_defaults():
    req = CheckRequest(cards=["Lightning Bolt"])
    assert req.finish == "all"
    assert req.output == "cheapest"
    assert req.language == "all"


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



def test_job_status_preserves_eur_jpy_rate():
    from app.models import JobStatus

    status = JobStatus(
        job_id="test",
        status="complete",
        completed=1,
        total=1,
        results=[],
        eur_jpy_rate=180.57,
    )
    assert status.eur_jpy_rate == 180.57


def test_request_language_filter():
    from app.models import CheckRequest

    assert CheckRequest(cards=["Lightning Bolt"], language="EN").language == "EN"
    assert CheckRequest(cards=["Lightning Bolt"], language="JP").language == "JP"
