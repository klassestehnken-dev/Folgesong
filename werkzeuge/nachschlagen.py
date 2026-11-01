"""
Schlägt Genre und Erscheinungsjahr der Songs online nach (Deezer, MusicBrainz, iTunes).
Alle Antworten landen im Cache (werkzeuge/cache/*.json), ein Abbruch ist jederzeit möglich:
beim nächsten Start geht es dort weiter, wo es aufgehört hat.

Aufruf:  python3 -I werkzeuge/nachschlagen.py <deezer|mb|mbartist|itunes>
Eingabe: werkzeuge/cache/songs.json  (id, titel, artist, ...)
"""

import json
import os
import re
import ssl
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

HIER = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HIER, "cache")
UA = "FolgesongFinder/1.0 ( https://klassestehnken-dev.github.io/Folgesong/ )"
# Python von python.org bringt keine Zertifikate mit, daher die des Systems verwenden
SSL = ssl.create_default_context(cafile="/etc/ssl/cert.pem")


# ---------- Bereinigen und Vergleichen ----------

EIGEN = re.compile(r"indamix|herr stehnken|vorprogramm|mash-?up|\bsamples\b|scratch samples", re.I)


def eigener_mix(song):
    return bool(EIGEN.search(song["titel"] + " " + song["artist"]))


def fold(s):
    s = unicodedata.normalize("NFKD", s.lower().replace("ß", "ss"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def titel_sauber(t):
    t = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", t)
    t = re.sub(r"\s+(feat|ft|featuring)\.?\s.*$", "", t, flags=re.I)
    t = re.sub(r"\s+-\s+.*(edit|mix|version|remaster|rework|bootleg).*$", "", t, flags=re.I)
    return t.strip() or t


def artist_haupt(a):
    a = re.split(r"\s+(?:feat\.?|ft\.?|featuring|vs\.?|versus|x|with)\s+|,|/", a, flags=re.I)[0]
    return a.strip()


def aehnlich(a, b):
    a, b = fold(a), fold(b)
    if not a or not b:
        return 0
    if a == b or a in b or b in a:
        return 1
    return SequenceMatcher(None, a, b).ratio()


def passt(song, titel, artist):
    t = aehnlich(titel_sauber(song["titel"]), titel_sauber(titel))
    a = max(aehnlich(artist_haupt(song["artist"]), artist), aehnlich(song["artist"], artist))
    return t >= 0.8 and a >= 0.6


# ---------- Cache und HTTP ----------

def lade(name):
    p = os.path.join(CACHE, name + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def speichere(name, data):
    p = os.path.join(CACHE, name + ".json")
    json.dump(data, open(p + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(p + ".tmp", p)


def hole(url, pause):
    for versuch in range(5):
        time.sleep(pause)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20, context=SSL) as r:
                d = json.loads(r.read().decode("utf-8"))
            if isinstance(d, dict) and d.get("error") and "quota" in json.dumps(d["error"]).lower():
                time.sleep(5)
                continue
            return d
        except Exception as e:
            code = getattr(e, "code", 0)
            if code in (403, 429, 503) or code == 0:
                time.sleep(3 * (versuch + 1))
                continue
            return None
    return None


def songs():
    return [s for s in json.load(open(os.path.join(CACHE, "songs.json"), encoding="utf-8")) if not eigener_mix(s)]


# ---------- Deezer: Album-Genres und Erscheinungsdatum ----------

_takt = threading.Lock()
_letzte = [0.0]


def deezer_hole(url):
    """Deezer erlaubt ca. 50 Anfragen in 5 Sekunden: höchstens 8 pro Sekunde über alle Threads."""
    with _takt:
        warte = _letzte[0] + 0.125 - time.time()
        if warte > 0:
            time.sleep(warte)
        _letzte[0] = time.time()
    return hole(url, 0)


def deezer():
    cache, alben = lade("deezer"), lade("deezer_alben")
    offen = [s for s in songs() if str(s["id"]) not in cache]
    print(f"Deezer: {len(offen)} offen", flush=True)
    sperre = threading.Lock()

    def ein_song(s):
        t, a = titel_sauber(s["titel"]), artist_haupt(s["artist"])
        treffer = []
        for q in (f'artist:"{a}" track:"{t}"', f"{a} {t}"):
            d = deezer_hole("https://api.deezer.com/search?limit=15&q=" + urllib.parse.quote(q))
            treffer = [x for x in (d or {}).get("data", []) if passt(s, x["title"], x["artist"]["name"])]
            if treffer:
                break
        ergebnis = []
        for x in treffer[:3]:
            aid = str(x["album"]["id"])
            if aid not in alben:
                al = deezer_hole(f"https://api.deezer.com/album/{aid}") or {}
                alben[aid] = {"genres": [g["name"] for g in al.get("genres", {}).get("data", [])],
                              "datum": al.get("release_date", ""), "typ": al.get("record_type", ""),
                              "titel": al.get("title", "")}
            ergebnis.append({"titel": x["title"], "artist": x["artist"]["name"], "rank": x.get("rank", 0),
                             "album": aid})
        with sperre:
            cache[str(s["id"])] = ergebnis
            if len(cache) % 100 == 0:
                speichere("deezer", cache), speichere("deezer_alben", dict(alben))
                print(f"Deezer: {len(cache)} fertig", flush=True)

    with ThreadPoolExecutor(6) as pool:
        list(pool.map(ein_song, offen))
    speichere("deezer", cache), speichere("deezer_alben", alben)
    print("Deezer fertig", flush=True)


# ---------- MusicBrainz: erstes Erscheinungsjahr und Tags ----------

class Takt:
    """Höchstens eine neue Anfrage je `abstand` Sekunden, auch wenn mehrere Threads gleichzeitig warten."""

    def __init__(self, abstand):
        self.abstand, self.sperre, self.letzte = abstand, threading.Lock(), 0.0

    def hole(self, url):
        for _ in range(6):
            with self.sperre:
                warte = self.letzte + self.abstand - time.time()
                if warte > 0:
                    time.sleep(warte)
                self.letzte = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=30, context=SSL) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                if getattr(e, "code", 0) not in (0, 429, 503):
                    return None
        return None


MB_TAKT = Takt(1.0)  # MusicBrainz: eine Anfrage pro Sekunde


def parallel(name, offen, ein_schritt, threads=3):
    cache = lade(name)
    sperre = threading.Lock()
    print(f"{name}: {len(offen)} offen", flush=True)

    def lauf(x):
        key, wert = ein_schritt(x)
        with sperre:
            cache[key] = wert
            if len(cache) % 25 == 0:
                speichere(name, dict(cache))
                print(f"{name}: {len(cache)} fertig", flush=True)

    with ThreadPoolExecutor(threads) as pool:
        list(pool.map(lauf, offen))
    speichere(name, cache)
    print(f"{name} fertig", flush=True)


def mb():
    cache = lade("mb")

    def schritt(s):
        t, a = titel_sauber(s["titel"]), artist_haupt(s["artist"])
        q = f'recording:"{t}" AND artist:"{a}"'
        d = MB_TAKT.hole("https://musicbrainz.org/ws/2/recording?fmt=json&limit=100&query=" + urllib.parse.quote(q))
        ergebnis = []
        for r in (d or {}).get("recordings", []):
            name = "".join(c["name"] + c.get("joinphrase", "") for c in r.get("artist-credit", []))
            if not passt(s, r.get("title", ""), name):
                continue
            ergebnis.append({"datum": r.get("first-release-date", ""),
                             "tags": [(g["name"], g.get("count", 0)) for g in r.get("tags", [])],
                             "artist_id": (r.get("artist-credit") or [{}])[0].get("artist", {}).get("id", ""),
                             "artist": name})
        return str(s["id"]), ergebnis

    parallel("mb", [s for s in songs() if str(s["id"]) not in cache], schritt)


def mbartist():
    """Tags und Herkunftsland der Künstler (genauer als die oft leeren Tags einzelner Aufnahmen)."""
    rec, cache = lade("mb"), lade("mb_artist")
    ids = list(dict.fromkeys(r["artist_id"] for lst in rec.values() for r in lst[:3]
                             if r["artist_id"] and r["artist_id"] not in cache))

    def schritt(aid):
        d = MB_TAKT.hole(f"https://musicbrainz.org/ws/2/artist/{aid}?fmt=json&inc=tags+genres") or {}
        return aid, {"name": d.get("name", ""), "land": d.get("country", ""),
                     "tags": [(g["name"], g.get("count", 0)) for g in d.get("genres", []) + d.get("tags", [])]}

    parallel("mb_artist", ids, schritt)


# ---------- iTunes: Ersatz für Songs ohne Treffer ----------

def itunes():
    dz, m, cache = lade("deezer"), lade("mb"), lade("itunes")
    offen = [s for s in songs() if str(s["id"]) not in cache and not dz.get(str(s["id"])) and not m.get(str(s["id"]))]
    print(f"iTunes: {len(offen)} offen", flush=True)
    for n, s in enumerate(offen, 1):
        q = f'{artist_haupt(s["artist"])} {titel_sauber(s["titel"])}'
        d = hole("https://itunes.apple.com/search?media=music&entity=song&limit=10&country=DE&term="
                 + urllib.parse.quote(q), 3.1) or {}
        cache[str(s["id"])] = [{"genre": x.get("primaryGenreName", ""), "datum": x.get("releaseDate", "")[:10],
                                "titel": x.get("trackName", ""), "artist": x.get("artistName", "")}
                               for x in d.get("results", []) if passt(s, x.get("trackName", ""), x.get("artistName", ""))]
        if n % 20 == 0:
            speichere("itunes", cache)
            print(f"iTunes: {n}/{len(offen)}", flush=True)
    speichere("itunes", cache)
    print("iTunes fertig", flush=True)


if __name__ == "__main__":
    {"deezer": deezer, "mb": mb, "mbartist": mbartist, "itunes": itunes}[sys.argv[1]]()
