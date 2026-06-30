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