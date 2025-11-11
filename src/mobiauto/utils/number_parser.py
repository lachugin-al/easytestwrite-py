from __future__ import annotations

import re


class NumberParser:
    """
    Extracts the first numeric value from an arbitrary string and converts it to a float.

    Suitable for prices or amounts containing non-breaking/thin spaces, currency symbols,
    apostrophes (') / typographic quotes (’), and mixed thousand/decimal separators (',' or '.').

    Heuristic rules:
    - Normalizes special spaces into regular spaces.
    - Extracts the first numeric token (with an optional sign), ignoring trailing currency symbols.
    - If both comma and dot are present, the rightmost one is treated as the decimal separator.
    - If only one of {',' '.'} is present, and the last group after it has length 3
      while the preceding groups also have length 3 — the separator is treated as a thousands
      separator and removed; otherwise it is treated as a decimal separator.
    - Spaces and apostrophes are always treated as thousands separators and removed.
    """

    # Special spaces: NBSP, NNBSP, Thin Space, Narrow No-Break Space, etc.
    _SPACE_RX = re.compile(r"[\u00A0\u2007\u202F\u2009\u200A\u2008\u2002\u2003\u2004\u2005\u2006]")
    # Allowed characters inside a numeric token
    _NUM_CHARS = set("0123456789.,'’ +-")

    @staticmethod
    def _normalize_spaces(s: str) -> str:
        s = NumberParser._SPACE_RX.sub(" ", s)
        # Collapse multiple spaces
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    @staticmethod
    def _extract_candidate(s: str) -> str | None:
        """Extract the first numeric fragment (including an optional sign)."""
        # Remove approximate symbols (~, ≈, etc.)
        s = s.replace("≈", " ")
        s = NumberParser._normalize_spaces(s)
        # Match: optional sign, then digit followed by allowed characters
        m = re.search(r"[+\-]?\s*\d[0-9\s.,'’]*", s)
        if not m:
            return None
        cand = m.group(0)
        # Trim potential trailing noise (we already filtered allowed chars)
        return cand.strip()

    @staticmethod
    def extract_first_number(s: str) -> float | None:
        s = str(s)
        cand = NumberParser._extract_candidate(s)
        if not cand:
            return None

        # Extract and apply sign
        sign = 1.0
        cand = cand.strip()
        if cand.startswith("+"):
            cand = cand[1:].lstrip()
        elif cand.startswith("-"):
            cand = cand[1:].lstrip()
            sign = -1.0

        # Remove explicit thousands separators: spaces and apostrophes
        cand = cand.replace(" ", "").replace("'", "").replace("’", "")

        # If only digits remain — simple integer case
        if re.fullmatch(r"\d+", cand):
            try:
                return sign * float(int(cand))
            except Exception:
                return None

        # Determine role of comma/dot
        last_dot = cand.rfind(".")
        last_comma = cand.rfind(",")

        def _as_float(body: str, dec: str | None) -> float | None:
            try:
                if dec is None:
                    # Integer part only
                    return sign * float(int(body))
                # Remove opposite separator used for thousands
                if dec == ".":
                    body = body.replace(",", "")
                else:
                    body = body.replace(".", "")
                # Convert decimal separator to dot
                body = body.replace(dec, ".")
                return sign * float(body)
            except Exception:
                return None

        if last_dot != -1 and last_comma != -1:
            # Decimal separator is the rightmost one
            dec = "." if last_dot > last_comma else ","
            return _as_float(cand, dec)

        # Only one separator present
        if last_dot != -1 or last_comma != -1:
            sep = "." if last_dot != -1 else ","
            parts = cand.split(sep)
            # Example patterns ['12','345','678'] or ['2','000'] → likely thousands separators
            if len(parts) >= 2:
                last_len = len(parts[-1])
                has_middle = len(parts) > 2
                middle_all_three = all(len(p) == 3 for p in parts[1:-1]) if has_middle else False
                leading = parts[0]
                if last_len == 3 and (
                    (has_middle and middle_all_three)
                    or any(len(p) == 3 for p in parts[1:-1])
                    or (len(parts) == 2 and leading.isdigit() and 1 <= len(leading) <= 3)
                ):
                    # Treat as thousands separator: remove it
                    joined = "".join(parts)
                    return _as_float(joined, None)
                # Otherwise treat as decimal separator
                return _as_float(cand, sep)

        # No dots or commas left — check if only digits remain
        if re.fullmatch(r"\d+", cand):
            try:
                return sign * float(int(cand))
            except Exception:
                return None

        # Could not parse according to heuristic
        return None


__all__ = ["NumberParser"]
