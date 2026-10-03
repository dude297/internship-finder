"""Adversarial unit tests of `provider_identity` (ADR-013 §2): the ONLY identity parser
discovery is allowed to use. No database, no network. Synthetic boards and IDs only."""

from app.ingestion.adapters.community_feed import provider_identity
from app.ingestion.normalize import ASHBY, GREENHOUSE, LEVER, Identifier

GH_BOARD = "examplerobotics"
GH_JOB = "12345"
GH_ID = f"greenhouse:{GH_BOARD}:{GH_JOB}"

LEVER_SITE = "exampleinstitute"
LEVER_UUID = "0a1b2c3d-0000-4000-8000-000000000001"
LEVER_ID = f"lever:{LEVER_SITE}:{LEVER_UUID}"
LEVER_URL = f"https://jobs.lever.co/{LEVER_SITE}/{LEVER_UUID}"
LEVER_EU_URL = f"https://jobs.eu.lever.co/{LEVER_SITE}/{LEVER_UUID}"

ASHBY_BOARD = "example-board"
ASHBY_UUID = "1b2c3d4e-0000-4000-8000-000000000001"
ASHBY_ID = f"ashby:{ASHBY_BOARD}:{ASHBY_UUID}"
ASHBY_URL = f"https://jobs.ashbyhq.com/{ASHBY_BOARD}/{ASHBY_UUID}"


# --- Greenhouse: ID alone is identity; a matching-host URL naming another board conflicts -----


def test_greenhouse_id_alone_is_accepted_on_a_company_career_page() -> None:
    identity = provider_identity(GH_ID, "https://careers.example.com/jobs/123")
    assert identity == Identifier(namespace=GREENHOUSE, value=f"{GH_BOARD}:{GH_JOB}")


def test_greenhouse_id_alone_is_accepted_with_no_url() -> None:
    assert provider_identity(GH_ID, None) is not None


def test_greenhouse_host_naming_a_different_board_is_rejected() -> None:
    evil_url = "https://boards.greenhouse.io/some-other-board/jobs/999"
    assert provider_identity(GH_ID, evil_url) is None


def test_greenhouse_host_naming_the_same_board_is_accepted() -> None:
    url = f"https://job-boards.greenhouse.io/{GH_BOARD}/jobs/{GH_JOB}"
    assert provider_identity(GH_ID, url) is not None


def test_greenhouse_uppercase_board_in_id_normalizes() -> None:
    identity = provider_identity(f"greenhouse:{GH_BOARD.upper()}:{GH_JOB}", None)
    assert identity == Identifier(namespace=GREENHOUSE, value=f"{GH_BOARD}:{GH_JOB}")


# --- Lever: ID *and* a hosted URL with matching path must both agree --------------------------


def test_lever_requires_both_id_and_hosted_url() -> None:
    expected = Identifier(namespace=LEVER, value=f"global:{LEVER_SITE}:{LEVER_UUID}")
    assert provider_identity(LEVER_ID, LEVER_URL) == expected


def test_lever_eu_host_sets_region() -> None:
    expected = Identifier(namespace=LEVER, value=f"eu:{LEVER_SITE}:{LEVER_UUID}")
    assert provider_identity(LEVER_ID, LEVER_EU_URL) == expected


def test_lever_id_without_a_url_is_rejected() -> None:
    assert provider_identity(LEVER_ID, None) is None


def test_lever_id_with_a_career_page_url_is_rejected() -> None:
    assert provider_identity(LEVER_ID, "https://careers.example.com/jobs/1") is None


def test_lever_site_mismatch_in_url_path_is_rejected() -> None:
    url = f"https://jobs.lever.co/some-other-site/{LEVER_UUID}"
    assert provider_identity(LEVER_ID, url) is None


def test_lever_posting_mismatch_in_url_path_is_rejected() -> None:
    other_uuid = "0a1b2c3d-0000-4000-8000-000000000099"
    url = f"https://jobs.lever.co/{LEVER_SITE}/{other_uuid}"
    assert provider_identity(LEVER_ID, url) is None


def test_lever_uppercase_url_normalizes() -> None:
    url = f"https://jobs.lever.co/{LEVER_SITE.upper()}/{LEVER_UUID.upper()}"
    expected = Identifier(namespace=LEVER, value=f"global:{LEVER_SITE}:{LEVER_UUID}")
    assert provider_identity(LEVER_ID, url) == expected


# --- Ashby: lookalike hosts never match exactly ------------------------------------------------


def test_ashby_requires_both_id_and_hosted_url() -> None:
    expected = Identifier(namespace=ASHBY, value=f"{ASHBY_BOARD}:{ASHBY_UUID}")
    assert provider_identity(ASHBY_ID, ASHBY_URL) == expected


def test_ashby_suffix_lookalike_host_is_rejected() -> None:
    url = f"https://jobs.ashbyhq.com.evil.com/{ASHBY_BOARD}/{ASHBY_UUID}"
    assert provider_identity(ASHBY_ID, url) is None


def test_ashby_prefix_lookalike_host_is_rejected() -> None:
    url = f"https://evil-jobs.ashbyhq.com/{ASHBY_BOARD}/{ASHBY_UUID}"
    assert provider_identity(ASHBY_ID, url) is None


def test_ashby_dash_lookalike_host_is_rejected() -> None:
    url = f"https://jobs-ashbyhq.com/{ASHBY_BOARD}/{ASHBY_UUID}"
    assert provider_identity(ASHBY_ID, url) is None


# --- Cross-cutting link shape rules (greenhouse host rules don't apply, since ID alone wins
# there; these matter for Lever/Ashby, which require the hosted URL to actually match) ---------


def test_http_scheme_is_not_a_plain_posting_link() -> None:
    url = f"http://jobs.lever.co/{LEVER_SITE}/{LEVER_UUID}"
    assert provider_identity(LEVER_ID, url) is None


def test_userinfo_in_url_is_rejected() -> None:
    url = f"https://user:pass@jobs.ashbyhq.com/{ASHBY_BOARD}/{ASHBY_UUID}"
    assert provider_identity(ASHBY_ID, url) is None


def test_explicit_port_is_rejected() -> None:
    url = f"https://jobs.lever.co:8443/{LEVER_SITE}/{LEVER_UUID}"
    assert provider_identity(LEVER_ID, url) is None


def test_explicit_default_port_443_is_still_rejected() -> None:
    url = f"https://jobs.lever.co:443/{LEVER_SITE}/{LEVER_UUID}"
    assert provider_identity(LEVER_ID, url) is None


def test_percent_encoded_slash_in_path_is_rejected() -> None:
    url = f"https://jobs.ashbyhq.com/{ASHBY_BOARD}%2F{ASHBY_UUID}"
    assert provider_identity(ASHBY_ID, url) is None


def test_dot_dot_path_segment_is_rejected() -> None:
    url = f"https://jobs.lever.co/{LEVER_SITE}/../{LEVER_UUID}"
    assert provider_identity(LEVER_ID, url) is None


# --- Malformed IDs -------------------------------------------------------------------------------


def test_extra_colon_in_id_is_rejected() -> None:
    assert provider_identity(f"greenhouse:{GH_BOARD}:{GH_JOB}:extra", None) is None


def test_empty_board_segment_is_rejected() -> None:
    assert provider_identity(f"greenhouse::{GH_JOB}", None) is None


def test_overlong_slug_is_rejected() -> None:
    overlong = "a" * 65
    assert provider_identity(f"greenhouse:{overlong}:{GH_JOB}", None) is None


def test_non_digit_job_id_is_rejected() -> None:
    assert provider_identity(f"greenhouse:{GH_BOARD}:not-digits", None) is None


def test_non_uuid_lever_posting_is_rejected() -> None:
    assert provider_identity(f"lever:{LEVER_SITE}:not-a-uuid", LEVER_URL) is None


def test_unknown_provider_prefix_is_rejected() -> None:
    assert provider_identity("bamboohr:acme:1", None) is None


def test_feed_native_id_is_rejected() -> None:
    assert provider_identity("workday:example:/job/Synthetic-Intern_R1", None) is None
