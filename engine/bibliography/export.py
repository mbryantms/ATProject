"""
Bibliography export: CSL-JSON, BibTeX, and RIS.

These are the three formats every reference manager can import. CSL-JSON is
the native format (already stored on each Source); BibTeX and RIS are
generated from the same structured fields, which keeps the converters small
and deterministic — no citeproc round-trip involved.
"""

import json

# CSL type -> BibTeX entry type
_BIBTEX_TYPES = {
    "article": "article",
    "article-journal": "article",
    "article-magazine": "article",
    "article-newspaper": "article",
    "book": "book",
    "chapter": "incollection",
    "paper-conference": "inproceedings",
    "thesis": "phdthesis",
    "report": "techreport",
    "manuscript": "unpublished",
    "software": "misc",
    "webpage": "misc",
    "post-weblog": "misc",
    "dataset": "misc",
}

# CSL type -> RIS TY code
_RIS_TYPES = {
    "article": "JOUR",
    "article-journal": "JOUR",
    "article-magazine": "MGZN",
    "article-newspaper": "NEWS",
    "book": "BOOK",
    "chapter": "CHAP",
    "paper-conference": "CONF",
    "thesis": "THES",
    "report": "RPRT",
    "manuscript": "UNPB",
    "software": "COMP",
    "webpage": "ELEC",
    "post-weblog": "BLOG",
    "dataset": "DATA",
    "motion_picture": "VIDEO",
    "interview": "INTV",
    "map": "MAP",
    "song": "SOUND",
    "legal_case": "CASE",
    "legislation": "STAT",
    "patent": "PAT",
}

EXPORT_FORMATS = {
    "bib": ("application/x-bibtex", "bib"),
    "ris": ("application/x-research-info-systems", "ris"),
    "json": ("application/vnd.citationstyles.csl+json", "json"),
}


def export_sources(sources, fmt: str) -> str:
    """Serialize sources in the requested format ("bib", "ris", or "json")."""
    if fmt == "bib":
        return to_bibtex(sources)
    if fmt == "ris":
        return to_ris(sources)
    if fmt == "json":
        return to_csl_json(sources)
    raise ValueError(f"Unknown export format: {fmt}")


def to_csl_json(sources) -> str:
    """Native CSL-JSON: a JSON array of each source's stored csl_json."""
    return json.dumps([s.csl_json for s in sources], indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# BibTeX
# ---------------------------------------------------------------------------

_BIBTEX_SPECIALS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
}


def _bib_escape(value: str) -> str:
    for char, replacement in _BIBTEX_SPECIALS.items():
        value = value.replace(char, replacement)
    return value


def _bib_names(people: list[dict]) -> str:
    parts = []
    for person in people:
        if "family" in person:
            given = person.get("given", "")
            parts.append(f"{person['family']}, {given}" if given else person["family"])
        elif person.get("literal"):
            parts.append("{" + person["literal"] + "}")
    return " and ".join(parts)


def to_bibtex(sources) -> str:
    """Render sources as a BibTeX bibliography."""
    entries = []
    for source in sources:
        entry_type = _BIBTEX_TYPES.get(source.source_type, "misc")
        fields = {}

        if source.authors:
            fields["author"] = _bib_names(source.authors)
        if source.editors:
            fields["editor"] = _bib_names(source.editors)
        # Braces preserve capitalization through style-mangling importers
        fields["title"] = "{" + _bib_escape(source.title) + "}"
        if source.container_title:
            container_field = "journal" if entry_type == "article" else "booktitle"
            fields[container_field] = _bib_escape(source.container_title)
        if source.year:
            fields["year"] = source.year
        if source.volume:
            fields["volume"] = source.volume
        if source.issue:
            fields["number"] = source.issue
        if source.page:
            fields["pages"] = source.page.replace("-", "--")
        if source.publisher:
            fields["publisher"] = _bib_escape(source.publisher)
        if source.publisher_place:
            fields["address"] = _bib_escape(source.publisher_place)
        if source.edition:
            fields["edition"] = source.edition
        if source.doi:
            fields["doi"] = source.doi
        if source.isbn:
            fields["isbn"] = source.isbn
        if source.issn:
            fields["issn"] = source.issn
        if source.url:
            fields["url"] = source.url

        lines = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields.items())
        entries.append(f"@{entry_type}{{{source.citation_key},\n{lines}\n}}")
    return "\n\n".join(entries) + "\n"


# ---------------------------------------------------------------------------
# RIS
# ---------------------------------------------------------------------------


def to_ris(sources) -> str:
    """Render sources as an RIS bibliography."""
    records = []
    for source in sources:
        lines = [f"TY  - {_RIS_TYPES.get(source.source_type, 'GEN')}"]
        lines.append(f"ID  - {source.citation_key}")
        lines.append(f"TI  - {source.title}")
        for person in source.authors or []:
            if "family" in person:
                given = person.get("given", "")
                name = f"{person['family']}, {given}" if given else person["family"]
            else:
                name = person.get("literal", "")
            if name:
                lines.append(f"AU  - {name}")
        if source.container_title:
            lines.append(f"T2  - {source.container_title}")
        if source.year:
            lines.append(f"PY  - {source.year}")
        if source.volume:
            lines.append(f"VL  - {source.volume}")
        if source.issue:
            lines.append(f"IS  - {source.issue}")
        if source.page:
            start, _, end = source.page.partition("-")
            if start.strip():
                lines.append(f"SP  - {start.strip()}")
            if end.strip():
                lines.append(f"EP  - {end.strip()}")
        if source.publisher:
            lines.append(f"PB  - {source.publisher}")
        if source.publisher_place:
            lines.append(f"CY  - {source.publisher_place}")
        if source.isbn or source.issn:
            lines.append(f"SN  - {source.isbn or source.issn}")
        if source.doi:
            lines.append(f"DO  - {source.doi}")
        if source.url:
            lines.append(f"UR  - {source.url}")
        if source.abstract:
            lines.append(f"AB  - {source.abstract}")
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "\n\n".join(records) + "\n"
