"""PII redaction for logs and traces."""

from __future__ import annotations

import re
from typing import Any

NAME_KEYS = {"holder_name", "holder_name_alt", "beneficiary", "beneficiary_conflict", "name"}
ACCOUNT_RE = re.compile(r"\bACC-[A-Z0-9-]{4,}\b", re.I)
DOB_RE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")


def redact_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in NAME_KEYS or key.endswith("_name"):
        return "[REDACTED]"
    if key in {"dob", "dob_redacted", "date_of_birth"}:
        return "[REDACTED]"
    if isinstance(value, str):
        value = ACCOUNT_RE.sub("[ACCT]", value)
        if key in {"purchase_date"}:
            return value  # purchase dates are not DOB; keep for citations
        value = DOB_RE.sub("[DATE]", value) if "dob" in key.lower() else value
    return value


def redact_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: redact_obj(redact_value(k, v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(x) for x in obj]
    return obj
