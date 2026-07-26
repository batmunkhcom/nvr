"""LPR Pattern Library — country-specific license plate regex patterns.

To add a new country:
    1. Add an entry to LPR_PATTERNS.
    2. Provide at least one regex pattern.
    3. The plugin will match OCR output against all patterns for the selected country.
"""

from __future__ import annotations

LPR_PATTERNS: dict[str, dict] = {
    "mongolia": {
        "code": "MN",
        "name": "Монгол Улс",
        "patterns": [
            r"[А-ЯЁ]{3}\s?\d{4}",
            r"\d{4}\s?[А-ЯЁ]{3}",
        ],
    },
    "europe": {
        "code": "EU",
        "name": "Европ (EU)",
        "patterns": [
            r"[A-Z]{2,3}\s?\d{2,4}\s?[A-Z]{0,3}",
            r"[A-Z]{3}\s?\d{4}",
        ],
    },
    "usa": {
        "code": "US",
        "name": "АНУ",
        "patterns": [
            r"[A-Z]{1,3}[-\s]?\d{4,7}",
        ],
    },
    "japan": {
        "code": "JP",
        "name": "Япон",
        "patterns": [
            r"[^\s\d]+\s?\d{1,4}\s?[^\s\d]+\s?\d{1,4}",
        ],
    },
    "china": {
        "code": "CN",
        "name": "Хятад",
        "patterns": [
            r"[А-ЯЁ]{1,2}[A-Z]\s?[·]?\d{5}",
        ],
    },
    "russia": {
        "code": "RU",
        "name": "Орос",
        "patterns": [
            r"[А-ЯЁ]{1,3}\d{3,4}[А-ЯЁ]{2,3}\s?\d{2,3}",
        ],
    },
    "south_korea": {
        "code": "KR",
        "name": "Өмнөд Солонгос",
        "patterns": [
            r"[^\s\d]+\s?\d{1,2}[^\s\d]\s?\d{4}",
        ],
    },
    "custom": {
        "code": "XX",
        "name": "Custom Regex",
        "patterns": None,
    },
}

DEFAULT_PATTERN = "mongolia"
