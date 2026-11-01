"""Parsing and classification of recipes for the local recipe catalog.

Pure functions only — no I/O. The importer feeds raw HTML in, the store
persists the resulting CatalogEntry.
"""
import html
import json
import re

from pydantic import BaseModel

from .devices import PREDEFINED_KITCHEN_DEVICES
from .models import Ingredient, NutritionInfo, Recipe
from .prices import estimate_price_per_serving

_LD_JSON_RE = re.compile(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_ISO_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

_UNICODE_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}

_UNITS = {
    "g": "g", "kg": "kg", "ml": "ml", "l": "l",
    "stück": "Stück", "stk": "Stück", "stk.": "Stück",
    "teelöffel": "TL", "tl": "TL",
    "esslöffel": "EL", "el": "EL",
    "prise": "Prise", "prisen": "Prise",
    "bund": "Bund", "dose": "Dose", "dosen": "Dose",
    "packung": "Packung", "päckchen": "Päckchen", "becher": "Becher",
    "scheibe": "Scheibe", "scheiben": "Scheibe",
    "zehe": "Zehe", "zehen": "Zehe",
    "handvoll": "Handvoll", "zweig": "Zweig", "zweige": "Zweig",
    "glas": "Glas", "flasche": "Flasche",
}

_TO_TASTE_RE = re.compile(r"^(nach geschmack|nach bedarf|etwas|eine prise)\s+(.+)$", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"^(\d+(?:[.,]\d+)?|[½¼¾⅓⅔])(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?\s+(.+)$")

# Category keywords, checked in order — first match wins.
_CATEGORY_RULES: list[tuple[str, re.Pattern]] = [
    ("Gewürze & Öle", re.compile(
        r"salz|pfeffer|öl\b|essig|gewürz|paprikapulver|zimt|curry|oregano|thymian\b.*getrocknet|kümmel|kurkuma|"
        r"muskat|cayenne|chiliflocken|zucker|vanille|backpulver|speisestärke|hello |zatar|za'atar|ras el|"
        r"koriander gemahlen|kreuzkümmel|garam|lorbeer|paprika edelsüß|rauchpaprika|knoblauchpulver|zwiebelpulver")),
    ("Konserven & Trockenwaren", re.compile(
        r"tomatenmark|passiert|gehackte tomaten|kokosmilch|kichererbsen|bohnen|linsen|mais\b|brühe|bouillon|fond\b|"
        r"sojasoße|sojasauce|soja soße|senf|honig|ketchup|mayonnaise|nüsse|mandeln|cashew|erdnuss|sesam|"
        r"rosinen|oliven|kapern|pesto|sauce|soße|marmelade|nussmus|tahini|sirup|essiggurke|gurkenscheiben|"
        r"cornichon|dose")),
    ("Fleisch & Fisch", re.compile(
        r"hähnchen|hühn|huhn|pute|truthahn|rind|schwein|hack|bacon|speck|schinken|wurst|würstchen|salami|chorizo|"
        r"lamm|kalb|steak|schnitzel|gulasch|geschnetzel|\bente\b|nuggets|pulled|mett|leber|lachs|fisch|thunfisch|"
        r"garnele|shrimp|scampi|forelle|kabeljau|hering|sardine|anchov|muschel|tintenfisch|krabbe|pangasius|"
        r"dorade|zander|barsch|filet|gyros|döner|frikadelle|bratwurst")),
    ("Milchprodukte & Eier", re.compile(
        r"milch|sahne|käse|joghurt|butter|quark|schmand|crème|creme fraîche|frischkäse|mozzarella|feta|parmesan|"
        r"burrata|halloumi|mascarpone|ricotta|gouda|emmentaler|cheddar|skyr|\bei\b|\beier\b|eigelb|eiweiß|"
        r"grana|pecorino|ziegenkäse")),
    ("Getreide & Backwaren", re.compile(
        r"nudel|penne|spaghetti|fusilli|tagliatelle|rigatoni|farfalle|pasta|reis\b|brot\b|brötchen|mehl|couscous|"
        r"bulgur|tortilla|wrap|gnocchi|\bbun|buns|fladenbrot|baguette|ciabatta|toast|haferflocken|panko|"
        r"semmelbrösel|polenta|quinoa|teig|naan|pita|knödel|spätzle|lasagne|udon|soba|ramen|burger-?brötchen|"
        r"croissant|brioche")),
    ("Gemüse & Obst", re.compile(
        r"zwiebel|knoblauch|tomate|paprika|karotte|möhre|spinat|salat|gurke|zucchini|pilz|champignon|kartoffel|lauch|"
        r"brokkoli|blumenkohl|apfel|zitrone|limette|orange|petersilie|basilikum|koriander|ingwer|avocado|chili|"
        r"aubergine|kürbis|süßkartoffel|mango|frühlingszwiebel|schalotte|kohl|rübe|sellerie|fenchel|spargel|"
        r"erbsen|bohne|mais|radieschen|rucola|kräuter|schnittlauch|dill|minze|birne|banane|beere|traube|"
        r"pfirsich|ananas|granatapfel|rosmarin|thymian|salbei|bärlauch|kohlrabi|mangold|pak choi|romana")),
]

_MEAT_RE = re.compile(
    r"hähnchen|hühn|huhn|pute|truthahn|rind|schwein|hack|bacon|speck|schinken|wurst|würstchen|salami|chorizo|"
    r"lamm|kalb|steak|schnitzel|gulasch|geschnetzel|\bente\b|nuggets|pulled|mett|leber|gyros|döner|frikadelle"
)
_FISH_RE = re.compile(
    r"lachs|fisch|thunfisch|garnele|shrimp|scampi|forelle|kabeljau|hering|sardine|anchov|muschel|tintenfisch|"
    r"krabbe|pangasius|dorade|zander|barsch"
)
_ANIMAL_RE = re.compile(
    r"milch|sahne|käse|joghurt|butter|quark|schmand|crème|creme fraîche|frischkäse|mozzarella|feta|parmesan|"
    r"burrata|halloumi|mascarpone|ricotta|skyr|\bei\b|\beier\b|eigelb|eiweiß|honig|grana|pecorino|kräuterbutter|"
    r"gouda|emmentaler|cheddar"
)
# Meat/fish substitutes ("veganes Hack") must not count as animal products.
VEGAN_PRODUCT_RE = re.compile(r"vegan|veggie|pflanzlich|planted|plant-based")
_PLANT_MILK_RE = re.compile(r"(kokos|hafer|soja|mandel)(milch|sahne|joghurt|drink)|pflanzlich\w*|vegan\w*")
_LACTOSE_RE = re.compile(
    r"milch|sahne|käse|joghurt|butter|quark|schmand|crème|creme fraîche|frischkäse|mozzarella|feta|parmesan|"
    r"burrata|halloumi|mascarpone|ricotta|skyr|grana|pecorino|gouda|emmentaler|cheddar"
)
_SPICY_RE = re.compile(r"chili|chilli|sriracha|gochujang|harissa|sambal|jalapeño|jalapeno|cayenne|peperoni|wasabi|cajun|scharf")
_GLUTEN_RE = re.compile(
    r"nudel|penne|spaghetti|fusilli|tagliatelle|rigatoni|farfalle|pasta|brot\b|brötchen|mehl|couscous|bulgur|tortilla|"
    r"wrap|gnocchi|\bbun|buns|fladenbrot|baguette|ciabatta|toast|panko|semmelbrösel|teig|naan|pita|knödel|spätzle|"
    r"lasagne|udon|ramen|weizen|gerste|roggen|seitan|croissant|brioche|haferflocken"
)

_DEVICE_PATTERNS = {
    "Airfryer": re.compile(r"airfryer|heißluftfritteuse", re.IGNORECASE),
    "Dampfgarer": re.compile(r"dampfgar", re.IGNORECASE),
    "Slow Cooker": re.compile(r"slow cooker|schongarer", re.IGNORECASE),
    "Thermomix": re.compile(r"thermomix", re.IGNORECASE),
    "Multikocher": re.compile(r"multikocher|instant pot", re.IGNORECASE),
    "Kontaktgrill": re.compile(r"kontaktgrill", re.IGNORECASE),
    "Grillplatte": re.compile(r"grillplatte", re.IGNORECASE),
    "Reiskocher": re.compile(r"reiskocher", re.IGNORECASE),
}


class CatalogEntry(BaseModel):
    source_url: str
    recipe: Recipe
    protein_type: str  # "fleisch" | "fisch" | "vegetarisch"
    is_vegetarian: bool
    is_vegan: bool
    is_spicy: bool
    ingredients_text: str


def categorize(ingredient_name: str) -> str:
    lowered = ingredient_name.lower()
    for category, pattern in _CATEGORY_RULES:
        if pattern.search(lowered):
            return category
    return "Sonstiges"


def ingredients_text(recipe: Recipe) -> str:
    return " | ".join(i.name.lower() for i in recipe.ingredients)


def has_gluten(text: str) -> bool:
    return bool(_GLUTEN_RE.search(text))


def has_lactose(text: str) -> bool:
    return bool(_LACTOSE_RE.search(_PLANT_MILK_RE.sub("", text)))


_TERM_GROUPS: dict[str, re.Pattern] = {
    "fleisch": _MEAT_RE,
    "fisch": _FISH_RE,
    "geflügel": re.compile(r"hähnchen|hühn|huhn|pute|truthahn|\bente\b"),
    "meeresfrucht": re.compile(r"garnele|shrimp|scampi|muschel|tintenfisch|krabbe"),
    "pilz": re.compile(r"pilz|champignon|shiitake|pfifferling|steinpilz|austernpilz|shimeji|kräuterseitling|portobello"),
    "nuss": re.compile(r"nuss|nüsse|mandel|cashew|pistazie|erdnuss|pinienkern"),
    "käse": re.compile(r"käse|mozzarella|feta|parmesan|halloumi|burrata|gouda|emmentaler|cheddar|ricotta|mascarpone|grana|pecorino"),
    "milchprodukt": _LACTOSE_RE,
    "ei": re.compile(r"\bei\b|\beier\b|eigelb|eiweiß"),
    "scharf": _SPICY_RE,
    "innerei": re.compile(r"leber|niere|herz\b"),
    "hülsenfrucht": re.compile(r"bohne|linse|kichererbse|erbse"),
}


def _term_key(term: str) -> str:
    """Lower-case a user term and strip a German plural ending ("Pilze" -> "pilz")."""
    t = term.strip().lower()
    if t.endswith("en") and len(t) > 5:
        return t[:-2]
    if t.endswith(("e", "n")) and len(t) > 4:
        return t[:-1]
    return t


def matches_term(term: str, haystack: str) -> bool:
    """True if a user-entered food term (or its category, e.g. "Fleisch") occurs in `haystack`."""
    key = _term_key(term)
    if not key:
        return False
    group = _TERM_GROUPS.get(key) or _TERM_GROUPS.get(term.strip().lower())
    if group:
        return bool(group.search(haystack))
    return key in haystack


def classify(recipe: Recipe) -> dict:
    """Derive diet/protein flags from the ingredient list (best-effort keyword matching)."""
    text = " | ".join(i.name.lower() for i in recipe.ingredients if not VEGAN_PRODUCT_RE.search(i.name.lower()))
    has_meat = bool(_MEAT_RE.search(text))
    has_fish = bool(_FISH_RE.search(text))
    animal = bool(_ANIMAL_RE.search(_PLANT_MILK_RE.sub("", text)))
    vegetarian = not (has_meat or has_fish)
    return {
        "protein_type": "fleisch" if has_meat else "fisch" if has_fish else "vegetarisch",
        "is_vegetarian": vegetarian,
        "is_vegan": vegetarian and not animal,
        "is_spicy": bool(_SPICY_RE.search(text)),
    }


def detect_devices(text: str) -> list[str]:
    return [d for d in PREDEFINED_KITCHEN_DEVICES if d in _DEVICE_PATTERNS and _DEVICE_PATTERNS[d].search(text)]


def _to_float(token: str) -> float:
    if token in _UNICODE_FRACTIONS:
        return _UNICODE_FRACTIONS[token]
    return float(token.replace(",", "."))


def parse_ingredient(line: str) -> Ingredient | None:
    line = html.unescape(line).strip()
    if not line:
        return None
    taste = _TO_TASTE_RE.match(line)
    if taste:
        name = taste.group(2).strip()
        return Ingredient(name=name, amount=0, unit="nach Geschmack", category=categorize(name))
    m = _AMOUNT_RE.match(line)
    if not m:
        return Ingredient(name=line, amount=0, unit="nach Geschmack", category=categorize(line))
    amount = _to_float(m.group(1))
    rest = m.group(2).strip()
    first, _, tail = rest.partition(" ")
    unit = _UNITS.get(first.lower())
    if unit and tail:
        name, unit_out = tail.strip(), unit
    else:
        name, unit_out = rest, ""
    return Ingredient(name=name, amount=amount, unit=unit_out, category=categorize(name))


def _parse_minutes(value) -> int | None:
    if not isinstance(value, str):
        return None
    m = _ISO_DURATION_RE.fullmatch(value.strip())
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def _parse_number(value) -> float | None:
    if value is None:
        return None
    m = _NUMBER_RE.search(str(value))
    return float(m.group(0).replace(",", ".")) if m else None


def _clean_step(text: str) -> str:
    text = re.sub(r"</p>\s*<p>", " ", text)
    text = html.unescape(_TAG_RE.sub("", text)).replace("\xa0", " ").replace("*", "")
    return re.sub(r"\s+", " ", text).strip()


def _image_url(node: dict) -> str | None:
    image = node.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    # Old recipes only carry the CDN prefix without a file name.
    if isinstance(image, str) and image.startswith("https://") and not image.endswith("/"):
        return image
    return None


def _find_recipe_node(page_html: str) -> dict | None:
    for match in _LD_JSON_RE.finditer(page_html):
        try:
            data = json.loads(match.group(1))
        except ValueError:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes if isinstance(nodes, list) else [nodes]:
            if isinstance(node, dict) and "Recipe" in str(node.get("@type")):
                return node
    return None


def parse_recipe_page(page_html: str, source_url: str) -> CatalogEntry | None:
    """Turn a recipe page into a CatalogEntry, or None when the data is incomplete."""
    node = _find_recipe_node(page_html)
    if not node or not node.get("name"):
        return None

    ingredients = [i for i in (parse_ingredient(str(x)) for x in node.get("recipeIngredient") or []) if i]
    steps = []
    for step in node.get("recipeInstructions") or []:
        text = step.get("text") if isinstance(step, dict) else step
        cleaned = _clean_step(str(text or ""))
        if cleaned:
            steps.append(cleaned)

    nutrition = node.get("nutrition") or {}
    calories = _parse_number(nutrition.get("calories"))
    servings = int(_parse_number(node.get("recipeYield")) or 0)
    if len(ingredients) < 3 or not steps or calories is None or servings < 1:
        return None

    minutes = _parse_minutes(node.get("totalTime")) or _parse_minutes(node.get("prepTime")) or 30
    recipe = Recipe(
        name=html.unescape(str(node["name"])).strip(),
        cooking_time_minutes=minutes,
        servings=servings,
        ingredients=ingredients,
        steps=steps,
        nutrition_per_serving=NutritionInfo(
            calories=round(calories),
            protein_g=_parse_number(nutrition.get("proteinContent")) or 0.0,
            carbs_g=_parse_number(nutrition.get("carbohydrateContent")) or 0.0,
            fat_g=_parse_number(nutrition.get("fatContent")) or 0.0,
        ),
        suggested_devices=detect_devices(" ".join(steps) + " " + str(node["name"])),
        source_url=source_url,
        image_url=_image_url(node),
    )
    recipe.price_per_serving = estimate_price_per_serving(recipe)
    return CatalogEntry(
        source_url=source_url,
        recipe=recipe,
        ingredients_text=ingredients_text(recipe),
        **classify(recipe),
    )


def scale_recipe(recipe: Recipe, persons: int) -> Recipe:
    """Return a copy of the recipe with ingredient amounts scaled to `persons` servings."""
    if persons == recipe.servings or recipe.servings < 1:
        return recipe
    factor = persons / recipe.servings
    scaled = []
    for ing in recipe.ingredients:
        amount = ing.amount * factor
        if amount:
            step = 0.5 if ing.unit in ("Stück", "Zehe", "Scheibe", "Bund", "Dose", "Packung", "Päckchen", "") else 0.1
            amount = max(step, round(amount / step) * step)
            amount = round(amount, 1)
        scaled.append(ing.model_copy(update={"amount": amount}))
    return recipe.model_copy(update={"ingredients": scaled, "servings": persons})
