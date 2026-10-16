"""Hides secrets that ride in a URL's query string before the text is stored or shown."""

import re

SECRET_PARAM = re.compile(r"(?i)((?:api_)?key=)[^&\s']+")


def redact(text: str) -> str:
    return SECRET_PARAM.sub(r"\1***", text)
