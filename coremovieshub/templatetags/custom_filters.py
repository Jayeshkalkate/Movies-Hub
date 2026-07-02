from django import template

register = template.Library()


@register.filter
def format_duration(minutes):
    """
    Convert minutes to a human-readable duration string.
    Example: 125 -> "2h 5m", 45 -> "45m", None -> "—"
    """
    if not minutes:
        return "—"

    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return "—"

    if minutes <= 0:
        return "—"

    hours = minutes // 60
    mins = minutes % 60

    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


@register.filter
def format_currency(value, symbol="$"):
    """
    Format a number as currency with the given symbol.
    Example: 1234567 -> "$1,234,567"
    """
    if value is None:
        return "—"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    # Format as integer with thousands separators (no decimals)
    return f"{symbol}{value:,.0f}"


@register.filter
def compact_number(value):
    """
    Convert large numbers to a compact human-readable format (K/M/B).
    Examples:
        1500 -> "1.5K"
        2_500_000 -> "2.5M"
        3_200_000_000 -> "3.2B"
        -12345 -> "-12.3K"
    """
    if value is None:
        return "—"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"

    sign = "-" if value < 0 else ""
    abs_val = abs(value)

    if abs_val >= 1_000_000_000:
        return f"{sign}{abs_val / 1_000_000_000:.1f}B"
    elif abs_val >= 1_000_000:
        return f"{sign}{abs_val / 1_000_000:.1f}M"
    elif abs_val >= 1000:
        return f"{sign}{abs_val / 1000:.1f}K"
    else:
        return f"{sign}{abs_val:.0f}"


@register.filter
def minutes_to_runtime(minutes):
    """
    Convert minutes to a runtime string, identical to format_duration.
    Provided as a separate filter for semantic clarity in templates.
    """
    if not minutes:
        return "—"

    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return "—"

    if minutes <= 0:
        return "—"

    hours = minutes // 60
    mins = minutes % 60

    if hours > 0 and mins > 0:
        return f"{hours}h {mins}m"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{mins}m"
    
