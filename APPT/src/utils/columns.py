import re
from typing import Optional


def normalize(col: Optional[str], preserve_underscores: bool = True) -> str:
    """
    Normalizes Excel column headers for consistent database mapping.

    Args:
        col: The raw column header string.
        preserve_underscores: If True, keeps underscores (standard for SQL).
                             If False, removes all special characters.

    Returns:
        A sanitized, lowercase string.
    """
    if col is None or not isinstance(col, str):
        return ""

    # 1. Lowercase and strip outer whitespace
    col = col.lower().strip()

    # 2. Replace internal spaces/hyphens with underscores for SQL friendliness
    col = re.sub(r"[\s\-]+", "_", col)

    # 3. Remove non-alphanumeric characters
    if preserve_underscores:
        # Keep letters, numbers, and underscores
        col = re.sub(r"[^a-z0-9_]", "", col)
    else:
        # Strict alphanumeric only
        col = re.sub(r"[^a-z0-9]", "", col)

    # 4. Clean up any resulting double underscores
    col = re.sub(r"_+", "_", col).strip("_")

    return col