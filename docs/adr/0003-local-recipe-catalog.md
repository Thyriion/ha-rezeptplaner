# Local Recipe Catalog Instead of AI Generation

The AI invented recipes (inconsistent quality, USDA lookups for nutrition, API keys and cost, 60 s waits). We replaced generation with a local **RecipeCatalog** imported from hellofresh.de and rule-based **Selection**.

- **Source:** hellofresh.de publishes ~12,500 recipe URLs in its recipe sitemap, which `robots.txt` allows. Each page carries a schema.org `Recipe` with ingredients, steps, time, yield and per-serving nutrition. Recipes before ~2015 are empty and are skipped. Chosen over Chefkoch (no clear terms), TheMealDB (English, small) and paid APIs (Spoonacular, Edamam).
- **Import:** background task, newest first (ObjectId timestamp in the URL), one request every ~2 s, resumable (imported and skipped URLs are remembered). Private household use only; the user is responsible for HelloFresh's terms.
- **Nutrition:** taken from the source, so USDA enrichment, its cache and the long-polling endpoint are gone (supersedes ADR 0002).
- **Diet flags:** derived from ingredient names by keyword matching — best-effort, not allergy-safe. Budget has no source data, so it only down-weights recipes by a rough cost proxy (ingredient count, premium ingredients, fish/meat) — no real prices.
- **No AI:** the OpenAI-compatible client, prompts and add-on options (`ai_*`, `usda_api_key`) were removed. The chat tab now means "plan" → build a week, anything else → keyword search in the catalog.
- **Trade-off:** the add-on depends on the HelloFresh page format; a format change breaks only the import, not the existing catalog.
