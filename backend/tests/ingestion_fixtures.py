"""Fabricated provider payloads for ingestion tests. They mimic the public schemas of the
discovery feed, Greenhouse, and Lever, but every company, posting, and date is fictional.
Never paste real postings here."""

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx2

from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER, FEEDS

FEED_URL = FEEDS[BUILTIN_IDENTIFIER]
GREENHOUSE_BOARD = "examplerobotics"
GREENHOUSE_URL = f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs?content=true"
LEVER_SITE = "exampleinstitute"
LEVER_URL = f"https://api.lever.co/v0/postings/{LEVER_SITE}?mode=json"
LEVER_EU_URL = f"https://api.eu.lever.co/v0/postings/{LEVER_SITE}?mode=json"
LEVER_POSTING_ID = "0a1b2c3d-0000-4000-8000-000000000001"
ASHBY_BOARD = "example-board"
ASHBY_URL = f"https://api.ashbyhq.com/posting-api/job-board/{ASHBY_BOARD}?includeCompensation=false"
ASHBY_JOB_ID = "1b2c3d4e-0000-4000-8000-000000000001"


def feed_job(
    job_id: str = "workday:example:/job/Synthetic-Intern_R1", **changes: Any
) -> dict[str, Any]:
    job: dict[str, Any] = {
        "id": job_id,
        "company": "Example Robotics",
        "title": "Synthetic Engineering Intern",
        "season": "Summer 2041",
        "seasons": None,
        "season_inferred": False,
        "category": "Software",
        "location": "Example City",
        "url": f"https://careers.example.com/jobs/{quote(job_id, safe='')}",
        "posted_at": "2040-09-20T00:00:00Z",
        "posted_at_source": "date_only",
        "first_seen_at": "2040-09-20T12:00:00Z",
        # Informational only; must never become a requirement.
        "sponsorship": "citizens-only",
        "salary": "$20/hr",
        "skills": ["Python", "SQL"],
        "source": "workday",
        "h1b_approvals": 12,
        "program": "Internship",
        "remote": False,
    }
    return job | changes


def feed(*jobs: Any, **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "generated_at": "2040-09-21T06:00:00Z",
        "data_as_of": "2040-09-21T06:00:00Z",
        "source": "https://example.org/synthetic-feed",
        "count": len(jobs),
        "jobs": list(jobs),
    }
    return body | changes


def greenhouse_job(job_id: int = 1001, **changes: Any) -> dict[str, Any]:
    job: dict[str, Any] = {
        "id": job_id,
        "internal_job_id": job_id + 5000,
        "title": "Synthetic Robotics Intern",
        "absolute_url": f"https://job-boards.greenhouse.io/{GREENHOUSE_BOARD}/jobs/{job_id}",
        "location": {"name": "Example City"},
        "updated_at": "2040-09-15T10:00:00-04:00",
        "first_published": "2040-09-01T09:00:00-04:00",
        "requisition_id": "SYN-1",
        "company_name": "Example Robotics",
        "language": "en",
        "metadata": None,
        # Greenhouse delivers entity-escaped HTML.
        "content": (
            "&lt;p&gt;Build &lt;strong&gt;synthetic&lt;/strong&gt; robots.&lt;/p&gt;"
            "&lt;script&gt;alert(1)&lt;/script&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"
        ),
        "departments": [{"id": 1, "name": "Engineering", "child_ids": [], "parent_id": None}],
        "offices": [{"id": 2, "name": "Example City", "location": "Example City"}],
    }
    return job | changes


def greenhouse_board(*jobs: dict[str, Any]) -> dict[str, Any]:
    return {"jobs": list(jobs), "meta": {"total": len(jobs)}}


def lever_posting(posting_id: str = LEVER_POSTING_ID, **changes: Any) -> dict[str, Any]:
    posting: dict[str, Any] = {
        "id": posting_id,
        "text": "Synthetic Research Intern",
        "categories": {
            "commitment": "Intern",
            "department": "Research",
            "location": "Example City",
            "team": "Synthetic Lab",
            "allLocations": ["Example City"],
        },
        "country": "US",
        "workplaceType": "hybrid",
        "createdAt": 2231100000000,  # 2040-09-12T22:00Z (epoch milliseconds)
        "description": "<div>Study <b>synthetic</b> data.</div>",
        "descriptionPlain": "Study synthetic data.",
        "lists": [{"text": "Requirements", "content": "<li>Curiosity</li>"}],
        "additional": "<div>Fictional posting.</div>",
        "hostedUrl": f"https://jobs.lever.co/{LEVER_SITE}/{posting_id}",
        "applyUrl": f"https://jobs.lever.co/{LEVER_SITE}/{posting_id}/apply",
    }
    return posting | changes


def ashby_job(job_id: str = ASHBY_JOB_ID, **changes: Any) -> dict[str, Any]:
    job: dict[str, Any] = {
        "id": job_id,
        "title": "Synthetic Data Science Intern",
        "department": "Engineering",
        "team": "Synthetic Lab",
        "employmentType": "Intern",
        "location": "Example City",
        "secondaryLocations": [{"location": "Remote - Example Country"}],
        "isRemote": False,
        "workplaceType": "Hybrid",
        "address": {"postalAddress": {"addressLocality": "Example City"}},
        "publishedAt": "2040-09-05T09:00:00.000+00:00",
        "isListed": True,
        "jobUrl": f"https://jobs.ashbyhq.com/{ASHBY_BOARD}/{job_id}",
        "applyUrl": f"https://jobs.ashbyhq.com/{ASHBY_BOARD}/{job_id}/application",
        "descriptionHtml": "<p>Build <b>synthetic</b> data pipelines.</p><ul><li>Python</li></ul>",
        "descriptionPlain": "Build synthetic data pipelines.\n- Python",
    }
    return job | changes


def ashby_board(*jobs: Any, **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"apiVersion": "1", "jobs": list(jobs)}
    return body | changes


class FakeSource:
    """An httpx2 transport serving canned responses per URL, recording every request."""

    def __init__(self) -> None:
        self.routes: dict[str, Callable[[httpx2.Request], httpx2.Response]] = {}
        self.requests: list[httpx2.Request] = []

    def json(
        self, url: str, body: Any, *, status: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self.routes[url] = lambda _request: httpx2.Response(
            status,
            content=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **(headers or {})},
        )

    def respond(self, url: str, handler: Callable[[httpx2.Request], httpx2.Response]) -> None:
        self.routes[url] = handler

    def transport(self) -> httpx2.MockTransport:
        def handle(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            handler = self.routes.get(str(request.url))
            return handler(request) if handler else httpx2.Response(404)

        return httpx2.MockTransport(handle)
