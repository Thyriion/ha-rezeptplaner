# Rezeptplaner

Home Assistant Add-on für KI-gestützte Wochenrezeptplanung.

## Features

- Wochenplan per Chat generieren (Mo–Fr Abendessen, Sa–So Mittag + Abendessen)
- Rezepte austauschen mit Begründung — das System lernt deine Präferenzen
- Einkaufsliste nach Kategorien gruppiert, direkt in die HA Shopping List
- Konfigurierbar mit jedem OpenAI-kompatiblen KI-Provider (Mistral, Claude, Ollama, ...)

## Installation

1. In Home Assistant → **Einstellungen → Add-ons → Add-on Store**
2. Drei-Punkte-Menü → **Benutzerdefinierte Repositories**
3. URL eintragen: `https://github.com/Thyriion/ha-rezeptplaner`
4. Add-on **Rezeptplaner** installieren
5. In der Add-on-Konfiguration API-Key und Modell eintragen

## Konfiguration

| Option | Beschreibung | Beispiel |
|---|---|---|
| `ai_base_url` | API Endpoint des KI-Providers | `https://api.mistral.ai/v1` |
| `ai_model` | Modellname | `mistral-small-latest` |
| `ai_api_key` | API Key | `sk-...` |

### Empfohlene Provider

- **Mistral AI** (kostenloser Free Tier, EU): `https://api.mistral.ai/v1`
- **Anthropic Claude**: `https://api.anthropic.com/v1`
- **Ollama** (lokal): `http://localhost:11434/v1`

## Entwicklung

```bash
cd rezeptplaner/backend
pip install -r requirements.txt
uvicorn main:app --reload
```
