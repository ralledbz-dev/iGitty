# iGitty — GitHub Repository Manager

Eine lokale Desktop-App mit Python und PySide6 zum Verwalten deiner GitHub-Repositories.

## Starten

Benötigt Python 3.10 oder neuer. Installiere die Abhängigkeiten und starte die App:

```bash
python -m pip install -r requirements.txt
python app.py
```

## Windows-Executable erstellen

Die Windows-EXE wird auf einem Windows-Computer erstellt (64-Bit-Python empfohlen). Im Projektordner `build_windows.bat` doppelklicken oder in einer Eingabeaufforderung ausführen. Das Skript richtet eine separate Build-Umgebung ein, installiert PySide6 und PyInstaller und erzeugt:

```text
dist\iGitty.exe
```

Die EXE enthält Python und PySide6; auf dem Zielrechner ist keine Python-Installation erforderlich. **Git ist für Git-Bundle-Backups weiterhin separat erforderlich** und muss im `PATH` liegen. ZIP-Downloads, Bearbeitung und Repository-Verwaltung benötigen Git nicht.

Ein Windows-Programm kann nicht zuverlässig als Windows-EXE auf Linux erzeugt werden. Daher wird die EXE mit dem mitgelieferten Build-Skript direkt unter Windows gebaut.

## Funktionen

- Repositories auflisten, durchsuchen und nach Sichtbarkeit filtern.
- Quellcode des Standard-Branches als ZIP herunterladen.
- Repository-Name, Beschreibung, Website und Sichtbarkeit bearbeiten.
- Textdateien bis 1 MB bearbeiten oder neue Dateien anlegen. Speichern erstellt einen Commit im Standard-Branch.
- Git-Bundle mit erreichbaren Branches, Tags und Commit-Historie erstellen; Wiederherstellung mit `git clone projekt.bundle`.
- Repositories nach exakter Namensbestätigung dauerhaft löschen.

## GitHub verbinden

Erstelle einen Fine-grained Personal Access Token und beschränke ihn auf die gewünschten Repositories. Für die angebotenen Funktionen werden die Repository-Berechtigungen **Contents: Read and write** und **Administration: Read and write** benötigt. GitHub kann für Organisationen zusätzliche Freigabe verlangen. Verwende möglichst den kleinstmöglichen Zugriff.

Der Token wird nur im Arbeitsspeicher gehalten. Er wird weder in Dateien noch in Anwendungseinstellungen gespeichert und beim Trennen oder Schließen der App verworfen. Für Git-Backups wird die Authentifizierung nur dem gestarteten Git-Prozess über dessen Umgebung übergeben; sie landet nicht in der Backup-Datei.

## Backup-Hinweis und Sicherheit

Ein Git-Bundle sichert erreichbare Git-Referenzen (Branches und Tags) sowie die Commit-Historie. Es enthält keine GitHub-Issues, Pull Requests, Releases, Wiki-Inhalte, Actions-Secrets oder tatsächlichen Git-LFS-Binärdateien. Ein ZIP enthält nur den Quellcode des Standard-Branches, keine Git-Historie.

Die App ist für den lokalen Einzelbenutzerbetrieb gedacht. Das Löschen eines Repositories ist endgültig; erstelle bei Bedarf vorher ein Git-Bundle.
