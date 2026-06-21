"""Pure word-suggestion logic, independent of Tk and Win32 so it can be tested."""

import re


# A word is considered "real" (worth learning / suggesting) if it doesn't look
# like keyboard mash. We reject words with excessive repeated characters or
# very long runs of the same letter — e.g. "tttyyyi", "aaaaah", "bbnnmmm".
# Tunable: max consecutive identical letters allowed.
_MAX_REPEAT = 3


def looks_like_word(word):
    """Return True if ``word`` plausibly is a real word, not keyboard mash.

    Checks:
    - At least 2 characters, all alphabetic.
    - No run of the same letter longer than ``_MAX_REPEAT`` (rejects "tttyyyi",
      "bbbbby", etc.). A 4+ run of any letter is almost never a real word.
    - Not too many repeated characters overall (rejects "bbnnmmmuyutt" where
      repeats are frequent even though no single run exceeds the limit).
    - Must contain at least one vowel (a, e, i, o, u, y) — real words almost
      always do; mash like "hgg", "bbnn" doesn't.
    """
    if not word or len(word) < 2 or not word.isalpha():
        return False
    lower = word.lower()
    # Reject long runs of the same letter: "tttyyyi" has "yyy" (ok) but
    # "aaaaah" has "aaaa" (rejected). We allow up to _MAX_REPEAT in a row.
    if re.search(r"(.)\1{" + str(_MAX_REPEAT) + r",}", lower):
        return False
    # Reject words with too many repeated characters. For short words (<=6)
    # more than half is junk; for longer words a third is already suspicious.
    repeats = sum(1 for i in range(1, len(word)) if word[i] == word[i - 1])
    threshold = len(word) / 2 if len(word) <= 6 else len(word) / 3
    if repeats > threshold:
        return False
    # Must contain at least one vowel — catches consonant-only mash like
    # "hgg", "bbnn", "jho" (no vowel). "y" counts as a vowel here.
    if not any(c in "aeiouy" for c in lower):
        return False
    return True


def matching_words(words, current, limit=6):
    """Return up to ``limit`` suggestions for the word being typed.

    With no partial word, returns the first ``limit`` common words. Otherwise
    returns the words that start with ``current`` (case-insensitive). Returns an
    empty list when nothing matches, so callers can decide on a fallback.
    """
    if not current:
        return list(words[:limit])

    lowered = current.lower()
    matches = [word for word in words if word.lower().startswith(lowered)]
    return matches[:limit]


def rank_words(words, frequencies, current, limit=6):
    """Like :func:`matching_words`, but orders results by learned frequency.

    ``frequencies`` maps a lower-cased word to how often it has been used.
    Candidates are the base ``words`` plus any learned words not already in the
    base list; matches are filtered by the ``current`` prefix, de-duplicated,
    then sorted most-used first (ties keep the base order, which is stable).
    """
    lowered = current.lower()
    seen = set()
    candidates = []
    for word in list(words) + [w for w in frequencies if w not in words]:
        lower = word.lower()
        if lower in seen:
            continue
        if current and not lower.startswith(lowered):
            continue
        # Skip learned "words" that look like keyboard mash (e.g. "tttyyyi")
        # so junk that slipped into learned_words.json never reaches the bar.
        if not looks_like_word(word):
            continue
        seen.add(lower)
        candidates.append(word)
    candidates.sort(key=lambda w: frequencies.get(w.lower(), 0), reverse=True)
    return candidates[:limit]


def completion(word, current):
    """Return the text to type to turn ``current`` into ``word``.

    If ``word`` continues ``current`` (the normal suggestion case), only the
    remaining suffix is returned. Otherwise the whole ``word`` is returned.
    """
    if current and word.lower().startswith(current.lower()):
        return word[len(current):]
    return word
