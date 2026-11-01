"""
Ordnet jedem Song genau ein Genre aus Joshuas Liste zu und bestimmt das erste Erscheinungsjahr.

Vorgehen:
1. Feste Regeln: eigene Mixe, Specials (Geburtstag, Weihnachten, Titelsongs), alles ab 2020 → 2020er,
   eindeutige Stichwörter für die neuen Genres (Electro-Swing, Balkan, Akustik …).
2. Sonst lernt ein einfacher Bayes-Klassifikator an den von Hand eingeordneten Songs, welche
   Online-Angaben (Deezer-Genres, MusicBrainz-Tags, Jahrzehnt, deutsch ja/nein, BPM) zu welchem Genre passen.
   Dazu kommen die Set-Nachbarn und die Hand-Genres anderer Songs desselben Künstlers.
3. Korrekturen von Hand (werkzeuge/korrekturen.json) gehen immer vor.

Aufruf:  python3 -I werkzeuge/zuordnen.py [--test]
--test   prüft das Verfahren an den Hand-Genres (jeder Song ohne sein eigenes Genre)
Ausgabe: werkzeuge/cache/genres.json  {id: {genre, jahr, sicherheit, quelle, api, hinweis}}
"""

import collections
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nachschlagen import CACHE, aehnlich, artist_haupt, eigener_mix, fold, lade, titel_sauber  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HIER, "..", "index.html")

STIL = {"Hip-Hop & R&B (ab 2000)", "90er Hip-Hop & R&B", "Deutschrap & Hip-Hop", "Reggae & Dancehall",
        "Deutschpop & Deutschrock", "Kölsch & Karneval", "Schlager & Ballermann", "Latin & Reggaeton",
        "Rock & Indie", "House & EDM"}

SPECIAL = re.compile(r"happy birthday|birthday|geburtstag|weihnacht|christmas|xmas|jingle bell|"
                     r"pok[eé]mon|\btheme\b|titelsong|fresh prince|kinderlied|nikolaus|schneeflöckchen|let it snow|"
                     r"santa baby|santa claus|winter wonderland|cold outside|feliz navidad|rudolph|white christmas|snowman", re.I)
SWING = re.compile(r"electro ?swing|nu jazz|nu-jazz|swing house", re.I)
SWING_ARTIST = re.compile(r"parov stelar|caravan palace|gramatik|caro emerald|cat empire|jamie berry|"
                          r"swing republic|tape five|movits|dunkelbunt|g-swing|sim gretina|lyre le temps", re.I)
BALKAN = re.compile(r"balkan|gypsy|bhangra|klezmer|romani|turbo-folk|chanson|french hip hop|"
                    r"french pop|vari[eé]t[eé] fran", re.I)
BALKAN_ARTIST = re.compile(r"shantel|panjabi mc|bregovi|fanfare cio|boban|kusturica|balkan beat|"
                           r"stromae|zaz\b|louane|sexion d.assaut|maître gims|indila|kendji|magic system", re.I)
COVER_ARTIST = re.compile(r"daniela andrade|alex cornell|obadiah parker|baseballs|julia sheer|"
                          r"postmodern jukebox|scott bradlee|matt johnson|janet devlin|funk ferret|ortopilot|"
                          r"boyce avenue|tiffany alvord|jazzbit|dieter thomas kuhn", re.I)

DINNER = re.compile(r"vocal jazz|\bjazz\b|crooner|easy listening|lounge|bossa|quiet storm|smooth soul|"
                    r"traditional pop|swing|big band|downtempo|trip hop|chill", re.I)
NICHT_DINNER = re.compile(r"hip hop|rap\b|reggae|dancehall|trap|metal|punk|reggaeton|grunge|hard rock|"
                          r"house|edm|techno|schlager|k[oö]lsch|karneval", re.I)

DEUTSCH_WORT = re.compile(r"[äöüß]|\b(ich|du|und|der|die|das|nicht|mir|mein|dich|wir|ein|eine|auf|wie|zu|"
                          r"mit|für|von|nur|noch|alles|immer|liebe|leben|nacht|jetzt|schön|geht|kein|"
                          r"mer|un|dä|et|jeht|kölle)\b", re.I)


def jahr_aus(datum):
    m = re.match(r"(\d{4})", datum or "")
    y = int(m.group(1)) if m else 0
    return y if 1940 <= y <= 2026 else 0


def daten():
    s = open(HTML, encoding="utf-8").read()
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', s, re.S).group(1))


def nachbarn(D):
    nb = collections.defaultdict(collections.Counter)
    for i, a in enumerate(D["e"]):
        for k in range(0, len(a), 2):
            nb[i][a[k]] += a[k + 1]
            nb[a[k]][i] += a[k + 1]
    return nb


def tag(t):
    return re.sub(r"\s+", " ", t.lower().replace("-", " ").replace("&", " and ")).strip()


def merkmale(s, sid, Q):
    """Merkmale eines Songs, das früheste plausible Jahr, die Herkunft der Daten und Roh-Angaben."""
    dz, dza, mb, mba, it = Q
    f, api, jahre, quellen = set(), [], [], []
    for r in dz.get(sid, [])[:3]:
        al = dza.get(r["album"], {})
        for g in al.get("genres", []):
            f.add("dz:" + tag(g))
            api.append("dz:" + g)
        y = jahr_aus(al.get("datum"))
        if y:
            jahre.append((y, "deezer"))
    if dz.get(sid):
        quellen.append("deezer")
    recs = mb.get(sid, [])
    tags = collections.Counter()
    for r in recs:
        y = jahr_aus(r["datum"])
        if y:
            jahre.append((y, "musicbrainz"))
        for t, c in r["tags"]:
            tags[tag(t)] += max(c, 1)
    for t, _ in tags.most_common(8):
        f.add("mb:" + t)
        api.append("mb:" + t)
    land = ""
    if recs:
        quellen.append("musicbrainz")
        a = mba.get(recs[0]["artist_id"], {})
        land = a.get("land", "")
        for t, c in sorted(a.get("tags", []), key=lambda x: -x[1])[:8]:
            f.add("mba:" + tag(t))
            api.append("mba:" + t)
    for r in it.get(sid, [])[:3]:
        f.add("it:" + tag(r["genre"]))
        api.append("it:" + r["genre"])
        y = jahr_aus(r["datum"])
        if y:
            jahre.append((y, "itunes"))
    if it.get(sid):
        quellen.append("itunes")
    # Frühestes Jahr: Wiederveröffentlichungen sind immer später, also zählt das Minimum
    y, yq = min(jahre) if jahre else (0, "")
    if y:
        f.add(f"dec:{y // 10 * 10}")
    else:
        f.add("dec:?")
    de = land in ("DE", "AT", "CH") or bool(DEUTSCH_WORT.search(s["titel"]))
    f.add("de:" + ("ja" if de else "nein"))
    if land:
        f.add("land:" + land)
    b = s["bpm"]
    f.add("bpm:" + ("?" if not b else "<90" if b < 90 else "<110" if b < 110 else "<124" if b < 124 else "<132" if b < 132 else "132+"))
    return f, y, yq, list(dict.fromkeys(api)), quellen


def jahrzehnt(y, f):
    if y >= 2020:
        return "2020er"
    if y >= 2010:
        return "2010er Pop"
    if y >= 2000:
        return "2000er Pop"
    if y >= 1990:
        return "90er Pop"
    if y >= 1980:
        return "80er"
    if y >= 1970:
        return "70er"
    return "Oldies (50er & 60er)" if y else ""


def feste_regel(s, f, y, allf, gleiche_titel):
    """Regeln für eindeutige Fälle und für die neuen Genres ohne Hand-Beispiele."""
    t = s["titel"] + " " + s["artist"]
    txt = " ".join(allf)
    if eigener_mix(s):
        return "Eigene Mixe & Jingles", "hoch"
    if SPECIAL.search(t):
        return "Specials", "hoch"
    if SWING_ARTIST.search(s["artist"]) or SWING.search(txt):
        return "Funk, Soul & Electro-Swing", "mittel"
    if BALKAN_ARTIST.search(s["artist"]) or BALKAN.search(txt):
        return "Balkan & Weltmusik", "mittel"
    if COVER_ARTIST.search(s["artist"]):
        return "Covers & Akustik", "mittel"
    if gleiche_titel and re.search(r"acoustic|\bcover|a cappella|unplugged", txt):
        return "Covers & Akustik", "niedrig"
    b = s["bpm"]
    if b and b < 96 and DINNER.search(txt) and not NICHT_DINNER.search(txt):
        return "Hochzeit, Balladen & Dinner", "niedrig"
    if y >= 2020:
        return "2020er", "hoch"
    return None


class Bayes:
    def __init__(self, beispiele, alpha=0.5):
        self.alpha = alpha
        self.n = collections.Counter()
        self.c = collections.defaultdict(collections.Counter)
        self.vocab = set()
        for f, g in beispiele:
            self.add(f, g, 1)

    def add(self, f, g, w):
        self.n[g] += w
        for x in f:
            self.c[g][x] += w
            self.vocab.add(x)

    def scores(self, f):
        V = len(self.vocab)
        out = {}
        for g, n in self.n.items():
            if n <= 0:
                continue
            s = 0.0
            for x in f:
                if x in self.vocab:
                    s += math.log((self.c[g][x] + self.alpha) / (n + self.alpha * 2))
            out[g] = s
        return out


# Zweite Stufe: House & EDM und Rock & Indie werden weiter unterteilt (nach Tags, Deezer-Bekanntheit, BPM, Jahr)
DEEP = re.compile(r"deep house|nu.?disco|^disco$|downtempo|lounge|chill|indie dance|soulful|melodic|organic|"
                  r"\bjazz|\bfunk", re.I)
CLUB = re.compile(r"electro house|big room|tech house|techno|trance|hard ?style|dutch|bounce|jumpstyle|hard dance|"
                  r"bass house|fidget|minimal|electroclash|complextro|dubstep|drum and bass|breakbeat", re.I)
CHARTS = re.compile(r"^pop$|dance pop|dance-pop|electropop|tropical house|charts", re.I)
KLASSIK = re.compile(r"classic rock|hard rock|metal|blues|album rock|arena rock|glam|southern rock|grunge|"
                     r"funk rock|stoner|rock and roll|rock & roll|psychedelic", re.I)
INDIE = re.compile(r"indie|punk|emo|britpop|garage|post-punk|new wave|power pop|pop rock|alternative dance", re.I)

ELTERN = {"Charts-House & EDM": "House & EDM", "Club & Electro House": "House & EDM",
          "Deep House & Nu-Disco": "House & EDM", "Rock-Klassiker & Hard Rock": "Rock & Indie",
          "Indie & Pop-Punk": "Rock & Indie"}


def unterteilen(g, s, api, y, rang):
    tags = [t.split(":", 1)[1] for t in api if t.startswith(("mb:", "mba:", "dz:", "it:"))]
    def n(rx): return sum(1 for t in tags if rx.search(t))
    bpm = s.get("bpm") or 0
    if g == "House & EDM":
        deep, club, charts = n(DEEP), n(CLUB), n(CHARTS)
        if rang and rang >= 550000:
            charts += 3
        elif rang and rang < 350000:
            club += 1.5
        if bpm and bpm <= 122:
            deep += 1
        elif bpm >= 126:
            club += 0.5
        best = max([(charts, "Charts-House & EDM"), (club, "Club & Electro House"), (deep, "Deep House & Nu-Disco")])
        return best[1] if best[0] > 0 else "Club & Electro House"
    if g == "Rock & Indie":
        k, i = n(KLASSIK), n(INDIE)
        if y and y < 1995:
            k += 1.5
        elif y and y >= 2000:
            i += 1
        return "Rock-Klassiker & Hard Rock" if k > i else "Indie & Pop-Punk"
    return g


def main():
    test = "--test" in sys.argv
    songs = json.load(open(os.path.join(CACHE, "songs.json"), encoding="utf-8"))
    mb = lade("mb_limit25")
    mb.update(lade("mb"))
    Q = (lade("deezer"), lade("deezer_alben"), mb, lade("mb_artist"), lade("itunes"))
    D = daten()
    nb = nachbarn(D)
    korr = lade_korrekturen()
    hand = {s["id"]: s["genre_hand"] for s in songs if s["genre_hand"]}
    hand.update({int(k): v[0] for k, v in korr.items()})
    # Untergenres lernt der Klassifikator als ihr Obergenre, die Aufteilung macht unterteilen()
    hand = {i: ELTERN.get(g, g) for i, g in hand.items()}

    M = {}
    for s in songs:
        M[s["id"]] = merkmale(s, str(s["id"]), Q)

    titel_zahl = collections.Counter(fold(titel_sauber(s["titel"])) for s in songs)
    top_titel = {}
    for s in songs:  # meistgespielte Fassung eines Titels
        k = fold(titel_sauber(s["titel"]))
        if k not in top_titel:
            top_titel[k] = s["id"]

    # Neue Genres haben zu wenige Beispiele zum Lernen, für sie gelten nur die festen Regeln
    NEU = {"Eigene Mixe & Jingles", "Funk, Soul & Electro-Swing", "Covers & Akustik", "Balkan & Weltmusik",
           "Specials", "Hochzeit, Balladen & Dinner"}
    beispiele = [(M[i][0], g) for i, g in hand.items() if g not in NEU and g != "2020er"]
    NB = Bayes(beispiele)
    artist = collections.defaultdict(collections.Counter)
    for i, g in hand.items():
        if g in STIL:
            artist[fold(artist_haupt(songs[i]["artist"]))][g] += 1

    W_NB, W_ART = float(os.environ.get("W_NB", 1.5)), float(os.environ.get("W_ART", 10))

    def bestimme(s, ohne_selbst):
        i = s["id"]
        f, y, yq, api, quellen = M[i]
        k = fold(titel_sauber(s["titel"]))
        cover = titel_zahl[k] > 1 and top_titel[k] != i and \
            aehnlich(artist_haupt(songs[top_titel[k]]["artist"]), artist_haupt(s["artist"])) < 0.6
        r = feste_regel(s, f, y, api, cover)
        if r:
            return r[0], r[1], "regel", ""
        if ohne_selbst and i in hand:
            NB.add(f, hand[i], -1)
        sc = NB.scores(f)
        if ohne_selbst and i in hand:
            NB.add(f, hand[i], 1)
        # Set-Nachbarn
        nbg = collections.Counter()
        for j, c in nb[i].items():
            if j in hand and j != i:
                nbg[hand[j]] += c
        tot = sum(nbg.values())
        for g in sc:
            sc[g] += W_NB * math.log((nbg[g] + 0.3) / (tot + 3)) if tot else 0
        # gleicher Künstler
        a = artist[fold(artist_haupt(s["artist"]))].copy()
        if ohne_selbst and i in hand and hand[i] in STIL:
            a[hand[i]] -= 1
        for g, c in a.items():
            if c > 0 and g in sc:
                sc[g] += W_ART
        # Jahrzehnt-Genres nur passend zum Jahr
        dec = jahrzehnt(y, f)
        for g in list(sc):
            if g in ("2010er Pop", "2000er Pop", "90er Pop", "90er Eurodance", "80er", "70er",
                     "Oldies (50er & 60er)", "2020er", "90er Hip-Hop & R&B", "Hip-Hop & R&B (ab 2000)") and y:
                ok = (g == dec or (g == "90er Eurodance" and dec == "90er Pop")
                      or (g == "90er Hip-Hop & R&B" and 1986 <= y < 2001)
                      or (g == "Hip-Hop & R&B (ab 2000)" and y >= 1999))
                if not ok:
                    sc[g] -= 8
        best = sorted(sc.items(), key=lambda x: -x[1])
        g, p = best[0]
        abstand = p - best[1][1] if len(best) > 1 else 9
        sich = "hoch" if abstand > 4 and quellen else "mittel" if abstand > 1.5 else "niedrig"
        hinweis = ""
        if tot >= 6:
            vg, vc = nbg.most_common(1)[0]
            if vg != g and vc / tot >= 0.7:
                hinweis = f"Set-Nachbarn eher {vg} ({vc / tot:.0%})"
        q = quellen[0] if quellen else "set_nachbarn"
        return g, sich, q, hinweis

    if test:
        ok, fehler, n = 0, [], 0
        for i, g in hand.items():
            s = songs[i]
            if eigener_mix(s):
                continue
            n += 1
            gg, sich, q, h = bestimme(s, True)
            if gg == g:
                ok += 1
            else:
                fehler.append((s["plays"], s["titel"], s["artist"], g, gg, M[i][1], M[i][3][:5]))
        print(f"Test: {ok}/{n} richtig ({ok / n:.0%})")
        fehler.sort(reverse=True)
        for x in fehler[:int(os.environ.get("ZEIGE", 40))]:
            print(x)
        return

    ergebnis = {}
    for s in songs:
        i = s["id"]
        f, y, yq, api, quellen = M[i]
        g, sich, q, hinweis = bestimme(s, False)
        if str(i) in korr:
            g, sich, q, hinweis = korr[str(i)][0], "hoch", "hand", ""
            if korr[str(i)][1]:
                y, yq = korr[str(i)][1], "hand"
        elif i in hand:
            if g != hand[i] and not eigener_mix(s):
                hinweis = f"Konflikt: Online-Daten deuten auf {g}"
            g, sich, q = hand[i], "hoch", "hand"
        dzr = Q[0].get(str(i)) or []
        g = unterteilen(g, s, api, y, dzr[0].get("rank") if dzr else None)
        ergebnis[str(i)] = {"genre": g, "jahr": y, "jahr_quelle": yq, "sicherheit": sich, "quelle": q,
                            "api": api[:8], "hinweis": hinweis}
    json.dump(ergebnis, open(os.path.join(CACHE, "genres.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(collections.Counter(e["genre"] for e in ergebnis.values()).most_common())
    print(collections.Counter(e["sicherheit"] for e in ergebnis.values()))


def lade_korrekturen():
    p = os.path.join(HIER, "korrekturen.json")
    roh = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    # Wert ist entweder "Genre" oder ["Genre", Jahr]
    return {k: (v, 0) if isinstance(v, str) else (v[0], v[1]) for k, v in roh.items()}


if __name__ == "__main__":
    main()
