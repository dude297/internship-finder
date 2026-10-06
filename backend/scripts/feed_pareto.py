"""Read-only feed-dependence Pareto: which open community-feed listings are NOT covered by a
direct source. One GET to the public feed; no database, no secrets.

    python scripts/feed_pareto.py [TOP_N]

ENABLED is the production enabled set approximated from docs/operations.md and
docs/releases/2026-10-06-m9-m11.md (45 boards); update it when activations change.
"""

import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

FEED = (  # same URL as FEEDS in app/ingestion/adapters/community_feed.py
    "https://zshah101.github.io/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships"
    "/api/jobs.json"
)

CATALOG = Path(__file__).resolve().parents[1] / "data" / "direct_source_catalog.json"
SUPPORTED = {"greenhouse", "lever", "ashby", "smartrecruiters", "workable", "pinpoint"}
ENABLED = {
    "rocketlab",
    "flyzipline",
    "astranis",
    "vardaspace",
    "neuralink",
    "formlabs",
    "palantir",
    "impulsespace",
    "etched",
    "saronic",
    "skydio",
    "togetherai",
    "quantinuum",
    "helion",
    "psiquantum",
    "figureai",
    "kodiak",
    "pinterest",
    "stripe",
    "waymo",
    "lyft",
    "coinbase",
    "akunacapital",
    "morsecorpcoop",
    "verkada",
    "hpiq",
    "robinhood",
    "devtechnology",
    "dvtrading",
    "advancedspace",
    "singlestore",
    "thenuclearcompany",
    "hermeus",
    "kitware",
    "ramp",
    "bedrock-robotics",
    "allen-control-systems",
    "base-power",
    "reflect-orbital",
    "abbvie",
    "boschgroup",
    "eurofins",
    "keenfinity",
    "llnl",
    "wellmarkinc",
}


def norm(name: str) -> str:
    name = re.sub(r"\b(inc|llc|corp|corporation|ltd)\b", "", name.lower())
    return re.sub(r"[^a-z0-9]+", "", name)


def board(job: dict[str, Any]) -> tuple[str, str]:
    """(provider, board identifier) from the feed id, which names the ATS board."""
    kind, _, rest = str(job["id"]).partition(":")
    if kind in SUPPORTED or kind in ("workday", "oracle"):
        return kind, rest.split(":")[0].lower()
    return kind, urlsplit(str(job.get("url") or "")).hostname or "?"


def main() -> None:
    top = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    req = urllib.request.Request(FEED, headers={"User-Agent": "feed-pareto"})
    jobs = json.load(urllib.request.urlopen(req, timeout=60))["jobs"]
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))["sources"]
    cat_boards = {c["identifier"].lower() for c in cat}
    cat_names = {norm(c["organization"]) for c in cat}
    status: Counter[str] = Counter()
    prov: Counter[str] = Counter()
    green: Counter[str] = Counter()
    orgs: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for j in jobs:
        kind, b = board(j)
        if kind in SUPPORTED and b in ENABLED:
            status["DIRECT ACTIVE"] += 1
        elif (kind in SUPPORTED and b in cat_boards) or norm(j["company"]) in cat_names:
            status["DIRECT AVAILABLE (catalog, not enabled)"] += 1
            prov[f"{kind} (in catalog)"] += 1
            orgs[j["company"]][f"{kind}:{b}"] += 1
        else:
            if kind in SUPPORTED:
                status["SUPPORTED, NOT CONFIGURED"] += 1
                green[f"{kind}:{b}"] += 1
                prov[f"{kind} (unconfigured)"] += 1
            else:
                status["UNSUPPORTED PROVIDER"] += 1
                prov[kind] += 1
            orgs[j["company"]][f"{kind}:{b}"] += 1
    n = len(jobs)
    print(f"Feed listings: {n}\n\n| Status | Listings | % |\n|---|---|---|")
    for k, v in status.most_common():
        print(f"| {k} | {v} | {v / n:.1%} |")
    print("\n| Provider (not DIRECT ACTIVE) | Listings |\n|---|---|")
    for k, v in prov.most_common():
        print(f"| {k} | {v} |")
    print("\n| # | Organization | Listings | Provider:board |\n|---|---|---|---|")
    ranked = sorted(orgs.items(), key=lambda kv: -sum(kv[1].values()))[:top]
    for i, (o, c) in enumerate(ranked, 1):
        print(f"| {i} | {o} | {sum(c.values())} | {c.most_common(1)[0][0]} |")
    print("\n| Supported-but-unconfigured board | Listings |\n|---|---|")
    for k, v in green.most_common():
        print(f"| {k} | {v} |")


if __name__ == "__main__":
    main()
