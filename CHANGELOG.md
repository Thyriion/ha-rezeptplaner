# Changelog

## 0.10.2 – 2026-06-29

### Bugfixes
- **Hintergrundbild nur bei Theme mit Bild**: Der Add-on lädt das Hintergrundbild jetzt nur, wenn das aktive HA-Theme eine `--background-image`-Variable definiert. Vorher wurde auch bei anderen Themes fest `/local/galaxy_bg.jpg` geladen.

---

## 0.10.1 – 2026-06-29

### Neue Features
- **Hintergrundbild im Add-on**: Das Galaxy-Hintergrundbild (`/local/galaxy_bg.jpg`) wird aus der HA-Theme-Variable `--background-image` übernommen und als Hintergrund des Rezeptplaner-iFrames angezeigt. Falls das Bild nicht erreichbar ist, fällt der Hintergrund auf `#0d0e14` zurück.

---

## 0.10.0 – 2026-06-29

### Neue Features
- **Galaxy Theme**: Der Rezeptplaner passt sich jetzt dem aktiven Home-Assistant-Theme an. Dazu liest `theme.js` die HA-CSS-Variablen aus `window.parent` und mapped sie auf die internen Design-Tokens.
- **Accent-Farbe**: Die Theme-Accent-Farbe (`#9b7abf`) wird für aktive Tabs, Chips, Option-Buttons und Fokus-Ringe verwendet.

### Architektur
- **ADR-0001**: Entscheidung dokumentiert, warum der Theme-Adapter den Parent-Window-Ansatz nutzt statt eine serverseitige HA-API-Abfrage.

---

## 0.8.1 – 2026-06-24

### Performance
- **USDA-Lookups parallel**: Nährwert-Anfragen pro Rezept und über alle Mahlzeiten eines Plans laufen jetzt gleichzeitig statt nacheinander. Bei einem 9-Mahlzeiten-Plan mit je ~5 Zutaten reduziert sich die Wartezeit von ~45 sequenziellen HTTP-Requests auf einen einzigen parallelen Batch.

---

## 0.8.0 – 2026-06-24

### Architektur-Refactoring
- **PlanStore**: Alle 22 freien DB-Funktionen zu einer injizierbaren Klasse zusammengefasst. `save_new_plan()` und `apply_swap()` als atomare Operationen.
- **NutritionClient**: Injizierbare Klasse ersetzt freie `enrich_nutrition()`-Funktion. Gibt `NutritionInfo | None` zurück statt in-place zu mutieren.
- **PlanService**: User-Rezepte laufen jetzt vollständig durch den Service — kein direkter DB-Zugriff mehr aus `main.py`.
- **`_context()` entfernt**: Jede Service-Methode lädt nur noch die Daten, die sie tatsächlich braucht.
- **state.js aufgeteilt**: Globales `state`-Objekt in vier domain-ausgerichtete Slices aufgeteilt (`planState`, `swapState`, `wizardState`, `recipeState`).
- **Testinfrastruktur**: Erste Backend-Tests mit `MemoryPlanStore` und `FakePlannerAI` (kein KI-API-Aufruf nötig).

---

## 0.4.1 – 2026-06-20

### Bugfixes
- **Tauschen repariert**: Mahlzeiten aus älteren Wochen konnten nicht getauscht werden (Fehler "Mahlzeit nicht gefunden"). Wird jetzt direkt per ID gesucht, unabhängig vom aktuellen Plan.
- **Wochendatum im Navigator**: Alle Pläne zeigten dasselbe Datum. Neue Pläne erhalten jetzt automatisch den nächsten freien Montag nach dem letzten vorhandenen Plan.
- **Bewertungssterne immer sichtbar**: Sterne waren nur nach dem Aufklappen einer Mahlzeit sichtbar. Sie erscheinen jetzt direkt auf der Karte.
- **Abstand Schnellaktionen → Eingabe**: Zu geringer Abstand zwischen den Quick-Action-Buttons und dem Chat-Eingabefeld behoben.

---

## 0.4.0 – 2026-06-20

### Architektur-Refactoring
- **PromptBuilder**: Alle KI-Prompts in eine tiefe Klasse gezogen (`system`, `plan`, `swap`, `chat`, `single_recipe`).
- **PlanService**: Absorbiert alle Domain-Operationen; `main.py` ist jetzt reiner HTTP-Router ohne eigene DB-Aufrufe.
- **HAClient-Adapter**: `SupervisorAdapter` und `NoopAdapter` hinter einer abstrakten Basisklasse — testbar und austauschbar.
- **Frontend ES-Module**: Monolithisches `app.js` (798 Zeilen) aufgeteilt in 7 Module (`state`, `api`, `cooking`, `plan`, `shopping`, `settings`, `chat`) + schlanken Orchestrator.

---

## 0.3.0 – 2026-06-15

### Neue Features
- **Mehrwochen-Planung**: Pläne werden nicht mehr überschrieben. Navigation mit ← → zwischen gespeicherten Wochen. Einzelne Wochen löschbar.
- **Rezept-Bewertungen**: 1–10 Sterne pro Rezeptname. Grundscore 5. Gerichte mit Score < 3 werden nicht mehr vorgeschlagen, Score ≥ 8 werden bevorzugt.
- **Quick-Actions im Chat**: Buttons "Wochenplan generieren" und "Einzelnes Rezept vorschlagen" ohne freie Texteingabe.
- **Einzelrezept-Flow**: KI schlägt ein Rezept im Chat vor, mit "Zum Plan hinzufügen"-Button inkl. Tag- und Mahlzeit-Auswahl.
- **Vielfalt im KI-Prompt**: Mindestens 4 verschiedene Küchenstile, kein wiederholtes Hauptzutat-Protein, Favoriten max. 1× pro Woche. Temperature auf 0,95 erhöht.
- **Groß-/Kleinschreibung bei verzichtbaren Zutaten**: `disliked_foods` werden jetzt case-insensitiv verglichen und dedupliziert.

### Bugfixes
- Einkaufslisten-Zeile vollständig klickbar (nicht nur Checkbox).
- HA Sync (`auth_api: true` in config.yaml ergänzt, Fallback-Endpunkt für neuere HA-Versionen).

---

## 0.2.2 – 2026-06-10

### Refactoring
- Architektur-Vertiefung (4 Kandidaten): Repository-Seam, Service-Schicht, erste Adapter-Strukturen, Frontend-Aufräumarbeiten.

---

## 0.2.1 – 2026-06-10

### Bugfixes
- SyntaxError durch ungültige Anführungszeichen in f-String behoben.

---

## 0.2.0 – 2026-06-08

### Neue Features
- Dark-Theme passend zum HA-Design.
- Kochmodus: Schritt-für-Schritt-Anleitung mit Timer.
- Wochenplan löschen.
- Chat-Bug behoben (Eingabe wurde nicht geleert).

---

## 0.1.0 – 2026-06-05

### Initiales Release
- FastAPI-Backend mit SQLite-Datenbank.
- KI-Rezeptgenerierung (OpenAI-kompatibel, Mistral/Ollama).
- Wochenplan mit Tausch-Funktion.
- Einkaufsliste mit HA-Sync.
- Einstellungs-Wizard (Personen, Ernährung, Vorlieben, Budget, Zeit).
- HA Ingress-Integration.
