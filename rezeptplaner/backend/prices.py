"""Rough price-per-serving estimate from the ingredient list.

Prices are approximate German supermarket prices (EUR per kg/l) and are meant for
*ranking* recipes against each other, not for exact cost. Adjust the table to taste.
"""
import re

from .models import Recipe

_VEGAN_PRODUCT_RE = re.compile(r"vegan|veggie|pflanzlich|planted|plant-based")

# (pattern, EUR per kg or l, grams per piece). First match wins, so specific entries come first.
# Bump when the table changes: the store then recomputes all catalog prices on startup.
PRICE_VERSION = 2

# Buying full packs means real spend exceeds the exact recipe amounts.
_PACKAGING_FACTOR = 1.25

_FREE_RE = re.compile(r"^(leitungs|heißes |kaltes |warmes )?wasser\b|eiswürfel")
_ORGANIC_RE = re.compile(r"\bbio\b|weide")
_ORGANIC_FACTOR = 1.3

_PRICES: list[tuple[re.Pattern, float, int]] = [(re.compile(p), eur, piece) for p, eur, piece in [
    # Specific beef mince first, then generic
    (r"(rind|weiderind).*hack|hack.*(rind|weiderind)", 17, 125),
    # Konserven / Basics that contain other ingredient words
    (r"tomatenmark", 8, 20), (r"passiert|gehackte tomaten|dosentomaten|stückige tomaten", 2.5, 400),
    (r"kokosmilch", 4, 400), (r"kichererbsen|kidneybohnen|weiße bohnen|dosen", 3, 240),
    (r"linsen", 4, 250), (r"mais", 3.5, 285),
    (r"brühe|brühpulver|bouillon|fond\b|brühwürfel", 12, 15), (r"sojasoße|sojasauce|soja soße|teriyaki", 8, 15),
    (r"miso", 20, 25), (r"gochujang|sambal|harissa|ketjap|worcester|chimichurri|ajvar|salsa", 9, 100),
    (r"pesto", 15, 190), (r"sauce|soße", 6, 100), (r"senf", 6, 15), (r"ketchup", 4, 20),
    (r"mayo", 5, 20), (r"honig|sirup|ahorn", 12, 20), (r"nussmus|tahini|erdnussbutter", 15, 15),
    (r"oliven", 9, 10), (r"kapern", 25, 10), (r"rosinen|sultanin|datteln|feigen|aprikose", 8, 20), (r"kokosraspel|kokosflocken", 10, 20),
    (r"cashew|pinienkern|pistazie", 22, 30), (r"mandel|walnuss|haselnuss|erdnuss|nüsse|sesam|kürbiskern|sonnenblumenkern", 12, 30),
    (r"hello |gewürzmischung|gewürz|za'?atar|ras el|garam|curry|paprikapulver|kreuzkümmel|kurkuma|zimt|muskat|"
     r"oregano|chiliflocken|cayenne|vanille|lorbeer|knoblauchpulver|zwiebelpulver|rauchpaprika|kumin|kümmel", 80, 3), (r"paste", 15, 20),
    (r"salz", 0.8, 5), (r"pfeffer", 60, 2), (r"zucker", 1.2, 5), (r"essig|balsamico", 4, 15),
    (r"olivenöl", 9, 15), (r"öl\b", 6, 15), (r"speisestärke|backpulver", 4, 10),
    # Fisch
    (r"räucherlachs|graved", 32, 100), (r"lachs", 26, 150), (r"thunfisch", 20, 150), (r"garnele|scampi|shrimp", 26, 100),
    (r"forelle", 16, 200), (r"kabeljau|seelachs|dorade|zander|barsch", 20, 150), (r"pangasius", 10, 150),
    (r"muschel|tintenfisch|krabbe", 14, 100), (r"fisch", 18, 150),
    # Fleisch
    (r"hähnchen|hühn|huhn", 9, 180), (r"pute|truthahn", 10, 180), (r"rinderfilet|steak", 30, 200),
    (r"rind", 14, 200), (r"hack", 9, 125), (r"schweinefilet", 11, 200), (r"schwein", 8, 200),
    (r"bacon|speck", 14, 20), (r"schinken|serrano|prosciutto", 18, 20), (r"salami|chorizo", 18, 10),
    (r"wurst|würstchen|bratwurst", 12, 80), (r"lamm", 26, 200), (r"kalb", 22, 200), (r"\bente\b|enten", 22, 250),
    (r"gyros|döner|frikadelle|nuggets|schnitzel|geschnetzel|pulled", 11, 150),
    # Milchprodukte / Eier
    (r"parmesan|grana|pecorino", 25, 10), (r"burrata", 14, 125), (r"halloumi", 12, 125),
    (r"mozzarella", 8, 125), (r"feta|hirtenkäse|schafskäse|ziegenkäse", 10, 100),
    (r"mascarpone|ricotta", 7, 125), (r"frischkäse|frischecreme", 6, 100), (r"camembert|brie|paneer", 12, 125),
    (r"käse|gouda|emmentaler|cheddar", 10, 30), (r"crème fraîche|creme fraiche", 5, 100),
    (r"schmand|saure sahne", 3.5, 100), (r"sahne", 4, 100), (r"joghurt|skyr|quark", 2.5, 150),
    (r"butter", 9, 10), (r"milch", 1.2, 100), (r"\bei\b|\beier\b|eigelb|eiweiß", 6, 60),
    # Getreide
    (r"udon|soba|glasnudeln|reisnudeln|ramen|somen", 6, 100),
    (r"nudel|penne|spaghetti|fusilli|tagliatelle|rigatoni|farfalle|conchiglie|orecchiette|pasta|lasagne|tortellini|ravioli", 3, 100), (r"gnocchi", 4, 100), (r"reis\b", 3, 100),
    (r"couscous|bulgur|polenta|haferflocken", 3.5, 100), (r"quinoa", 8, 100), (r"mehl", 1.2, 100),
    (r"chips|pommes", 6, 100), (r"tortilla|wrap|naan|pita|fladenbrot|burger-?brötchen|\bbun|brötchen|baguette|ciabatta|brot\b|toast", 6, 60),
    (r"teig|knödel|spätzle|panko|semmelbrösel|croissant|brioche", 5, 100),
    # Gemüse / Obst / Kräuter
    (r"süßkartoffel", 3.5, 300), (r"kartoffel", 1.6, 100), (r"zwiebel|schalotte", 1.8, 80),
    (r"knoblauch", 10, 5), (r"ingwer", 10, 20), (r"chili|peperoni|jalapeño", 15, 15),
    (r"kirschtomate|cherrytomate|datteltomate", 8, 15), (r"tomate", 3.5, 100),
    (r"paprika", 4.5, 180), (r"karotte|möhre", 1.4, 80), (r"zucchini", 3, 250), (r"gurke", 2.5, 400),
    (r"aubergine", 4, 300), (r"brokkoli", 3.5, 300), (r"blumenkohl", 3, 500), (r"babyspinat|spinat", 8, 100),
    (r"rucola|feldsalat", 15, 100), (r"salat|romana|eisberg", 6, 200), (r"champignon|pilz|shiitake|pfifferling|seitling", 8, 125),
    (r"petersilie|basilikum|koriander|dill|schnittlauch|minze|kräuter", 25, 30),
    (r"lauch|porree", 3, 200), (r"kürbis", 2.5, 800), (r"erbsen|bohnen", 4, 150), (r"avocado", 8, 150),
    (r"zitrone|limette", 4, 100), (r"frühlingszwiebel", 8, 30), (r"rosmarin|thymian|salbei", 25, 5), (r"apfel|birne", 3, 180), (r"orange|mandarine", 2.5, 180),
    (r"mango|ananas|granatapfel|pfirsich", 5, 250), (r"banane", 2, 120), (r"beere|traube", 9, 125),
    (r"rote bete|rübe|sellerie|kohlrabi|fenchel", 3, 250), (r"spargel", 9, 100), (r"pak choi|mangold|romanesco|stir fry", 5, 300), (r"kohl", 2.5, 400), (r"radieschen", 4, 20), (r"nektarine", 4, 150),
]]

_DEFAULT = (6.0, 80)  # EUR/kg, grams per piece for unknown ingredients

# grams per unit for non-weight units (pieces use the per-ingredient piece weight)
_UNIT_GRAMS = {
    "g": 1, "kg": 1000, "ml": 1, "l": 1000, "TL": 5, "EL": 15, "Prise": 0.5, "Bund": 30, "Dose": 400,
    "Packung": 250, "Päckchen": 100, "Becher": 150, "Scheibe": 20, "Zehe": 5, "Handvoll": 30,
    "Zweig": 3, "Glas": 200, "Flasche": 500,
}


def _price_of(name: str) -> tuple[float, int]:
    lowered = name.lower()
    if _VEGAN_PRODUCT_RE.search(lowered):
        return 12.0, 125
    for pattern, eur_per_kg, piece in _PRICES:
        if pattern.search(lowered):
            return eur_per_kg, piece
    return _DEFAULT


def estimate_price_per_serving(recipe: Recipe) -> float:
    """Approximate ingredient cost in EUR per serving (pantry items 'nach Geschmack' count as 0)."""
    total = 0.0
    for ing in recipe.ingredients:
        if not ing.amount or _FREE_RE.search(ing.name.lower()):
            continue
        eur_per_kg, piece = _price_of(ing.name)
        grams = ing.amount * _UNIT_GRAMS.get(ing.unit, piece)
        cost = grams / 1000 * eur_per_kg
        total += cost * (_ORGANIC_FACTOR if _ORGANIC_RE.search(ing.name.lower()) else 1.0)
    return round(total * _PACKAGING_FACTOR / max(recipe.servings, 1), 2)
