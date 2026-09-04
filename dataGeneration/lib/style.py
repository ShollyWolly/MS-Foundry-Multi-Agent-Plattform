"""Number formatting helpers shared by every report generator.

These format *display strings* for the PDF only — the underlying numeric values are kept
unformatted in the ground-truth sidecar (see render.py / generate_reports.py), so a RAG answer
can be checked against real numbers, not the formatted text.
"""


def fmt_currency(value, symbol: str = "$") -> str:
    v = float(value)
    if v < 0:
        return f"({symbol}{abs(v):,.0f})"
    return f"{symbol}{v:,.0f}"


def fmt_thousands(value) -> str:
    return f"{float(value):,.0f}"


def fmt_percent(value, decimals: int = 1, signed: bool = False) -> str:
    v = float(value)
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v:.{decimals}f}%"
