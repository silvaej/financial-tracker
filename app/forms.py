def parse_optional_id(raw: str) -> int | None:
    """An HTML <select> "no selection" option submits as an empty string, not
    an absent field -- see CLAUDE.md's "Optional FK form fields" note. Parse
    it into the int | None an optional FK actually needs."""
    return int(raw) if raw else None
