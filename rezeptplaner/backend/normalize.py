import re
import unicodedata


def normalize_recipe_name(name: str) -> str:
    """Return a canonical form of a recipe name for matching.

    Rules:
    - lower case
    - umlauts and eszett are expanded (ä -> ae, ö -> oe, ü -> ue, ß -> ss)
    - spaces, hyphens and all other non-alphanumeric characters are removed
    """
    name = name.lower().strip()
    name = (
        name.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    # Decompose any remaining accented characters and drop combining marks.
    name = "".join(
        c for c in unicodedata.normalize("NFKD", name)
        if not unicodedata.combining(c)
    )
    # Keep only letters and digits, then join them.
    return "".join(re.findall(r"[a-z0-9]+", name))
