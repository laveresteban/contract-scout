import httpx
import respx

from app.models import VerifyStatus
from app.services.verify import verify_job


@respx.mock
async def test_live(make_job):
    respx.get("https://jobs.example.com/1").mock(
        return_value=httpx.Response(200, text="<h1>Apply now</h1> Great remote role.")
    )
    job = make_job()
    result = await verify_job(job)
    assert result["status"] == VerifyStatus.live.value
    assert result["cached"] is False
    assert job.verify_checked_at is not None


@respx.mock
async def test_expired_404(make_job):
    respx.get("https://jobs.example.com/1").mock(return_value=httpx.Response(404))
    result = await verify_job(make_job())
    assert result["status"] == VerifyStatus.expired.value
    assert result["http_status"] == 404


@respx.mock
async def test_dead_marker_on_200(make_job):
    respx.get("https://jobs.example.com/1").mock(
        return_value=httpx.Response(200, text="This position has been filled. Thanks!")
    )
    result = await verify_job(make_job())
    assert result["status"] == VerifyStatus.expired.value


@respx.mock
async def test_transient_failure_is_unreachable_not_expired(make_job):
    respx.get("https://jobs.example.com/1").mock(side_effect=httpx.ConnectTimeout("boom"))
    result = await verify_job(make_job())
    # A timeout must never be treated as expired.
    assert result["status"] == VerifyStatus.unreachable.value


@respx.mock
async def test_server_error_is_unreachable(make_job):
    respx.get("https://jobs.example.com/1").mock(return_value=httpx.Response(503))
    result = await verify_job(make_job())
    assert result["status"] == VerifyStatus.unreachable.value


async def test_no_url_is_unreachable(make_job):
    result = await verify_job(make_job(job_url=None, job_url_direct=None))
    assert result["status"] == VerifyStatus.unreachable.value


@respx.mock
async def test_fake_remote_flagged_in_detail(make_job):
    respx.get("https://jobs.example.com/1").mock(
        return_value=httpx.Response(200, text="This is a hybrid role, on-site 3 days a week.")
    )
    result = await verify_job(make_job(is_remote=True))
    assert result["status"] == VerifyStatus.live.value
    assert "remote is unverified" in result["detail"]


@respx.mock
async def test_cache_prevents_refetch(make_job):
    route = respx.get("https://jobs.example.com/1").mock(return_value=httpx.Response(200, text="open"))
    job = make_job()
    first = await verify_job(job)
    assert first["cached"] is False
    second = await verify_job(job)  # within cache window
    assert second["cached"] is True
    assert route.call_count == 1  # not re-fetched


@respx.mock
async def test_force_bypasses_cache(make_job):
    route = respx.get("https://jobs.example.com/1").mock(return_value=httpx.Response(200, text="open"))
    job = make_job()
    await verify_job(job)
    await verify_job(job, force=True)
    assert route.call_count == 2
