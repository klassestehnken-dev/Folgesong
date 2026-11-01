"""
Schreibt Genre und Erscheinungsjahr aus werkzeuge/cache/genres.json in die Daten von index.html
und baut daraus die Genre-Listen neu (alle Songs je Genre, nach Plays sortiert).

Aufruf:  python3 -I werkzeuge/einbauen.py
Daten danach: s = [titel, artist, plays, bpm, key, genre-index, jahr], G = Genre-Namen, g = [[name, [[id, plays], …]], …]
"""

import json
import os
import re

HIER = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HIER, "..", "index.html")

GENRES = ["Hip-Hop & R&B (ab 2000)", "90er Hip-Hop & R&B", "Deutschrap & Hip-Hop", "Reggae & Dancehall",
          "Deutschpop & Deutschrock", "Kölsch & Karneval", "Schlager & Ballermann", "Latin & Reggaeton",
          "Rock & Indie", "House & EDM", "Funk, Soul & Electro-Swing", "Balkan & Weltmusik",
          "2020er", "2010er Pop", "2000er Pop", "90er Pop", "90er Eurodance", "80er", "70er", "Oldies (50er & 60er)",
          "Hochzeit, Balladen & Dinner", "Covers & Akustik", "Specials", "Eigene Mixe & Jingles"]


def main():
    src = open(HTML, encoding="utf-8").read()
    m = re.search(r'(<script id="data" type="application/json">)(.*?)(</script>)', src, re.S)
    D = json.loads(m.group(2))
    erg = json.load(open(os.path.join(HIER, "cache", "genres.json"), encoding="utf-8"))
    listen = {g: [] for g in GENRES}
    for i, s in enumerate(D["s"]):
        e = erg[str(i)]
        s[:] = s[:5] + [GENRES.index(e["genre"]), e["jahr"] or 0]
        listen[e["genre"]].append([i, s[2]])
    D["G"] = GENRES
    D["g"] = [[g, sorted(l, key=lambda x: -x[1])] for g, l in listen.items() if l]
    neu = src[:m.start(2)] + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + src[m.end(2):]
    open(HTML, "w", encoding="utf-8").write(neu)
    print({g: len(l) for g, l in D["g"]})


if __name__ == "__main__":
    main()
