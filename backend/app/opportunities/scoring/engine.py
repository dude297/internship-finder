"""Fit scoring (ADR-010 §7, v2 per ADR-019). Pure: no database, network, clock, or randomness."""

from collections.abc import Iterable, Sequence
from datetime import date

from app.enums import RemoteMode, RequirementsAssessmentStatus
from app.opportunities.scoring import config
from app.opportunities.scoring.schemas import (
    ComponentResult,
    FitOpportunityInput,
    FitProfileInput,
    MissingInput,
    NamedItem,
    ScoreBreakdown,
)
from app.opportunities.scoring.text import Corpus, Phrase, tokens


def percent(numerator: int, denominator: int) -> int:
    """round_half_up(100 × numerator / denominator) in integer arithmetic."""
    return (200 * numerator + denominator) // (2 * denominator)


def _mean(values: Sequence[int]) -> int:
    return (2 * sum(values) + len(values)) // (2 * len(values))


def _join(items: Iterable[str]) -> str:
    return ", ".join(items)


def _missing(key: str, missing_input: MissingInput, reason: str) -> ComponentResult:
    return ComponentResult(
        score=0,
        weight=config.WEIGHTS[key],
        missing=True,
        missing_input=missing_input,
        reason=reason,
    )


def _distinct_terms(terms: Iterable[str]) -> list[tuple[str, Phrase]]:
    """Usable terms (at least one word), first spelling kept for duplicates."""
    seen: set[Phrase] = set()
    result: list[tuple[str, Phrase]] = []
    for term in terms:
        phrase = tokens(term)
        if phrase and phrase not in seen:
            seen.add(phrase)
            result.append((term.strip(), phrase))
    return result


def _term_match(
    key: str, noun: str, terms: Sequence[str], corpus: Corpus, *, skill: bool = False
) -> ComponentResult:
    usable = _distinct_terms(terms)
    if not usable:
        return _missing(key, "profile", f"Add {noun} to your Match Profile to score this.")
    found = {term: corpus.match_via(phrase, skill=skill) for term, phrase in usable}
    matched = [term for term, via in found.items() if via]
    unmatched = [term for term, via in found.items() if not via]
    # Evidence for matches that aren't the exact spelling: "alias <posting phrase>" / "related ...".
    evidence = {
        term: f"{via[0]} {' '.join(via[1])}"
        for term, via in found.items()
        if via and via[0] != "exact"
    }
    if matched:
        shown = [f"{t} ({evidence[t]})" if t in evidence else t for t in matched]
        reason = f"Matched {len(matched)} of {len(usable)} {noun}: {_join(shown)}."
    else:
        reason = f"None of your {len(usable)} {noun} appear in this posting."
    return ComponentResult(
        score=percent(len(matched), len(usable)),
        weight=config.WEIGHTS[key],
        reason=reason,
        matched=matched,
        unmatched=unmatched,
        details={"evidence": evidence} if evidence else None,
    )


def technical(profile: FitProfileInput, corpus: Corpus) -> ComponentResult:
    return _term_match("technical", "skills", profile.skills, corpus, skill=True)


def interests(profile: FitProfileInput, corpus: Corpus) -> ComponentResult:
    return _term_match("interests", "interests", profile.interests, corpus)


def _course_words(phrase: Phrase) -> list[str]:
    return [
        word
        for word in phrase
        if word not in config.STOP_WORDS and word not in config.COURSE_FILLER and not word.isdigit()
    ]


def _course_group_term(phrase: Phrase, corpus: Corpus) -> str | None:
    """The posting term that connects a course to the posting through a subject group."""
    name = " ".join(phrase)
    for course_names, posting_terms in config.SUBJECT_GROUPS:
        if name in course_names:
            for term in sorted(posting_terms):
                if corpus.has_phrase(tokens(term)):
                    return term
    return None


def academic(profile: FitProfileInput, corpus: Corpus) -> ComponentResult:
    usable = _distinct_terms(profile.courses)
    if not usable:
        return _missing("academic", "profile", "Add courses to your Match Profile to score this.")
    exact: list[str] = []
    keywords: list[str] = []
    groups: dict[str, str] = {}
    unmatched: list[str] = []
    for course, phrase in usable:
        words = _course_words(phrase)
        if corpus.matches(phrase):
            exact.append(course)
        elif words and all(corpus.matches((word,)) for word in words):
            keywords.append(course)
        elif (group_term := _course_group_term(phrase, corpus)) is not None:
            keywords.append(course)
            groups[course] = group_term
        else:
            unmatched.append(course)
    points = config.COURSE_EXACT_POINTS * len(exact) + config.COURSE_KEYWORD_POINTS * len(keywords)
    parts = [
        *([f"named in the posting: {_join(exact)}"] if exact else []),
        *(
            [f"subject words in the posting: {_join(k for k in keywords if k not in groups)}"]
            if len(keywords) > len(groups)
            else []
        ),
        *(
            [f"course group: {_join(f'{c} (posting says {t})' for c, t in groups.items())}"]
            if groups
            else []
        ),
    ]
    reason = (
        f"{len(exact) + len(keywords)} of {len(usable)} courses relate ({'; '.join(parts)})."
        if parts
        else f"None of your {len(usable)} courses appear related to this posting."
    )
    return ComponentResult(
        score=percent(points, config.COURSE_EXACT_POINTS * len(usable)),
        weight=config.WEIGHTS["academic"],
        reason=reason,
        matched=exact + keywords,
        unmatched=unmatched,
        details={"exact": exact, "keywords": keywords, **({"groups": groups} if groups else {})},
    )


def _item_words(item: NamedItem) -> list[str]:
    words: dict[str, None] = {}
    for word in (*tokens(item.name), *tokens(item.description)):
        if (
            len(word) >= 2
            and not word.isdigit()
            and word not in config.STOP_WORDS
            and word not in config.GENERIC_WORDS
        ):
            words[word] = None
    return list(words)


def projects(profile: FitProfileInput, corpus: Corpus) -> ComponentResult:
    items = [*profile.projects, *profile.research]
    if not items:
        return _missing(
            "projects", "profile", "Add projects or research to your Match Profile to score this."
        )
    ranked = sorted(
        ((item, [word for word in _item_words(item) if corpus.matches((word,))]) for item in items),
        key=lambda pair: -len(pair[1]),  # stable: equal overlaps keep profile order
    )
    shown = [(item, words) for item, words in ranked[: config.PROJECT_ITEMS_SHOWN] if words]
    full = config.PROJECT_KEYWORDS_FOR_FULL_SCORE
    best = min(len(ranked[0][1]), full)
    if shown:
        top, words = shown[0]
        reason = (
            f"Strongest match: {top.name} ({len(words)} shared keyword"
            f"{'' if len(words) == 1 else 's'}: {_join(words[:8])}). "
            f"{full} or more shared keywords earn the full score."
        )
    else:
        reason = f"None of your {len(items)} projects or research items share keywords."
    return ComponentResult(
        score=percent(best, full),
        weight=config.WEIGHTS["projects"],
        reason=reason,
        matched=[item.name for item, _ in shown],
        unmatched=[item.name for item, words in ranked if not words],
        details={"items": [{"name": item.name, "keywords": words} for item, words in shown]},
    )


_MODE_LABELS = {
    RemoteMode.REMOTE: "remote",
    RemoteMode.HYBRID: "hybrid",
    RemoteMode.ONSITE: "on-site",
}


def _remote_in_text(location: str | None) -> bool:
    """Strict: "Remote", or "Remote" plus the US or one US state ("Remote - US", "Remote (CA)")."""
    words = tokens(location)
    if words[:1] != ("remote",):
        return False
    rest = " ".join(words[1:])
    return (
        rest == ""
        or rest in config.REMOTE_US_WORDS
        or rest in config.US_STATE_NAMES
        or rest in config.US_STATE_CODES
    )


def _region_match(place: str, location: str) -> tuple[int, str] | None:
    """(score, explanation) when the preferred place and the posting are in the same region."""
    key = " ".join(tokens(place.split(",")[0]))
    for region, cities in config.REGION_CITIES.items():
        if key not in cities:
            continue
        where = Corpus(location)
        found = [c for c in sorted(cities) if where.has_phrase(tokens(c))]
        covered = {word for city in found for word in tokens(city)}
        # Anything else in the location (another state, a country) means a different place.
        # A 5-digit ZIP (or its +4 part) is not another place.
        extra = [
            w
            for w in tokens(location)
            if w not in covered | config.REGION_ALLOWED_WORDS
            and not (w.isdigit() and len(w) in (4, 5))
        ]
        if found and not extra:
            score = (
                config.LOCATION_MATCH_SCORE
                if key in config.REGION_LABELS
                else config.REGION_CITY_SCORE
            )
            return score, f'Region match: "{location}" is in the {region} region.'
    return None


def _place(
    profile: FitProfileInput, opportunity: FitOpportunityInput
) -> tuple[int | None, list[str]]:
    reasons: list[str] = []
    mode_score: int | None = None
    mode = opportunity.remote_mode
    if mode is None and _remote_in_text(opportunity.location):
        mode = RemoteMode.REMOTE
        reasons.append("Location text says remote, so it is treated as remote work.")
    if profile.remote_preference is not None and mode is not None:
        mode_score = config.WORK_MODE_SCORES[profile.remote_preference][mode]
        preference = profile.remote_preference.value.replace("_", " ")
        reasons.append(
            f"{_MODE_LABELS[mode].capitalize()} work scores {mode_score} for your"
            f" {preference} setting."
        )
    location_score: int | None = None
    if mode is not RemoteMode.REMOTE and profile.preferred_locations and opportunity.location:
        where = Corpus(opportunity.location)
        hits = [
            place
            for place in profile.preferred_locations
            if where.matches(tokens(place.split(",")[0])) or where.matches(tokens(place))
        ]
        location_score = config.LOCATION_MATCH_SCORE if hits else 0
        region_notes: list[str] = []
        if not hits:
            for place in profile.preferred_locations:
                region = _region_match(place, opportunity.location)
                if region:
                    hits.append(place)
                    score, note = region
                    location_score = max(location_score, score)
                    region_notes.append(note)
        reasons.append(
            (f"Location matches {_join(hits)}." + "".join(f" {n}" for n in region_notes))
            if hits
            else f"Location {opportunity.location} isn't one of your preferred locations."
        )
    known = [s for s in (mode_score, location_score) if s is not None]
    return (min(known) if known else None), reasons


def _schedule(
    profile: FitProfileInput, opportunity: FitOpportunityInput
) -> tuple[int | None, list[str]]:
    if profile.availability_start is None and profile.availability_end is None:
        return None, []
    start = opportunity.start_date
    if start is None:
        return None, ["The posting has no start date, so availability can't be compared."]
    first = profile.availability_start or date.min
    last = profile.availability_end or date.max
    end = opportunity.end_date
    if end is None:
        inside = first <= start <= last
        return (
            config.SCHEDULE_PARTIAL_SCORE if inside else 0,
            [
                "It starts within your availability (end date unknown)."
                if inside
                else "It starts outside your availability."
            ],
        )
    if first <= start and end <= last:
        return config.SCHEDULE_INSIDE_SCORE, ["Its dates fall within your availability."]
    if start <= last and end >= first:
        return config.SCHEDULE_PARTIAL_SCORE, ["Its dates partly overlap your availability."]
    return 0, ["Its dates don't overlap your availability."]


def location_schedule(
    profile: FitProfileInput, opportunity: FitOpportunityInput
) -> ComponentResult:
    has_evidence = (
        profile.remote_preference is not None
        or bool(profile.preferred_locations)
        or profile.availability_start is not None
        or profile.availability_end is not None
    )
    if not has_evidence:
        return _missing(
            "location_schedule",
            "profile",
            "Add a work-mode preference, preferred locations, or availability to score this.",
        )
    place, place_reasons = _place(profile, opportunity)
    schedule, schedule_reasons = _schedule(profile, opportunity)
    known = [s for s in (place, schedule) if s is not None]
    if not known:
        return _missing(
            "location_schedule",
            "opportunity",
            " ".join(
                schedule_reasons
                or ["The posting doesn't say enough about work mode, location, or dates."]
            ),
        )
    return ComponentResult(
        score=_mean(known),
        weight=config.WEIGHTS["location_schedule"],
        reason=" ".join(place_reasons + schedule_reasons),
        details={"place": place, "schedule": schedule},
    )


_QUALITY_LABELS = {
    "description": "a detailed description",
    "application_url": "an application link",
    "application_deadline": "a deadline",
    "start_date": "a start date",
    "posted_at": "a posted date",
    "requirements_reviewed": "reviewed requirements",
}


def quality(opportunity: FitOpportunityInput) -> ComponentResult:
    present = {
        "description": len(opportunity.description or "") >= config.MIN_DESCRIPTION_CHARS,
        "application_url": bool(opportunity.application_url),
        "application_deadline": opportunity.application_deadline is not None,
        "start_date": opportunity.start_date is not None,
        "posted_at": opportunity.posted_at is not None,
        "requirements_reviewed": opportunity.requirements_assessment_status
        is not RequirementsAssessmentStatus.UNASSESSED,
    }
    has = [_QUALITY_LABELS[k] for k, ok in present.items() if ok]
    lacks = [_QUALITY_LABELS[k] for k, ok in present.items() if not ok]
    reason = " ".join(
        [
            *([f"Has {_join(has)}."] if has else []),
            *([f"Missing {_join(lacks)}."] if lacks else []),
        ]
    )
    return ComponentResult(
        score=sum(config.QUALITY_POINTS[k] for k, ok in present.items() if ok),
        weight=config.WEIGHTS["quality"],
        reason=reason,
        matched=has,
        unmatched=lacks,
    )


def score_fit(profile: FitProfileInput, opportunity: FitOpportunityInput) -> ScoreBreakdown:
    """The fit score and its explanation. Never reads or affects eligibility (ADR-001)."""
    text = Corpus(opportunity.title, opportunity.description)
    with_org = Corpus(opportunity.title, opportunity.organization, opportunity.description)
    components = {
        "technical": technical(profile, text),
        "academic": academic(profile, text),
        "projects": projects(profile, text),
        "interests": interests(profile, with_org),
        "location_schedule": location_schedule(profile, opportunity),
        "quality": quality(opportunity),
    }
    total = sum(c.score * c.weight for c in components.values())
    return ScoreBreakdown(
        scoring_version=config.SCORING_VERSION,
        score=(total + 50) // 100,
        coverage=sum(c.weight for c in components.values() if not c.missing),
        components=components,
    )
