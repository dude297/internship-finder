"""Ingestion without a database: the safe HTTP client, normalization helpers, and adapters.
All payloads are synthetic (tests/ingestion_fixtures.py)."""

import json
from datetime import UTC, date, datetime
from typing import Any

import httpx2
import pytest

from app.enums import (
    IngestionSourceKind,
    OpportunityType,
    RemoteMode,
    RequirementAppliesAt,
    RequirementType,
    SourceRegion,
)
from app.ingestion import http
from app.ingestion.adapters import SourceConfig, ashby, community_feed, greenhouse, lever
from app.ingestion.http import FetchError, check_url, fetch_json
from app.ingestion.normalize import (
    ItemError,
    NormalizedOpportunity,
    SnapshotError,
    canonical_url,
    classify_opportunity_type,
    html_to_text,
    is_internship_title,
    parse_timestamp,
)
from app.opportunities.eligibility.schemas import OpportunityInput, ProfileInput, RequirementInput
from app.repositories import eligibility_fingerprint
from tests.ingestion_fixtures import (
    ASHBY_BOARD,
    ASHBY_JOB_ID,
    FEED_URL,
    GREENHOUSE_BOARD,
    GREENHOUSE_URL,
    LEVER_POSTING_ID,
    LEVER_SITE,
    FakeSource,
    ashby_board,
    ashby_job,
    feed,
    feed_job,
    greenhouse_board,
    greenhouse_job,
    lever_posting,
)

FEED_SOURCE = SourceConfig(
    IngestionSourceKind.COMMUNITY_FEED, "zshah-tech-internships", None, "Discovery Feed"
)
GH_SOURCE = SourceConfig(IngestionSourceKind.GREENHOUSE, GREENHOUSE_BOARD, None, "Example Robotics")
LEVER_SOURCE = SourceConfig(
    IngestionSourceKind.LEVER, LEVER_SITE, SourceRegion.GLOBAL, "Example Institute"
)
ASHBY_SOURCE = SourceConfig(IngestionSourceKind.ASHBY, ASHBY_BOARD, None, "Example Board Inc.")


def fetch(source: FakeSource, url: str = FEED_URL, **kwargs: Any) -> http.Fetched:
    sleeps: list[float] = []
    result = fetch_json(url, transport=source.transport(), sleep=sleeps.append, **kwargs)
    return result


def only_items(items: list[NormalizedOpportunity | ItemError]) -> list[NormalizedOpportunity]:
    assert all(isinstance(i, NormalizedOpportunity) for i in items), items
    return [i for i in items if isinstance(i, NormalizedOpportunity)]


# --- URL policy ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://api.lever.co/v0/postings/x",  # not HTTPS
        "https://example.com/jobs.json",  # not allowlisted
        "https://localhost/api",
        "https://127.0.0.1/api",
        "file:///etc/passwd",
        "https://user:secret@api.lever.co/v0/postings/x",  # credentials
        "https://api.lever.co:8443/v0/postings/x",  # custom port
        "https://api.lever.co.evil.example/v0/postings/x",
    ],
)
def test_only_allowlisted_https_urls_are_fetched(url: str) -> None:
    with pytest.raises(FetchError) as error:
        check_url(url, resolve=None)
    assert error.value.code == "blocked_url"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.8", "192.168.1.1", "169.254.169.254"])
def test_allowlisted_host_resolving_inward_is_refused(address: str) -> None:
    with pytest.raises(FetchError) as error:
        check_url("https://api.lever.co/v0/postings/x", resolve=lambda _host: [address])
    assert error.value.code == "blocked_url"


def test_allowlisted_host_resolving_publicly_is_allowed() -> None:
    check_url(
        "https://api.lever.co/v0/postings/x",
        resolve=lambda _host: ["1.1.1.1", "2606:4700:4700::1111"],
    )


# --- HTTP client --------------------------------------------------------------------------------


def test_fetch_returns_json_and_validators_and_sends_a_user_agent() -> None:
    source = FakeSource()
    validators = {"ETag": '"v1"', "Last-Modified": "Thu, 20 Sep 2040"}
    source.json(FEED_URL, {"jobs": []}, headers=validators)

    result = fetch(source)

    assert result.data == {"jobs": []}
    assert (result.etag, result.last_modified) == ('"v1"', "Thu, 20 Sep 2040")
    assert "PersonalInternshipFinder" in source.requests[0].headers["User-Agent"]


def test_conditional_request_and_304() -> None:
    source = FakeSource()
    source.respond(FEED_URL, lambda _r: httpx2.Response(304))

    result = fetch(source, etag='"v1"', last_modified="Thu, 20 Sep 2040")

    assert result.not_modified
    assert source.requests[0].headers["If-None-Match"] == '"v1"'
    assert source.requests[0].headers["If-Modified-Since"] == "Thu, 20 Sep 2040"


def test_server_errors_are_retried_a_bounded_number_of_times() -> None:
    source = FakeSource()
    source.respond(FEED_URL, lambda _r: httpx2.Response(500))

    with pytest.raises(FetchError) as error:
        fetch(source)

    assert error.value.code == "http_error"
    assert len(source.requests) == http.MAX_ATTEMPTS


def test_a_transient_error_then_success() -> None:
    source = FakeSource()
    answers = iter([httpx2.Response(503), httpx2.Response(200, json={"jobs": []})])
    source.respond(FEED_URL, lambda _r: next(answers))

    assert fetch(source).data == {"jobs": []}


def test_timeouts_are_retried_then_fail() -> None:
    source = FakeSource()

    def timeout(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("synthetic timeout", request=request)

    source.respond(FEED_URL, timeout)

    with pytest.raises(FetchError) as error:
        fetch(source)
    assert error.value.code == "timeout"
    assert len(source.requests) == http.MAX_ATTEMPTS


def test_429_honors_a_short_retry_after() -> None:
    source = FakeSource()
    answers = iter(
        [httpx2.Response(429, headers={"Retry-After": "2"}), httpx2.Response(200, json=[])]
    )
    source.respond(FEED_URL, lambda _r: next(answers))
    sleeps: list[float] = []

    result = fetch_json(FEED_URL, transport=source.transport(), sleep=sleeps.append)

    assert result.data == []
    assert sleeps == [2.0]


def test_429_with_a_long_retry_after_fails_instead_of_waiting() -> None:
    source = FakeSource()
    source.respond(FEED_URL, lambda _r: httpx2.Response(429, headers={"Retry-After": "3600"}))

    with pytest.raises(FetchError) as error:
        fetch(source)
    assert error.value.code == "rate_limited"
    assert len(source.requests) == 1


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (
            httpx2.Response(
                200, content=b"{not json", headers={"Content-Type": "application/json"}
            ),
            "invalid_json",
        ),
        (
            httpx2.Response(200, content=b"<html></html>", headers={"Content-Type": "text/html"}),
            "unexpected_content_type",
        ),
        (httpx2.Response(404), "not_found"),
        (httpx2.Response(403), "http_error"),
    ],
)
def test_unusable_responses(response: httpx2.Response, code: str) -> None:
    source = FakeSource()
    source.respond(FEED_URL, lambda _r: response)

    with pytest.raises(FetchError) as error:
        fetch(source)
    assert error.value.code == code


def test_oversized_responses_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "MAX_BYTES", 100)
    source = FakeSource()
    source.json(FEED_URL, {"jobs": ["x" * 200]})

    with pytest.raises(FetchError) as error:
        fetch(source)
    assert error.value.code == "response_too_large"


def test_oversized_stream_without_content_length_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http, "MAX_BYTES", 100)
    source = FakeSource()
    chunks = [b'{"jobs": ["' + b"x" * 60, b"x" * 60 + b'"]}']
    source.respond(
        FEED_URL,
        lambda _r: httpx2.Response(
            200, content=iter(chunks), headers={"Content-Type": "application/json"}
        ),
    )

    with pytest.raises(FetchError) as error:
        fetch(source)
    assert error.value.code == "response_too_large"


def test_redirects_stay_on_the_allowlist() -> None:
    source = FakeSource()
    source.respond(
        FEED_URL,
        lambda _r: httpx2.Response(302, headers={"Location": "https://api.lever.co/v0/postings/x"}),
    )
    source.json("https://api.lever.co/v0/postings/x", [])
    assert fetch(source).data == []

    source.respond(
        FEED_URL, lambda _r: httpx2.Response(302, headers={"Location": "https://example.com/x"})
    )
    with pytest.raises(FetchError) as error:
        fetch(source)
    assert error.value.code == "blocked_url"


def test_redirect_loops_are_bounded() -> None:
    source = FakeSource()
    source.respond(FEED_URL, lambda _r: httpx2.Response(302, headers={"Location": FEED_URL}))

    with pytest.raises(FetchError) as error:
        fetch(source)
    assert error.value.code == "too_many_redirects"


def test_fixture_transport_serves_the_mapping(tmp_path: Any) -> None:
    fixture = tmp_path / "responses.json"
    fixture.write_text(json.dumps({FEED_URL: {"jobs": []}}), encoding="utf-8")

    transport = http.fixture_transport(str(fixture))

    assert fetch_json(FEED_URL, transport=transport).data == {"jobs": []}
    with pytest.raises(FetchError):
        fetch_json(GREENHOUSE_URL, transport=transport)


# --- Helpers ------------------------------------------------------------------------------------


def test_html_to_text_is_plain_text() -> None:
    html = (
        '<p>Hello <b>there</b></p><script>alert("x")</script><style>p{}</style>'
        "<ul><li>One</li></ul>"
    )
    assert html_to_text(html) == "Hello there\n\n• One"
    assert html_to_text("&lt;p&gt;A &amp;amp; B&lt;/p&gt;", entity_escaped=True) == "A & B"
    assert html_to_text("<img src=x onerror=alert(1)>") is None
    assert html_to_text(None) is None


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        (
            "HTTPS://Jobs.Example.COM:443/Role/1?b=2&a=1#apply",
            "https://jobs.example.com/Role/1?b=2&a=1",
        ),
        ("https://jobs.example.com:8443/x", "https://jobs.example.com:8443/x"),
        ("https://jobs.example.com/", None),  # a home page isn't a posting identity
        ("https://jobs.example.com", None),
        ("javascript:alert(1)", None),
        ("https://user:pw@jobs.example.com/x", None),
        (None, None),
    ],
)
def test_canonical_url(url: str | None, canonical: str | None) -> None:
    assert canonical_url(url) == canonical


def test_parse_timestamp() -> None:
    assert parse_timestamp("2040-09-20T00:00:00Z") == datetime(2040, 9, 20, tzinfo=UTC)
    assert parse_timestamp(2231100000000) == datetime(2040, 9, 12, 22, tzinfo=UTC)
    assert parse_timestamp("2040-09-20T00:00:00") is None  # no timezone: not guessed
    assert parse_timestamp("yesterday") is None
    assert parse_timestamp(True) is None


# --- Discovery feed -----------------------------------------------------------------------------


def test_feed_mapping_keeps_signals_out_of_canonical_fields() -> None:
    job = feed_job(
        "greenhouse:ExampleRobotics:1001",
        url="https://job-boards.greenhouse.io/examplerobotics/jobs/1001",
        remote=True,
    )

    [item] = only_items(community_feed.parse(feed(job), FEED_SOURCE).items)

    assert item.external_id == "greenhouse:ExampleRobotics:1001"
    assert item.title == "Synthetic Engineering Intern"
    assert item.organization == "Example Robotics"
    assert item.opportunity_type is OpportunityType.INTERNSHIP
    assert item.remote_mode is RemoteMode.REMOTE
    assert item.posted_at == datetime(2040, 9, 20, tzinfo=UTC)
    assert item.description is None
    assert {(i.namespace, i.value) for i in item.identifiers} == {
        ("zshah", "greenhouse:ExampleRobotics:1001"),
        ("greenhouse", "examplerobotics:1001"),
        ("url", "https://job-boards.greenhouse.io/examplerobotics/jobs/1001"),
    }
    # Sponsorship, skills, and H-1B data are kept only as raw provenance.
    assert item.raw_payload["sponsorship"] == "citizens-only"
    assert "citizens" not in item.model_dump_json(exclude={"raw_payload"})


@pytest.mark.parametrize(
    ("item_id", "url", "expected"),
    [
        (
            f"lever:{LEVER_SITE}:{LEVER_POSTING_ID}",
            f"https://jobs.lever.co/{LEVER_SITE}/{LEVER_POSTING_ID}",
            ("lever", f"global:{LEVER_SITE}:{LEVER_POSTING_ID}"),
        ),
        (
            f"lever:{LEVER_SITE}:{LEVER_POSTING_ID}",
            f"https://jobs.eu.lever.co/{LEVER_SITE}/{LEVER_POSTING_ID}/apply",
            ("lever", f"eu:{LEVER_SITE}:{LEVER_POSTING_ID}"),
        ),
        # Region unknown or URL disagrees: never guessed.
        (f"lever:{LEVER_SITE}:{LEVER_POSTING_ID}", "https://careers.example.com/x", None),
        (
            f"lever:{LEVER_SITE}:{LEVER_POSTING_ID}",
            f"https://jobs.lever.co/othersite/{LEVER_POSTING_ID}",
            None,
        ),
        ("greenhouse:examplerobotics:12ab", "https://careers.example.com/x", None),
        ("greenhouse:examplerobotics:", "https://careers.example.com/x", None),
        ("ashby:example:abc", "https://careers.example.com/x", None),  # not supported directly
    ],
)
def test_feed_provider_identity_only_when_exact(
    item_id: str, url: str, expected: tuple[str, str] | None
) -> None:
    identity = community_feed.provider_identity(item_id, url)
    assert (identity.namespace, identity.value) == expected if identity else expected is None


def test_feed_program_and_remote_are_mapped_only_when_unambiguous() -> None:
    # Titles deliberately don't say "intern" here: this test is about the *program* field being
    # ambiguous, not the title-fallback matcher (covered separately below).
    items = only_items(
        community_feed.parse(
            feed(
                feed_job("a", title="Synthetic Engineering Analyst", program="Co-op", remote=False),
                feed_job(
                    "b",
                    title="Synthetic Engineering Analyst",
                    program="Internship / Co-op",
                    remote=None,
                ),
            ),
            FEED_SOURCE,
        ).items
    )
    assert [i.opportunity_type for i in items] == [OpportunityType.OTHER, OpportunityType.OTHER]
    assert [i.remote_mode for i in items] == [None, None]


def test_feed_falls_back_to_title_when_program_isnt_structured_intern() -> None:
    [item] = only_items(
        community_feed.parse(
            feed(feed_job("c", title="Synthetic Engineering Intern", program="Co-op")),
            FEED_SOURCE,
        ).items
    )
    assert item.opportunity_type is OpportunityType.INTERNSHIP


def test_feed_bad_items_are_item_errors_not_snapshot_failures() -> None:
    snapshot = community_feed.parse(
        feed(feed_job("ok"), feed_job("no-title", title=None), "not an object", {"id": "x"}),
        FEED_SOURCE,
    )
    kinds = [type(i).__name__ for i in snapshot.items]
    assert kinds == ["NormalizedOpportunity", "ItemError", "ItemError", "ItemError"]
    errors = [i for i in snapshot.items if isinstance(i, ItemError)]
    assert errors[0].external_id == "no-title"
    assert snapshot.generated_at == datetime(2040, 9, 21, 6, tzinfo=UTC)


def test_feed_long_fields_are_bounded_and_bad_urls_dropped() -> None:
    [item] = only_items(
        community_feed.parse(
            feed(feed_job(location="L" * 400, url="javascript:alert(1)")), FEED_SOURCE
        ).items
    )
    assert item.location is not None and len(item.location) == 200
    assert item.application_url is None
    assert item.raw_payload["location"] == "L" * 400  # the raw payload keeps the original


@pytest.mark.parametrize(
    "payload",
    [[], {"jobs": "nope"}, {"items": []}, "text", None],
)
def test_feed_top_level_mismatch(payload: Any) -> None:
    with pytest.raises(SnapshotError) as error:
        community_feed.parse(payload, FEED_SOURCE)
    assert error.value.code == "schema_mismatch"


def test_feed_declared_count_must_match() -> None:
    with pytest.raises(SnapshotError) as error:
        community_feed.parse(feed(feed_job(), count=2), FEED_SOURCE)
    assert error.value.code == "incomplete_snapshot"


# --- Greenhouse ---------------------------------------------------------------------------------


def test_greenhouse_mapping() -> None:
    [item] = only_items(greenhouse.parse(greenhouse_board(greenhouse_job()), GH_SOURCE).items)

    assert item.external_id == "1001"
    assert item.organization == "Example Robotics"  # the configured organization
    assert item.description == "Build synthetic robots.\n\n• Python"  # script dropped
    assert item.location == "Example City"
    assert item.opportunity_type is OpportunityType.INTERNSHIP  # title-based: "...Robotics Intern"
    assert item.posted_at == item.source_published_at
    assert item.source_updated_at is not None and item.source_updated_at != item.posted_at
    assert ("greenhouse", "examplerobotics:1001") in {
        (i.namespace, i.value) for i in item.identifiers
    }


def test_greenhouse_non_intern_title_is_other() -> None:
    [item] = only_items(
        greenhouse.parse(
            greenhouse_board(greenhouse_job(title="Synthetic Robotics Engineer")), GH_SOURCE
        ).items
    )
    assert item.opportunity_type is OpportunityType.OTHER


def test_greenhouse_incomplete_board_fails() -> None:
    body = greenhouse_board(greenhouse_job())
    body["meta"]["total"] = 5
    with pytest.raises(SnapshotError):
        greenhouse.parse(body, GH_SOURCE)


@pytest.mark.parametrize(
    ("value", "token"),
    [
        ("examplerobotics", "examplerobotics"),
        ("ExampleRobotics", "examplerobotics"),
        ("https://boards.greenhouse.io/examplerobotics", "examplerobotics"),
        ("https://job-boards.greenhouse.io/examplerobotics/jobs/1001?gh_src=x", "examplerobotics"),
        ("job-boards.greenhouse.io/examplerobotics", "examplerobotics"),
    ],
)
def test_greenhouse_board_reference(value: str, token: str) -> None:
    assert greenhouse.parse_board_reference(value) == token


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/examplerobotics",
        "https://boards.greenhouse.io/",
        "http://169.254.169.254/latest",
        "bad token!",
        "",
        "https://boards-api.greenhouse.io/v1/boards/x/jobs",
        "https://user:pw@boards.greenhouse.io/examplerobotics",
        "https://user@job-boards.greenhouse.io/examplerobotics",
        "https://boards.greenhouse.io:8443/examplerobotics",
        "https://boards.greenhouse.io:443/examplerobotics",
        "https://boards.greenhouse.io:bad/examplerobotics",
    ],
)
def test_greenhouse_board_reference_rejects(value: str) -> None:
    with pytest.raises(ValueError):
        greenhouse.parse_board_reference(value)


# --- Lever --------------------------------------------------------------------------------------


def test_lever_mapping() -> None:
    [item] = only_items(lever.parse([lever_posting()], LEVER_SOURCE).items)

    assert item.title == "Synthetic Research Intern"
    assert item.organization == "Example Institute"
    assert item.opportunity_type is OpportunityType.INTERNSHIP
    assert item.remote_mode is RemoteMode.HYBRID
    assert item.posted_at == datetime(2040, 9, 12, 22, tzinfo=UTC)
    assert (
        item.description
        == "Study synthetic data.\n\nRequirements\n\n• Curiosity\n\nFictional posting."
    )
    assert ("lever", f"global:{LEVER_SITE}:{LEVER_POSTING_ID}") in {
        (i.namespace, i.value) for i in item.identifiers
    }


def test_lever_unknown_workplace_and_commitment() -> None:
    [item] = only_items(
        lever.parse(
            [
                lever_posting(
                    text="Synthetic Research Associate",
                    workplaceType="unspecified",
                    categories={"commitment": "Full-time"},
                )
            ],
            LEVER_SOURCE,
        ).items
    )
    assert item.remote_mode is None
    assert item.opportunity_type is OpportunityType.OTHER


def test_lever_falls_back_to_title_when_commitment_isnt_structured_intern() -> None:
    [item] = only_items(
        lever.parse(
            [lever_posting(text="Synthetic Internship, Hardware", categories={"commitment": ""})],
            LEVER_SOURCE,
        ).items
    )
    assert item.opportunity_type is OpportunityType.INTERNSHIP


def test_lever_top_level_must_be_a_list() -> None:
    with pytest.raises(SnapshotError):
        lever.parse({"postings": []}, LEVER_SOURCE)


@pytest.mark.parametrize(
    ("value", "region", "expected"),
    [
        ("exampleinstitute", None, ("exampleinstitute", SourceRegion.GLOBAL)),
        ("exampleinstitute", SourceRegion.EU, ("exampleinstitute", SourceRegion.EU)),
        ("https://jobs.lever.co/exampleinstitute", None, ("exampleinstitute", SourceRegion.GLOBAL)),
        (
            "https://jobs.eu.lever.co/ExampleInstitute/abc",
            None,
            ("exampleinstitute", SourceRegion.EU),
        ),
    ],
)
def test_lever_site_reference(
    value: str, region: SourceRegion | None, expected: tuple[str, SourceRegion]
) -> None:
    assert lever.parse_site_reference(value, region) == expected


@pytest.mark.parametrize(
    ("value", "region"),
    [
        ("https://jobs.lever.co/exampleinstitute", SourceRegion.EU),  # conflicting region
        ("https://api.lever.co/v0/postings/x", None),
        ("https://evil.example/exampleinstitute", None),
        ("x y", None),
        ("https://user:pw@jobs.lever.co/exampleinstitute", None),
        ("https://jobs.lever.co:8443/exampleinstitute", None),
        ("https://jobs.eu.lever.co:443/exampleinstitute", None),
    ],
)
def test_lever_site_reference_rejects(value: str, region: SourceRegion | None) -> None:
    with pytest.raises(ValueError):
        lever.parse_site_reference(value, region)


# --- Ashby ---------------------------------------------------------------------------------------


def test_ashby_mapping() -> None:
    [item] = only_items(ashby.parse(ashby_board(ashby_job()), ASHBY_SOURCE).items)

    assert item.external_id == ASHBY_JOB_ID
    assert item.organization == "Example Board Inc."
    assert item.opportunity_type is OpportunityType.INTERNSHIP  # structured: employmentType
    assert item.remote_mode is RemoteMode.HYBRID
    assert item.location == "Example City · Remote - Example Country"
    assert item.description == "Build synthetic data pipelines.\n- Python"  # descriptionPlain wins
    assert item.application_url == f"https://jobs.ashbyhq.com/{ASHBY_BOARD}/{ASHBY_JOB_ID}"
    assert item.posted_at == datetime(2040, 9, 5, 9, tzinfo=UTC)
    assert ("ashby", f"{ASHBY_BOARD}:{ASHBY_JOB_ID}") in {
        (i.namespace, i.value) for i in item.identifiers
    }
    assert ("url", f"https://jobs.ashbyhq.com/{ASHBY_BOARD}/{ASHBY_JOB_ID}") in {
        (i.namespace, i.value) for i in item.identifiers
    }


def test_ashby_description_falls_back_to_html_when_plain_is_missing() -> None:
    [item] = only_items(
        ashby.parse(
            ashby_board(
                ashby_job(
                    descriptionPlain=None,
                    descriptionHtml="<p>Build <b>robots</b>.</p><script>bad()</script>",
                )
            ),
            ASHBY_SOURCE,
        ).items
    )
    assert item.description == "Build robots."


def test_ashby_non_intern_title_is_other() -> None:
    [item] = only_items(
        ashby.parse(
            ashby_board(ashby_job(employmentType="FullTime", title="Synthetic Data Engineer")),
            ASHBY_SOURCE,
        ).items
    )
    assert item.opportunity_type is OpportunityType.OTHER


def test_ashby_falls_back_to_title_when_employment_type_isnt_structured_intern() -> None:
    [item] = only_items(
        ashby.parse(
            ashby_board(ashby_job(employmentType="FullTime", title="Synthetic Summer Intern")),
            ASHBY_SOURCE,
        ).items
    )
    assert item.opportunity_type is OpportunityType.INTERNSHIP


def test_ashby_isremote_fallback_without_workplace_type() -> None:
    [on, off] = only_items(
        ashby.parse(
            ashby_board(
                ashby_job("a", workplaceType=None, isRemote=True),
                ashby_job("b", workplaceType=None, isRemote=False),
            ),
            ASHBY_SOURCE,
        ).items
    )
    assert on.remote_mode is RemoteMode.REMOTE
    assert off.remote_mode is None  # isRemote: false doesn't mean on-site


def test_ashby_unlisted_jobs_are_excluded() -> None:
    snapshot = ashby.parse(
        ashby_board(ashby_job("a", isListed=True), ashby_job("b", isListed=False)), ASHBY_SOURCE
    )
    [item] = only_items(snapshot.items)
    assert item.external_id == "a"


def test_ashby_missing_islisted_is_treated_as_listed() -> None:
    job = ashby_job()
    del job["isListed"]
    [item] = only_items(ashby.parse(ashby_board(job), ASHBY_SOURCE).items)
    assert item.external_id == ASHBY_JOB_ID


def test_ashby_bad_items_are_item_errors_not_snapshot_failures() -> None:
    snapshot = ashby.parse(
        ashby_board(ashby_job(), ashby_job("no-title", title=None), "not an object"), ASHBY_SOURCE
    )
    kinds = [type(i).__name__ for i in snapshot.items]
    assert kinds == ["NormalizedOpportunity", "ItemError", "ItemError"]
    errors = [i for i in snapshot.items if isinstance(i, ItemError)]
    assert errors[0].external_id == "no-title"


@pytest.mark.parametrize(
    "payload",
    [[], {"jobs": "nope"}, {"items": []}, "text", None],
)
def test_ashby_top_level_mismatch(payload: Any) -> None:
    with pytest.raises(SnapshotError) as error:
        ashby.parse(payload, ASHBY_SOURCE)
    assert error.value.code == "schema_mismatch"


@pytest.mark.parametrize(
    ("value", "name"),
    [
        ("example-board", "example-board"),
        ("Example-Board", "example-board"),  # case-insensitive at the provider: lowered
        ("https://jobs.ashbyhq.com/Example-Board", "example-board"),
        (f"https://jobs.ashbyhq.com/example-board/{ASHBY_JOB_ID}", "example-board"),
        ("jobs.ashbyhq.com/example-board", "example-board"),
    ],
)
def test_ashby_board_reference(value: str, name: str) -> None:
    assert ashby.parse_board_reference(value) == name


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/example-board",
        "https://jobs.ashbyhq.com/",
        "https://jobs.ashbyhq.com.evil.test/example-board",  # lookalike host
        "https://evil-ashbyhq.com/example-board",  # lookalike host
        "http://169.254.169.254/latest",
        "bad board!",
        "",
        "https://api.ashbyhq.com/posting-api/job-board/example-board",
        "https://user:pw@jobs.ashbyhq.com/example-board",
        "https://user@jobs.ashbyhq.com/example-board",
        "https://jobs.ashbyhq.com:8443/example-board",
        "https://jobs.ashbyhq.com:443/example-board",
        "https://jobs.ashbyhq.com:bad/example-board",
        "https://jobs.ashbyhq.com/%2e%2e%2fadmin",  # encoded traversal still rejected by SLUG
        "https://jobs.ashbyhq.com/example board",  # whitespace in the segment
        "a" * 65,  # too long for the identifier column
    ],
)
def test_ashby_board_reference_rejects(value: str) -> None:
    with pytest.raises(ValueError):
        ashby.parse_board_reference(value)


# --- Classification -------------------------------------------------------------------------------


def test_classify_opportunity_type_structured_signal_wins() -> None:
    assert (
        classify_opportunity_type("Software Engineer", structured_intern=True)
        is OpportunityType.INTERNSHIP
    )


def test_classify_opportunity_type_falls_back_to_title() -> None:
    assert (
        classify_opportunity_type("Software Engineering Intern", structured_intern=False)
        is OpportunityType.INTERNSHIP
    )
    assert classify_opportunity_type("Senior Software Engineer") is OpportunityType.OTHER


# --- Evaluation fingerprint ---------------------------------------------------------------------


def test_fingerprint_ignores_requirement_order_and_ids_but_not_values() -> None:
    profile = ProfileInput(date_of_birth=date(2023, 6, 20))
    opportunity = OpportunityInput(start_date=date(2041, 6, 20))
    age = RequirementInput(requirement_type=RequirementType.MINIMUM_AGE, value={"years": 16})
    cit = RequirementInput(
        requirement_type=RequirementType.CITIZENSHIP,
        value={"countries": ["US"]},
        applies_at=RequirementAppliesAt.PROGRAM_START,
    )
    base = eligibility_fingerprint(profile, opportunity, [age, cit])

    assert base == eligibility_fingerprint(profile, opportunity, [cit, age.model_copy()])
    assert len(base) == 64
    older = age.model_copy(update={"value": {"years": 18}})
    assert base != eligibility_fingerprint(profile, opportunity, [older, cit])
    moved = OpportunityInput(start_date=date(2041, 6, 21))
    assert base != eligibility_fingerprint(profile, moved, [age, cit])
    assert base != eligibility_fingerprint(ProfileInput(), opportunity, [age, cit])


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineering Intern",
        "Summer 2041 Internship - Robotics",
        "Interns: Synthetic Data",
        "Co-op, Hardware (Fall)",
        "Co op Student",
        "Engineering COOP",
        "Mechanical Co-ops",
        "Electrician Apprentice",
        "Apprenticeship Program",
        "INTERN – Synthetic Lab",
        "Research Intern/Associate",
    ],
)
def test_internship_titles(title: str) -> None:
    assert is_internship_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "Senior Software Engineer",
        "Internal Tools Engineer",
        "International Sales Manager",
        "Cooperative Robotics Engineer",
        "Co-operative Systems Lead",
        "Student Success Manager",
        "New Grad Software Engineer",
        "Junior Data Analyst",
        "Entry Level Technician",
    ],
)
def test_non_internship_titles(title: str) -> None:
    assert not is_internship_title(title)
