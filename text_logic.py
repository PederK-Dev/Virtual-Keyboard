"""Pure word-suggestion logic, independent of Tk and Win32 so it can be tested."""


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
