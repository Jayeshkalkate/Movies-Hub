import re


def clean_caption(text):
    if not text:
        return ""

    text = re.sub(r"JOIN.*", "", text, flags=re.I)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"t\.me/\S+", "", text)

    return text.strip()


def extract_title(text):
    if not text:
        return ""

    first_line = text.split("\n")[0]

    first_line = re.sub(
        r"S\d+.*",
        "",
        first_line,
        flags=re.I
    )

    return first_line.strip()


def extract_season(text):
    match = re.search(r"S(\d+)", text, re.I)

    if match:
        return int(match.group(1))

    return None


def extract_quality(text):

    for q in [
        "2160p",
        "1440p",
        "1080p",
        "720p",
        "480p"
    ]:

        if q.lower() in text.lower():
            return q

    return "Unknown"


def extract_language(text):

    lower = text.lower()

    if "dual audio" in lower:
        return "Dual Audio"

    if "hindi" in lower:
        return "Hindi"

    if "english" in lower:
        return "English"

    return ""