"""Deterministic lexical matching (ADR-010 §6): normalization, tokenization, phrase search.

No fuzzy matching, stemming, or embeddings. Meaningful punctuation survives tokenization
(`c++`, `c#`, `.net`, `node.js`); everything else separates words.
"""

import re
import unicodedata
from collections import defaultdict
from functools import cache

from app.opportunities.scoring import config
from app.opportunities.scoring.config import ALIAS_GROUPS

_WORD = r"[^\W_]"
# `.net`-style tokens (a leading dot not preceded by a word character), or a word optionally
# followed by `++`, `#`, or dotted parts (`node.js`, `asp.net`; a trailing period is dropped).
_TOKEN = re.compile(rf"(?<!{_WORD})\.{_WORD}+|{_WORD}+(?:\+\+|#|(?:\.{_WORD}+)+)?")

Phrase = tuple[str, ...]


def tokens(text: str | None) -> Phrase:
    if not text:
        return ()
    return tuple(_TOKEN.findall(unicodedata.normalize("NFKC", text).casefold()))


@cache
def _alias_phrases() -> dict[Phrase, frozenset[Phrase]]:
    variants: dict[Phrase, frozenset[Phrase]] = {}
    for group in ALIAS_GROUPS:
        phrases = frozenset(tokens(term) for term in group)
        for phrase in phrases:
            variants[phrase] = phrases
    return variants


def variants(phrase: Phrase) -> frozenset[Phrase]:
    """The phrase and its configured aliases."""
    return _alias_phrases().get(phrase, frozenset({phrase}))


class Corpus:
    """A posting's text, indexed for contiguous phrase search."""

    def __init__(self, *texts: str | None) -> None:
        self.words: Phrase = tuple(word for text in texts for word in (*tokens(text), ""))
        # "" separates the texts, so a phrase can't span two fields.
        self._positions: dict[str, list[int]] = defaultdict(list)
        for position, word in enumerate(self.words):
            self._positions[word].append(position)

    def has_phrase(self, phrase: Phrase) -> bool:
        if not phrase:
            return False
        size = len(phrase)
        return any(
            self.words[start : start + size] == phrase
            for start in self._positions.get(phrase[0], ())
        )

    def matches(self, phrase: Phrase) -> bool:
        """The phrase or one of its aliases appears contiguously."""
        return any(self.has_phrase(variant) for variant in variants(phrase))

    def match_via(self, phrase: Phrase, *, skill: bool = False) -> tuple[str, Phrase] | None:
        """How the phrase matched, for explanations: ("exact" | "alias" | "related", the posting
        phrase found), or None. With skill=True, ambiguous short skills (Go, C, R, Rust) need
        programming context and machine-learning-style skills also accept related phrases."""
        for variant in sorted(variants(phrase), key=lambda v: v != phrase):
            found = self._has_skill_phrase(variant) if skill else self.has_phrase(variant)
            if found:
                return ("exact" if variant == phrase else "alias", variant)
        if skill:
            for term in sorted(config.RELATED_SKILL_TERMS.get(" ".join(phrase), ())):
                if self.has_phrase(tokens(term)):
                    return "related", tokens(term)
        return None

    def _has_skill_phrase(self, phrase: Phrase) -> bool:
        if len(phrase) == 1 and phrase[0] in config.AMBIGUOUS_SKILLS:
            return any(
                self._has_programming_context(phrase[0], p) for p in self._positions[phrase[0]]
            )
        return self.has_phrase(phrase)

    def _has_programming_context(self, word: str, position: int) -> bool:
        following = self.words[position + 1 : position + 2]
        if following and following[0] in config.AMBIGUOUS_NEXT_BLOCK[word]:
            return False
        window = self.words[
            max(0, position - config.CONTEXT_WINDOW) : position + config.CONTEXT_WINDOW + 1
        ]
        return any(w in config.SKILL_CONTEXT_WORDS for w in window)
