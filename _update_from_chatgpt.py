#!/usr/bin/env python3
"""
Update Stilmittel.json with improvements extracted from chatgpt.md.

Key additions from the ChatGPT conversation:
1. Commoratio.predigtwerkstatt – add full 3-step "Christus lebt" chain (was missing entirely)
2. Subiectio.predigtwerkstatt – add the 4-step Vollkombination build (stufen 6-9)
3. Commutando tractationem.predigtwerkstatt – add intermediate +Anapher / +Metapher steps
4. kombinationsregeln.klassische_kombinationen[0] – add detailed stufen to Vollkombination entry
5. Expolitio.kombinationen – add "Expolitio + Interrogatio" and "Expolitio + Periphrase"
6. Ornatus grundlagen predigtwerkstatt – add stufe 5 with Metapher+Anapher+Klimax chain
"""

import json, copy, sys

SRC = "d:/Bilder/Lausberg/Stilmittel.json"

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

def find_stilmittel(name):
    for s in data["stilmittel"]:
        if s["figur_name"] == name:
            return s
    raise KeyError(f"Stilmittel not found: {name}")

def find_grundlage(konzept):
    for g in data["grundlagen"]:
        if g.get("konzept", "") == konzept:
            return g
    raise KeyError(f"Grundlage not found: {konzept}")

# ────────────────────────────────────────────────────────────
# 1. Commoratio – add predigtwerkstatt (completely missing)
# ────────────────────────────────────────────────────────────
commoratio = find_stilmittel("Commoratio")
commoratio["predigtwerkstatt"] = {
    "ausgangssatz": "Christus lebt.",
    "stufen": [
        {
            "stufe": 1,
            "text": "Christus lebt.",
            "mittel": "schlichte Aussage – der Zentralgedanke"
        },
        {
            "stufe": 2,
            "text": (
                "Christus lebt. Darum ist Schuld nicht das Letzte. "
                "Christus lebt. Darum ist Grab nicht das Letzte. "
                "Christus lebt. Darum ist Angst nicht das Letzte."
            ),
            "mittel": "Commoratio + Epimone: der Leitgedanke kehrt dreimal wieder"
        },
        {
            "stufe": 3,
            "text": (
                "Christus lebt. Und wenn Christus lebt, dann ist deine Schuld nicht mehr Richter, "
                "dein Grab nicht mehr Herr und deine Angst nicht mehr König."
            ),
            "mittel": "Commoratio + Antithese + Klimax: dreifache Machtenthronung"
        }
    ]
}
print("✓ Commoratio – predigtwerkstatt added")

# ────────────────────────────────────────────────────────────
# 2. Subiectio – add 4-step Vollkombination as stufen 6–9
# ────────────────────────────────────────────────────────────
subiectio = find_stilmittel("Subiectio")
pw_sub = subiectio["predigtwerkstatt"]
existing_nums = {st["stufe"] for st in pw_sub.get("stufen", [])}

vollkombi_stufen = [
    {
        "stufe": 6,
        "titel": "Vollkombination Stufe 1 – reine Subiectio",
        "text": (
            "Du fragst: Kann Gott mir wirklich vergeben? "
            "Ich antworte: Ja, genau dir."
        ),
        "mittel": "Subiectio allein – Dialog- und Antwortstruktur"
    },
    {
        "stufe": 7,
        "titel": "Vollkombination Stufe 2 – + Klimax",
        "text": (
            "Du fragst: Kann Gott mir wirklich vergeben? "
            "Mir, der ich gelogen habe, der ich gefallen bin, "
            "der ich wieder und wieder zurück in dieselbe Schuld gegangen bin? "
            "Ich antworte: Ja, genau dir."
        ),
        "mittel": "Subiectio + Klimax: Schuldlast wächst stufenweise"
    },
    {
        "stufe": 8,
        "titel": "Vollkombination Stufe 3 – + Anapher",
        "text": (
            "Du fragst: Kann Gott mir wirklich vergeben? "
            "Mir, der ich gefallen bin? Mir, der ich versagt habe? "
            "Mir, der ich bete und doch wieder zweifle, lese und doch wieder vergesse, "
            "verspreche und doch wieder breche? "
            "Ich antworte: Ja, genau dir."
        ),
        "mittel": "Subiectio + Klimax + Anapher: Rhythmus durch Wiederkehr von 'Mir, der ich'"
    },
    {
        "stufe": 9,
        "titel": "Vollkombination Stufe 4 – + Metapher (Höhepunkt)",
        "text": (
            "Du fragst: Kann Gott mir wirklich vergeben? "
            "Mir, der ich gefallen bin? Mir, der ich versagt habe? "
            "Mir, der ich mit schmutzigen Händen, mit müdem Herzen, mit zerrissener Seele "
            "vor ihm stehe? "
            "Ich antworte: Ja, genau dir – "
            "denn Christus sucht nicht die Sauberen, sondern wäscht die Schuldigen."
        ),
        "mittel": (
            "Subiectio + Klimax + Anapher + Metapher: Vollkombination. "
            "Satzteilhäufung (schmutzige Hände / müdes Herz / zerrissene Seele) + "
            "Antithese im Schlusssatz als evangelistischer Landepunkt."
        )
    },
]

for st in vollkombi_stufen:
    if st["stufe"] not in existing_nums:
        pw_sub.setdefault("stufen", []).append(st)
        print(f"  ✓ Subiectio – Vollkombination Stufe {st['stufe']} added")
    else:
        print(f"  – Subiectio Stufe {st['stufe']} already present, skipping")

# ────────────────────────────────────────────────────────────
# 3. Commutando tractationem – add intermediate stufen 2b+2c
#    (currently: 1=schlicht, 2=+Interrogatio, 3=stark, 4=+Subiectio)
#    Insert between current stufe 2 and 3: +Anapher, +Metapher
# ────────────────────────────────────────────────────────────
ct = find_stilmittel("Commutando tractationem")
pw_ct = ct["predigtwerkstatt"]
ct_stufen = pw_ct.get("stufen", [])

# We insert new stufen as 2b / 2c (using float stufe numbers)
new_ct_stufen = [
    {
        "stufe": "2b",
        "titel": "Mit Interrogatio + Anapher",
        "text": (
            "Wie lange noch fern? "
            "Wie lange noch stolz? "
            "Wie lange noch leer? "
            "Ich muss zurück."
        ),
        "mittel": "Tractando + Interrogatio + Anapher: dreifacher Anaphern-Aufschlag"
    },
    {
        "stufe": "2c",
        "titel": "Mit Interrogatio + Anapher + Metapher",
        "text": (
            "Wie lange noch fern? "
            "Wie lange noch stolz? "
            "Wie lange noch leer? "
            "Wie lange will ich noch draußen im Kalten sitzen, "
            "wenn das Vaterhaus längst offen steht? "
            "Ich muss zurück."
        ),
        "mittel": (
            "Tractando + Interrogatio + Anapher + Metapher: "
            "das Bild 'draußen im Kalten / Vaterhaus offen' bricht das Pathos auf"
        )
    },
]

existing_ct_nums = {st.get("stufe") for st in ct_stufen}
added_ct = False
for s in new_ct_stufen:
    if s["stufe"] not in existing_ct_nums:
        # Insert after stufe 2, before stufe 3
        insert_pos = 2
        for i, st in enumerate(ct_stufen):
            if st.get("stufe") == 2:
                insert_pos = i + 1
                break
        ct_stufen.insert(insert_pos, s)
        print(f"  ✓ Commutando tractationem – Stufe {s['stufe']} inserted")
        added_ct = True
    else:
        print(f"  – Commutando tractationem Stufe {s['stufe']} already present")

if added_ct:
    pw_ct["stufen"] = ct_stufen

# ────────────────────────────────────────────────────────────
# 4. kombinationsregeln.klassische_kombinationen[0]
#    Add detailed stufen to the Subiectio+Klimax+Anapher+Metapher entry
# ────────────────────────────────────────────────────────────
kr = data["kombinationsregeln"]
kk = kr["klassische_kombinationen"]
vollkombi_entry = next(
    (k for k in kk if "Subiectio" in k.get("name", "") and "Metapher" in k.get("name", "")),
    None
)
if vollkombi_entry and "stufen" not in vollkombi_entry:
    vollkombi_entry["stufen"] = [
        {
            "stufe": 1,
            "figuren": "Subiectio",
            "text": (
                "Du fragst: Kann Gott mir wirklich vergeben? "
                "Ich antworte: Ja, genau dir."
            )
        },
        {
            "stufe": 2,
            "figuren": "Subiectio + Klimax",
            "text": (
                "Du fragst: Kann Gott mir wirklich vergeben? "
                "Mir, der ich gelogen habe, der ich gefallen bin, "
                "der ich wieder und wieder zurück in dieselbe Schuld gegangen bin? "
                "Ich antworte: Ja, genau dir."
            )
        },
        {
            "stufe": 3,
            "figuren": "Subiectio + Klimax + Anapher",
            "text": (
                "Du fragst: Kann Gott mir wirklich vergeben? "
                "Mir, der ich gefallen bin? Mir, der ich versagt habe? "
                "Mir, der ich bete und doch wieder zweifle, lese und doch wieder vergesse, "
                "verspreche und doch wieder breche? "
                "Ich antworte: Ja, genau dir."
            )
        },
        {
            "stufe": 4,
            "figuren": "Subiectio + Klimax + Anapher + Metapher (Vollkombination)",
            "text": (
                "Du fragst: Kann Gott mir wirklich vergeben? "
                "Mir, der ich gefallen bin? Mir, der ich versagt habe? "
                "Mir, der ich mit schmutzigen Händen, mit müdem Herzen, mit zerrissener Seele "
                "vor ihm stehe? "
                "Ich antworte: Ja, genau dir – "
                "denn Christus sucht nicht die Sauberen, sondern wäscht die Schuldigen."
            )
        },
    ]
    vollkombi_entry["warnung"] = (
        "Nur einsetzen wenn: Satzlänge hörbar bleibt; Steigerung klar erkennbar ist; "
        "das Bild nicht kitschig wird; am Ende eine klare evangelistische Landung kommt."
    )
    print("✓ kombinationsregeln Vollkombination – stufen added")
elif vollkombi_entry:
    print("– kombinationsregeln Vollkombination – stufen already present, skipping")
else:
    print("⚠ kombinationsregeln Vollkombination entry not found!")

# ────────────────────────────────────────────────────────────
# 5. Expolitio.kombinationen – add missing entries
# ────────────────────────────────────────────────────────────
expolitio = find_stilmittel("Expolitio")
existing_kombis = {k.get("kombi", "") for k in expolitio["kombinationen"]}

new_expolitio_kombis = [
    {
        "kombi": "Expolitio + Interrogatio",
        "beispiel": (
            "Wie sollte Christus gerade dich nicht meinen, "
            "wenn er doch für Sünder gekommen ist?"
        ),
        "wirkung": "Die fragende Dringlichkeit treibt die Expolitio voran"
    },
    {
        "kombi": "Expolitio + Periphrase",
        "beispiel": (
            "'Gott vergibt' → "
            "'Gott nimmt die Last von den Schultern' → "
            "'Gott bricht das Siegel der Vergangenheit'"
        ),
        "wirkung": "Periphrase entfaltet den Gedanken durch immer reichere Umschreibungen"
    },
]

for k in new_expolitio_kombis:
    if k["kombi"] not in existing_kombis:
        expolitio["kombinationen"].append(k)
        print(f"  ✓ Expolitio – kombinationen '{k['kombi']}' added")
    else:
        print(f"  – Expolitio '{k['kombi']}' already present")

# ────────────────────────────────────────────────────────────
# 6. Ornatus grundlagen – add stufe 5 (Ornatus from Metapher+Anapher+Klimax)
# ────────────────────────────────────────────────────────────
ornatus = find_grundlage("Ornatus – Rhetorischer Schmuck")
pw_orn = ornatus.get("predigtwerkstatt", {})
orn_stufen = pw_orn.get("stufen", [])
existing_orn = {st.get("stufe") for st in orn_stufen}

if 5 not in existing_orn:
    orn_stufen.append({
        "stufe": 5,
        "text": (
            "Er nimmt die Last von deinen Schultern. "
            "Er nimmt die Scham von deinem Gesicht. "
            "Er nimmt die Nacht aus deinem Herzen. "
            "Er stellt dich wieder ins Licht."
        ),
        "mittel": (
            "Ornatus höchster Stufe: Metapher + Anapher + Klimax. "
            "Nicht mehr nur schön, sondern mitreißend (movere)."
        )
    })
    pw_orn["stufen"] = orn_stufen
    ornatus["predigtwerkstatt"] = pw_orn
    print("✓ Ornatus grundlagen – Stufe 5 added")
else:
    print("– Ornatus Stufe 5 already present")

# ────────────────────────────────────────────────────────────
# 7. Add new grundlagen entry: ars – natura, ars, exercitatio
#    (from Lausberg Kapitel I, §§ 1–5)
# ────────────────────────────────────────────────────────────
existing_grundlagen_konzepte = {g.get("konzept", "") for g in data["grundlagen"]}
ars_konzept = "Rednerbildung: natura – ars – exercitatio"

if ars_konzept not in existing_grundlagen_konzepte:
    data["grundlagen"].append({
        "konzept": ars_konzept,
        "lausberg_paragraphen": "§§ 1–8",
        "definition": (
            "Jede Kunst (τέχνη / ars) setzt die natürliche Anlage (φύσις / natura) voraus "
            "und wird durch Übung (ἐξάσκησις / exercitatio) zur Meisterschaft. "
            "Die Kunst selbst entsteht nicht aus dem Nichts, sondern durch den Dreischritt: "
            "ἀπειρία (Unerfahrenheit) → τύχη (Zufall) → ἐμπειρία (Erfahrung) → τέχνη (Kunst)."
        ),
        "fremdsprachige_originale": [
            {
                "sprache": "Griechisch",
                "original": "φύσις – τύχη – τέχνη",
                "uebersetzung_woertlich": "Natur – Zufall – Kunst",
                "uebersetzung_idiomatisch": "Natürliche Anlage, zufälliger Erfolg, planvoll eingesetzte Kunst",
                "funktion": "Grundtrias des Kunstbegriffs bei Lausberg"
            },
            {
                "sprache": "Griechisch",
                "original": "ἀπειρία → τύχη → ἐμπειρία → τέχνη",
                "uebersetzung_woertlich": "Unerfahrenheit → Zufall → Erfahrung → Kunst",
                "uebersetzung_idiomatisch": (
                    "Erst ist der Mensch unerfahren; durch Zufall entdeckt er Wirkungsweisen; "
                    "durch Wiederholung entsteht Erfahrung; durch Reflexion dieser Erfahrung entsteht Kunst."
                ),
                "funktion": "Entstehungsgeschichte der ars (Lausberg § 2)"
            },
            {
                "sprache": "Latein",
                "original": "industriam vero scientia consequitur; ex scientia copia et facultas ingenii nascitur",
                "uebersetzung_woertlich": "Auf Fleiß folgt Erkenntnis; aus Erkenntnis entstehen Fülle und Fähigkeit",
                "uebersetzung_idiomatisch": (
                    "Wer tätig und fleißig ist, gewinnt Wissen; "
                    "aus Wissen entsteht die Fähigkeit, souverän und reich über eine Sache zu verfügen."
                ),
                "funktion": "Cicero-Formel für die Kette von Arbeit zu wirksamer Rede"
            }
        ],
        "erklaerung_einfach": (
            "Gute Rhetorik entsteht aus drei Faktoren: "
            "(1) natura – die gegebene Begabung des Redners; "
            "(2) ars – das systematisch erlernte Regelwissen, das aus reflektierter Erfahrung abstrahiert wird; "
            "(3) exercitatio – die Übung, durch die Wissen zur zweiten Natur wird. "
            "Lausberg betont: Talent allein reicht nicht; Theorie allein reicht nicht; "
            "nur aus dem Zusammenspiel aller drei entsteht Meisterschaft."
        ),
        "dreischritt_entstehung": {
            "apeiria": "Unerfahrenheit – der Anfänger redet drauflos ohne System",
            "tyche": "Zufall – eine Predigt trifft, ohne dass man weiß warum",
            "empeiria": "Erfahrung – Muster werden erkannt und wiederholbar gemacht",
            "techne": (
                "Kunst – die abstrahierte, systematisch-lehrhafte Formulierung der Erfahrung. "
                "Erst hier entstehen Kategorien (Kasus), übertragbare Regeln und Schubladen."
            )
        },
        "predigtanwendung": [
            "Nur ars ohne natura klingt trocken und gemacht",
            "Nur natura ohne ars bleibt unstrukturiert und zufällig wirkungsvoll",
            "Nur exercitatio ohne ars macht Gewohnheiten, aber keine Entwicklung",
            "Das Ziel: Anlage + System + Übung = wirkungsvolle, evangelistische Predigt"
        ],
        "predigtwerkstatt": {
            "ausgangssatz": "Gott liebt dich.",
            "stufen": [
                {
                    "stufe": 1,
                    "text": "Gott liebt dich.",
                    "mittel": "nur natura: richtig, aber wirkungslos"
                },
                {
                    "stufe": 2,
                    "text": (
                        "Gott liebt dich – nicht die Version von dir, die du gerne wärst, "
                        "sondern dich, genau jetzt."
                    ),
                    "mittel": "natura + ars: rhetorisch geformte Wahrheit mit konkreter Zuspitzung"
                },
                {
                    "stufe": 3,
                    "text": (
                        "Du fragst: Kann Gott mich lieben, nach allem? "
                        "Mir, der ich mich selbst kaum noch annehmen kann? "
                        "Ja – denn Gott liebt nicht wer du sein könntest, sondern wer du bist."
                    ),
                    "mittel": "natura + ars + exercitatio: Subiectio + Klimax + Antithese = Meisterschaft"
                }
            ]
        },
        "combinationen": [
            {
                "kombi": "natura + Interrogatio",
                "beispiel": "Kennst du dieses Gefühl, dass Gott sich abgewandt hat?",
                "wirkung": "Authentizität durch echte Frage"
            },
            {
                "kombi": "ars + Klimax",
                "beispiel": "Du zweifelst. Du kämpfst. Du zerbrichst. Und dort beginnt Gott.",
                "wirkung": "Gezielte Steigerung durch Struktur"
            },
            {
                "kombi": "exercitatio + Subiectio",
                "beispiel": "Du sagst: Ich kann nicht mehr. Ich sage dir: Du kannst – weil Gott kann.",
                "wirkung": "Souveräne Hörerfüh­rung durch Übung"
            }
        ],
        "tags": ["grundlagen", "rednerbildung", "ars", "techne", "natura", "exercitatio", "lausberg_kapitel_1"]
    })
    print("✓ Grundlage 'Rednerbildung: natura – ars – exercitatio' added")
else:
    print("– Grundlage 'Rednerbildung' already present")

# ────────────────────────────────────────────────────────────
# Save
# ────────────────────────────────────────────────────────────
with open(SRC, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# Validate
with open(SRC, encoding="utf-8") as f:
    check = json.load(f)

print()
print(f"✓ JSON valid: {len(check['stilmittel'])} stilmittel, {len(check['grundlagen'])} grundlagen")

# Final line counts
import os
size = os.path.getsize(SRC)
print(f"  File size: {size:,} bytes")
with open(SRC, encoding="utf-8") as f:
    lines = f.read().count('\n')
print(f"  Lines: {lines:,}")
