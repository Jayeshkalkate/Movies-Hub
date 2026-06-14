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

    title = text.split("\n")[0]

    patterns = [
        r"\b2160p\b",
        r"\b1080p\b",
        r"\b720p\b",
        r"\b480p\b",
        r"\bWEB[- ]DL\b",
        r"\bBluRay\b",
        r"\bHDRip\b",
        r"\bHindi\b",
        r"\bEnglish\b",
        r"\bDual Audio\b",
        r"\b\d{4}\b",
    ]

    for pattern in patterns:
        title = re.sub(
            pattern,
            "",
            title,
            flags=re.I
        )
        
        title = title.replace(".", " ")
        
        title = re.sub(
            r"\b(x264|x265|AAC|HEVC)\b",
            "",
            title,
            flags=re.I,
        )
        
        title = re.sub(
            r"\s+",
            " ",
            title,
        )

    return title.strip()


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