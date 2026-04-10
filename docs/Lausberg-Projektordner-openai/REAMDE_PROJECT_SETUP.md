# Projektsetup: Lausberg-Analysewerkstatt

## Zweck
Dieses Projekt dient dem systematischen Aufbau eines rhetorischen Wissenskorpus zu Stilfiguren nach Heinrich Lausberg und verwandten rhetorischen Traditionen.

Das Projekt ist nicht primär ein Predigtgenerator, sondern die fachlich saubere Grundlage für:
- Stilfiguren-Archiv
- RAG-System
- Bewertungsagent
- Stilmittelgenerator
- Predigt- und Redeunterstützung
- spätere Automatisierung

## Zentrale Dateien
- `project_systemprompt.md`
- `FIGURE_SCHEMA.json`
- `FIGURE_TEMPLATE.json`
- `WORKFLOW.md`
- `QUALITY_RULES.md`

## Empfohlene Ordnerstruktur

data/
  figures/
  raw_sources/
  reviewed/
prompts/
exports/
notes/

## Empfehlung für einzelne Figuren-Dateien
Pro Stilfigur eine Datei, z. B.:
- `data/figures/anapher.json`
- `data/figures/epipher.json`
- `data/figures/antithese.json`

## Dateiprinzip
Jede Stilfigur soll möglichst:
- eine eigene JSON-Datei haben
- auf demselben Schema beruhen
- spätere Suche und Bewertung unterstützen

## Arbeitsweise
- Immer zuerst eine Stilfigur sauber fertigstellen
- Dann eine eng verwandte Figur zum Vergleich bearbeiten
- Erst danach den Bestand verbreitern

## Leitregel
Lieber 20 Figuren exzellent und systemfähig als 100 Figuren halbunsauber.