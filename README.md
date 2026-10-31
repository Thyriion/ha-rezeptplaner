# Rezeptplaner

Home Assistant Add-on für KI-gestützte Wochenrezeptplanung.

## Features

- Wochenplan per Knopfdruck (Mo–Fr Abendessen, Sa–So Mittag + Abendessen) — **ohne KI**
- Rezepte stammen aus einem lokalen Katalog (Import von hellofresh.de, inkl. Nährwerten)
- Auswahl nach deinen Einstellungen: Ernährungsform, Kochzeit, Abneigungen, Küchengeräte, Bewertungen, Abwechslung
- Rezepte austauschen mit Begründung — getauschte Gerichte kommen nicht so schnell wieder
- Zutaten werden auf die Personenzahl umgerechnet
- Eigene Rezepte fließen mit in die Auswahl ein
- Einkaufsliste nach Kategorien gruppiert, direkt in die HA Shopping List

## Installation

1. In Home Assistant → **Einstellungen → Add-ons → Add-on Store**
2. Drei-Punkte-Menü → **Benutzerdefinierte Repositories**
3. URL eintragen: `https://github.com/Thyriion/ha-rezeptplaner`
4. Add-on **Rezeptplaner** installieren
5. Add-on starten, in den Einstellungen unter **Rezeptkatalog** den Import starten (läuft im Hintergrund, die neuesten Rezepte zuerst; nutzbar, sobald die ersten Rezepte da sind)

## Rezeptquelle

Der Import liest die in der `robots.txt` erlaubten Rezeptseiten von hellofresh.de (schema.org-Daten) langsam (ein Abruf alle ~2 s) und speichert sie lokal auf dem Gerät. Die Rezepte sind nur für den privaten Gebrauch im eigenen Haushalt gedacht — bitte nicht weitergeben oder veröffentlichen und die Nutzungsbedingungen von HelloFresh beachten. Ältere, unvollständige Rezepte werden übersprungen.

Ernährungsformen (vegetarisch/vegan, glutenfrei, laktosefrei) werden anhand der Zutatennamen geschätzt — bei Allergien bitte immer die Zutatenliste prüfen.

## Entwicklung

```bash
cd rezeptplaner/backend
pip install -r requirements.txt
uvicorn main:app --reload
```
