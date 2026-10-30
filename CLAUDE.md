# Folgesong-Finder

Zeigt aus Joshuas DJ-Playlisten, welche Songs er nach (oder vor) einem Song am häufigsten gespielt hat,
dazu Top 25 nach Genre und die meistgespielten Songs.

## Technik
- Eine einzige `index.html`, ohne Server und ohne Datenbank. Die Daten stehen als JSON im
  `<script id="data">`-Block (Songs: Titel, Artist, Plays, BPM; Übergänge; Genres).
- Einstellungen (Anzahl, Richtung, Genre) merkt sich der Browser per localStorage.
- Ursprünglich als Claude-Artefakt gebaut: https://claude.ai/artifact/RCN5V3KeQC4aXY6jUtTcXH

## Hosting
- GitHub Pages, Repo `klassestehnken-dev/Folgesong-Finder` (öffentlich), Branch `main`, Ordner `/ (root)`.
- Adresse: https://klassestehnken-dev.github.io/Folgesong-Finder/
- Remote: `git@github-konto:klassestehnken-dev/Folgesong-Finder.git`

## Veröffentlichen
`index.html` ändern, dann committen und `git push`. GitHub Pages ist nach ca. 1 Minute aktuell.
