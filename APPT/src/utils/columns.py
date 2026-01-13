import re

def normalize(col: str) -> str:
    """
    Normalize Excel column headers:
    - lowercase
    - remove spaces, newlines
    - remove special chars
    """
    col = col.lower()
    col = re.sub(r"\s+", "", col)
    col = re.sub(r"[^a-z0-9]", "", col)
    return col