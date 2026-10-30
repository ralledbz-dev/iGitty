# iGitty — GitHub & lokale Ordner

Eine lokale Desktop-App mit Python und PySide6, angelehnt an den klassischen Zweifenster-Aufbau von Total Commander: **links GitHub-Repositories, rechts lokale Ordner**. Helle, kompakte Tabellen, blaue Auswahl und eine Funktionsleiste halten beide Seiten gleichzeitig im Blick. iGitty ist ein eigenständiges Projekt und nicht mit Total Commander verbunden.

## Starten

Benötigt Python 3.10 oder neuer. Im Projektordner:

```bash
python -m pip install -r requirements.txt
python app.py
```

## Zweifenster-Bedienung

Links erscheinen nach der GitHub-Anmeldung die Online-Repositories. Suche und Sichtbarkeitsfilter grenzen die Liste ein. Doppelklick öffnet die Repository-Dateien; „GitHub öffnen“ öffnet das ausgewählte Repository im Browser.

Rechts navigierst du durch das lokale Dateisystem. Ordner lassen sich per Doppelklick, Pfadeingabe, übergeordnetem Ordner, Benutzerordner oder Ordnerauswahl öffnen. Laufwerke bzw. Dateisystemwurzeln sind auswählbar. Dateien werden mit der zugeordneten lokalen Anwendung geöffnet. Diese Seite funktioniert auch ohne GitHub-Verbindung.

Die Trennleiste zwischen den Seiten ist verschiebbar. Über **Ansicht → Fensterhälften gleich breit** stellst du die ursprüngliche Aufteilung wieder her.

| Taste | Funktion |
| --- | --- |
| F3 | Dateien des ausgewählten GitHub-Repositories anzeigen/bearbeiten |
| F4 | Repository-Details bearbeiten |
| F5 | Repository als ZIP herunterladen |
| F6 | Git-Bundle-Backup erstellen |
| F7 | Lokalen Ordner wählen |
| F8 | GitHub-Repository nach ausdrücklicher Namensbestätigung löschen |
| Strg+R | GitHub-Repositories aktualisieren |

Bei ZIPs und Git-Backups wird der rechts geöffnete lokale Ordner als Speicherziel vorgeschlagen. Der Speicherdialog bleibt erhalten; nichts wird ungefragt überschrieben. Nach dem Download wird die lokale Ansicht aktualisiert. **Es gibt keine automatische Synchronisation, keinen lokalen Upload und kein Verschieben oder Löschen lokaler Dateien.** Die Tastenbelegung ist iGitty-spezifisch und keine vollständige Nachbildung von Total Commander.

## Funktionen

- Repositories auflisten, durchsuchen und nach Sichtbarkeit filtern.
- Quellcode des Standard-Branches als ZIP herunterladen.
- Repository-Name, Beschreibung, Website und Sichtbarkeit bearbeiten.
- Textdateien bis 1 MB bearbeiten oder neue Dateien anlegen. Speichern erstellt einen Commit im Standard-Branch.
- Git-Bundle mit erreichbaren Branches, Tags und Commit-Historie erstellen; Wiederherstellung mit `git clone projekt.bundle`.
- Repositories nach exakter Namensbestätigung dauerhaft löschen.
- Lokale Ordner und Dateien parallel zu den Online-Repositories anzeigen und öffnen.

## GitHub verbinden

Erstelle einen Fine-grained Personal Access Token und beschränke ihn auf die gewünschten Repositories. Für die angebotenen Funktionen werden die Repository-Berechtigungen **Contents: Read and write** und **Administration: Read and write** benötigt. GitHub kann für Organisationen zusätzliche Freigabe verlangen. Verwende möglichst den kleinstmöglichen Zugriff.

Der Token wird nur im Arbeitsspeicher gehalten. Er wird weder in Dateien noch in Anwendungseinstellungen gespeichert und beim Trennen oder Schließen der App verworfen. Für Git-Backups wird die Authentifizierung nur dem gestarteten Git-Prozess über dessen Umgebung übergeben; sie landet nicht in der Backup-Datei.

## Windows-Executable erstellen

Die Windows-EXE wird auf einem Windows-Computer erstellt (64-Bit-Python empfohlen). Im Projektordner `build_windows.bat` doppelklicken oder in einer Eingabeaufforderung ausführen. Das Skript richtet eine separate Build-Umgebung ein, installiert PySide6 und PyInstaller und erzeugt `dist\iGitty.exe`.

Die EXE enthält Python und PySide6; auf dem Zielrechner ist keine Python-Installation erforderlich. **Git ist für Git-Bundle-Backups weiterhin separat erforderlich** und muss im `PATH` liegen. ZIP-Downloads, Bearbeitung und Repository-Verwaltung benötigen Git nicht. Das lokale Modul `local_panel.py` muss beim Bauen neben `app.py` liegen; PyInstaller nimmt es über den Import automatisch auf.

Ein Windows-Programm kann nicht zuverlässig als Windows-EXE auf Linux erzeugt werden. Daher wird die EXE mit dem mitgelieferten Build-Skript direkt unter Windows gebaut.

### Automatischer Build und Download

Bei jedem Push auf `main` baut GitHub Actions die Windows-EXE und führt zuvor die Tests aus. Zum Herunterladen öffne im Repository **Actions → Windows-EXE → den neuesten erfolgreichen Lauf** und lade unter **Artifacts** `iGitty-Windows-x64` herunter. GitHub stellt das Artefakt als ZIP bereit; entpacke es, um `iGitty.exe` zu erhalten. Artefakte bleiben 30 Tage verfügbar. Ein Build lässt sich außerdem unter **Actions → Windows-EXE → Run workflow** manuell starten.

## Tests

```bash
python -m unittest discover -s tests -v
```

Für Linux ohne Bildschirm: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`.

## Backup-Hinweis und Sicherheit

Ein Git-Bundle sichert erreichbare Git-Referenzen (Branches und Tags) sowie die Commit-Historie. Es enthält keine GitHub-Issues, Pull Requests, Releases, Wiki-Inhalte, Actions-Secrets oder tatsächlichen Git-LFS-Binärdateien. Ein ZIP enthält nur den Quellcode des Standard-Branches, keine Git-Historie.

Die App ist für den lokalen Einzelbenutzerbetrieb gedacht. Das Löschen eines Repositories ist endgültig; erstelle bei Bedarf vorher ein Git-Bundle.
