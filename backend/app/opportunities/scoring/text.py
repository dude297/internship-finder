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

_LIST_ITEM_SPLIT = re.compile(r"[,;/|\u2022\u00b7*\n]|\s[-\u2013\u2014]\s|\s(?:or|and)\s", re.I)
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
        self._texts = tuple(t for t in texts if t)
        self._skill_ok: dict[str, bool] = {}  # memoised ambiguous-skill checks (linear cost)
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
            return self._ambiguous_skill_ok(phrase[0])
        return self.has_phrase(phrase)

    def _ambiguous_skill_ok(self, word: str) -> bool:
        if word not in self._skill_ok:
            self._skill_ok[word] = any(
                self._has_programming_context(word, p) for p in self._positions.get(word, ())
            ) or self._in_tech_list(word)
        return self._skill_ok[word]

    def _in_tech_list(self, word: str) -> bool:
        """The bare word is one item of a comma/slash/bullet/"or"/"and" list next to a known
        technology ("Tools: R, Tableau, Excel"; "- Go\n- Terraform")."""
        for text in self._texts:
            items = [tokens(item) for item in _LIST_ITEM_SPLIT.split(text)]
            for i, item in enumerate(items):
                if item != (word,):
                    continue
                before = items[i - 1][-1:] if i > 0 else ()
                after = items[i + 1][:1] if i + 1 < len(items) else ()
                if any(t in config.TECH_TOKENS for t in (*before, *after)):
                    return True
        return False

    def _has_programming_context(self, word: str, position: int) -> bool:
        following = self.words[position + 1 : position + 2]
        if following and following[0] in config.AMBIGUOUS_NEXT_BLOCK[word]:
            return False
        before = self.words[max(0, position - config.CONTEXT_WINDOW) : position]
        if len(before) >= 2 and (before[-2], before[-1]) in config.SKILL_LEAD_IN:
            return True  # "experience with Go", "proficiency in C"
        after = self.words[position + 1 : position + config.CONTEXT_WINDOW + 1]
        # The skill's own position is excluded from the window.
        return any(w in config.SKILL_CONTEXT_WORDS for w in (*before, *after))
