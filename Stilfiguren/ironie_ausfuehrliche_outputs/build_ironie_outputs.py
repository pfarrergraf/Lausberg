# -*- coding: utf-8 -*-
from pathlib import Path
import json

OUT = Path(__file__).resolve().parent

def main():
    data = json.loads((OUT / "lausberg_ironie.json").read_text(encoding="utf-8"))
    print("Stilfigur:", data["figure_name_de"])
    print("Originalbegriffe:", ", ".join(x["term"] for x in data["figure_name_original"]))
    print("Kategorie:", data["category"])
    print("DOCX:", OUT / "ironie_einleger_ausfuehrlich.docx")
    print("Markdown:", OUT / "ironie_einleger_ausfuehrlich.md")

if __name__ == "__main__":
    main()
