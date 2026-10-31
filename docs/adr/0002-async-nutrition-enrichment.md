**Status: superseded by [ADR 0003](0003-local-recipe-catalog.md)** — the AI and USDA enrichment were removed.

# Asynchronous USDA Nutrition Enrichment with Long Polling

Recipe generation blocked on a synchronous USDA lookup for every English ingredient name (`name_en`). With ~30–45 HTTP requests per weekly plan and a rate-limited `DEMO_KEY`, users waited 60+ seconds before seeing any recipes.

We decided to return the AI-generated plan immediately and enrich nutrition values asynchronously in the background. The frontend uses long polling (`GET /api/plan/{id}/nutrition`) to update the UI once all meals have USDA-backed nutrition data. A persistent SQLite cache (`usda_cache`) stores lookup results so repeated ingredients never trigger another external request.

This keeps nutrition accuracy (USDA remains the source of truth) while making the perceived generation time roughly the pure AI latency. The trade-off is temporary UI inconsistency: nutrition values may appear after the rest of the recipe.
