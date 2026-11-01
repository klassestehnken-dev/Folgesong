# Folgesong-Finder

Zeigt aus Joshuas DJ-Playlisten, welche Songs er nach (oder vor) einem Song am häufigsten gespielt hat,
dazu Listen nach Genre (alle Songs, mit Jahr) und die meistgespielten Songs.

## Technik
- Eine einzige `index.html`, ohne Server und ohne Datenbank. Die Daten stehen als JSON im
  `<script id="data">`-Block (Songs: Titel, Artist, Plays, BPM, Camelot-Key, Genre-Index, Jahr; Übergänge; Genre-Listen).
- `noindex` im Kopf der Seite: Suchmaschinen sollen sie nicht aufnehmen. Das Repo selbst ist trotzdem öffentlich.
- Icon: `icon.svg` (Browser-Tab) und `apple-touch-icon.png` (iPhone-Homebildschirm, 180 px).
- Einstellungen (Anzahl, Richtung, Genre) merkt sich der Browser per localStorage.
- Ursprünglich als Claude-Artefakt gebaut: https://claude.ai/artifact/RCN5V3KeQC4aXY6jUtTcXH

## Hosting
- GitHub Pages, Repo `klassestehnken-dev/Folgesong` (öffentlich), Branch `main`, Ordner `/ (root)`.
- Adresse: https://klassestehnken-dev.github.io/Folgesong/
- Remote: `git@github-konto:klassestehnken-dev/Folgesong.git`

## Veröffentlichen
`index.html` ändern, dann committen und `git push`. GitHub Pages ist nach ca. 1 Minute aktuell.

## Daten
- Quelle: Serato-History (`~/Music/_Serato_/History/Sessions/*.session`) und Bibliothek (`~/Music/_Serato_/database V2`).
  Parser dafür: `../Serato MP3/Engine/historycrate.py`.
- Camelot-Key: Session-Feld 51 bzw. `tkey` in der Bibliothek, zugeordnet über Titel + Artist (häufigster Wert).
  Rund 88 % der Songs haben einen Key, eigene Mixe meist nicht.
- Lokal testen: Browser-Vorschau „folgesong“ aus `Coding/.claude/launch.json` (http://localhost:8765).

## Genres und Erscheinungsjahre
Jeder Song hat genau ein Genre aus Joshuas Liste (27 Genres, Reihenfolge in `werkzeuge/einbauen.py`; House & EDM ist in Charts/Club/Deep geteilt, Rock & Indie in Rock-Klassiker/Indie – das macht `unterteilen()` in `zuordnen.py`) und das erste Erscheinungsjahr.
- `werkzeuge/nachschlagen.py deezer|mb|mbartist|itunes`: Online-Abfrage mit Cache in `werkzeuge/cache/` (nicht im Repo).
  MusicBrainz nur 1 Anfrage/s, alles zusammen dauert mehrere Stunden; Abbruch jederzeit möglich, setzt beim Stand fort.
- `werkzeuge/zuordnen.py [--test]`: feste Regeln (eigene Mixe, Specials, ab 2020 → 2020er, Electro-Swing, Balkan,
  Covers, Dinner) + Bayes-Klassifikator, gelernt an den Hand-Genres; schreibt `cache/genres.json`.
- `werkzeuge/korrekturen.json`: Korrekturen von Hand (`"id": "Genre"` oder `["Genre", Jahr]`), gehen immer vor.
  Die IDs sind die Positionen in der Songliste (`D.s`). Songs bis Platz 2.400 (≥ 5 Plays, 92 % der Plays) sind durchgesehen.
- `werkzeuge/einbauen.py`: schreibt Genre und Jahr in `index.html`. Danach committen und pushen, Artefakt angleichen.
- Neue Playlisten/Songs: Songliste neu erzeugen ändert die IDs, dann müssen Hand-Genres und Korrekturen neu zugeordnet werden.
- Modus „Passend“ (im Artefakt entstanden, auf die Website übernommen): Songs mit ±3/5/8 BPM, harmonischem Key (gleich, ±1, Dur/Moll) und gleichem Genre, sortiert nach Plays. Halbes/doppeltes Tempo zählt mit (73 ↔ 146 BPM).
