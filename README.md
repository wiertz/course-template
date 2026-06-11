# course-template

Build-Werkzeug für statische Kurswebseiten (universitäre Seminare). Inhalte
werden in Markdown + YAML gepflegt und per **Pandoc** in ein deploybares
statisches HTML-Verzeichnis (`_site/`) übersetzt.

Dieses Repo enthält **nur die Vorlage** (Tooling, Pandoc-Template, Assets). Der
konkrete Kursinhalt lebt in einem **eigenen Repo**, das mit `course init`
angelegt wird.

## Installation

Die Vorlage wird einmal als Werkzeug installiert und stellt dann global den
Befehl `course` bereit:

```sh
git clone <dieses-repo> course-template
uv tool install --editable ./course-template
```

`--editable` sorgt dafür, dass Änderungen an Template/Assets/Tooling sofort wirken
und direkt in diesem Repo committet werden können — unabhängig von einzelnen
Kursen.

## Einen Kurs anlegen

```sh
mkdir mein-kurs && cd mein-kurs
git init
course init                      # legt das Kurs-Skelett im aktuellen Verzeichnis an
cp deploy.example.yaml deploy.yaml   # Deploy-Ziel eintragen (gitignored)
course serve                     # http://localhost:8000
```

## Befehle

```sh
course init     # Kurs-Skelett ins aktuelle Verzeichnis schreiben
course build    # einmalig bauen nach _site/
course serve    # bauen + lokal auf http://localhost:8000 ausliefern
course watch    # bauen + bei Änderungen (Inhalt und Vorlage) automatisch neu bauen
course clean    # _site/ entfernen
course deploy   # mit deploy_base bauen und per rsync zu deploy_target ausspielen
```

## Architektur

**Build-Prinzip:** Inhalte (Markdown + YAML + Assets) → Pandoc → statisches HTML
in `_site/`. Die gesamte Build-Logik liegt in [tooling/__init__.py](tooling/__init__.py).

- **Pfadtrennung:** Vorlagen-Dateien (`tooling/templates/`, `tooling/assets/`,
  `tooling/skeleton/`) werden **paket-relativ** (`Path(__file__).parent`)
  aufgelöst und reisen mit der Installation. Kursinhalt wird **cwd-relativ**
  gelesen (`SRC_PATH`, Default `.` = das Kurs-Repo-Root).
- **Seitenerzeugung:** Jede `.md`-Datei wird per Pandoc mit `--citeproc` und dem
  gemeinsamen Template gerendert. Inkrementeller Build über mtime-Vergleich
  (`out_of_date`). Ein `.base`-Marker erzwingt Clean-Rebuild bei geändertem
  Base-Pfad.
- **Seitendateien:** Die Hauptseite eines Ordners heißt `index.md` und wird als
  `index.html` ausgegeben, damit Webserver sie als Verzeichnis-Default
  ausliefern und die saubere URL `/sessions/01/` funktioniert.
- **Sitzungen:** Jede Sitzung ist ein Ordner (`sessions/01/`…) mit einer
  `session.yml` (title/date/time/description/materials), einer `index.md`
  (Prosa/Aufgaben) sowie den sitzungseigenen Materialien. Beim Build wird die
  `session.yml` per `--metadata-file` an Pandoc übergeben.
- **Listings:** Eine `index.md`, deren Verzeichnis Unterordner mit `session.yml`
  enthält (z. B. `sessions/`), erhält automatisch eine nach Datum sortierte
  Tabelle mit Links auf die jeweiligen Sitzungsseiten.
- **Template** ([tooling/templates/default.html](tooling/templates/default.html)):
  Pandoc-Template mit Navigation, Materialliste, Listing-Tabelle und
  Literaturverzeichnis-Anker (`#refs`). **Assets:** Pico.css, `custom.css`,
  Font Awesome.

## Kurs-Layout (flach)

Ein Kurs-Repo enthält den Inhalt direkt im Root:

```
mein-kurs/
├── course.yaml        # Metadaten (Titel, Semester, Dozent, lang, bibliography)
├── index.md           # Homepage
├── assignments.md, results.md, literature.md
├── literature.json    # CSL-Bibliografie
├── sessions/
│   ├── index.md       # Listing
│   └── 01/{session.yml, index.md, …}
├── shared/            # gemeinsam genutzte Materialien
├── deploy.yaml        # gitignored: deploy_base + deploy_target
├── deploy.example.yaml
└── _site/             # Build-Ausgabe (gitignored)
```

## Deployment

`course deploy` liest `deploy.yaml` (gitignored, aus `deploy.example.yaml`
kopiert):

```yaml
deploy_base: /pfad/zum/kurs
deploy_target: user@server:/var/www/pfad/zum/kurs
```

Es baut mit `deploy_base` (alle Links/Asset-URLs bekommen diesen Präfix) und
synchronisiert `_site/` per `rsync --delete` zu `deploy_target`.
