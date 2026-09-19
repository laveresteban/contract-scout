import httpx
import respx

from app.models import VerifyStatus
from app.services.salary import normalize_yearly, parse_salary
from app.services.verify import verify_job


def test_parses_hourly_range():
    result = parse_salary("Contract rate: $95 - $120 per hour, W2 or C2C.")
    assert result["min_amount"] == 95
    assert result["max_amount"] == 120
    assert result["interval"] == "hourly"
    assert result["normalized_min_yearly"] == 95 * 2080


def test_parses_yearly_with_k_shorthand():
    result = parse_salary("Base salary $150k–$180k depending on experience.")
    assert result["min_amount"] == 150_000
    assert result["max_amount"] == 180_000
    assert result["interval"] == "yearly"
    assert result["normalized_max_yearly"] == 180_000


def test_parses_single_amount_in_pay_context():
    result = parse_salary("The salary for this position is $200,000 annually.")
    assert result["min_amount"] == result["max_amount"] == 200_000
    assert result["interval"] == "yearly"


def test_orders_reversed_range():
    result = parse_salary("Compensation: $120 to $95 /hr")
    assert result["min_amount"] == 95
    assert result["max_amount"] == 120


def test_ignores_text_without_pay_context():
    # No salary/pay/rate keyword nearby → don't guess off a stray dollar figure.
    assert parse_salary("Donate $50 to our foundation. Great remote team!") is None


def test_rejects_implausible_amounts():
    # A "$401k plan" mention shouldn't be read as a $401k salary… but a phone
    # number or headcount that normalizes absurdly high is dropped.
    assert parse_salary("Call 8005551234 about the pay rate today") is None


def test_normalize_passthrough_when_interval_unknown():
    assert normalize_yearly(100, 120, None) == (None, None)


@respx.mock
async def test_verify_scrapes_salary_from_live_page(make_job):
    respx.get("https://jobs.example.com/1").mock(
        return_value=httpx.Response(
            200, text="<p>Great remote role. Pay rate: $100 - $130 per hour.</p>"
        )
    )
    job = make_job(min_amount=None, max_amount=None)
    result = await verify_job(job)
    assert result["status"] == VerifyStatus.live.value
    assert job.min_amount == 100
    assert job.max_amount == 130
    assert job.interval == "hourly"
    assert result["normalized_min_yearly"] == 100 * 2080


@respx.mock
async def test_verify_keeps_existing_salary_without_force(make_job):
    respx.get("https://jobs.example.com/1").mock(
        return_value=httpx.Response(200, text="Pay rate: $200 - $250 per hour")
    )
    job = make_job(min_amount=95, max_amount=120, interval="hourly")
    await verify_job(job)
    # Original scrape wins unless the caller forces a refresh.
    assert job.min_amount == 95
    assert job.max_amount == 120
