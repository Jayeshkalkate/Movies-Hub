from django import template

register = template.Library()


@register.filter
def format_duration(minutes):
    if not minutes:
        return "—"

    try:
        seconds = int(seconds)
        minutes = seconds // 60
    except (TypeError, ValueError):
        return "—"

    hours = minutes // 60
    mins = minutes % 60

    if hours:
        return f"{hours}h {mins}m"

    return f"{mins}m"