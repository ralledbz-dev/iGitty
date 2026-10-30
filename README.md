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
| F9 | Ausgewähltes GitHub-Repository als Gitea-Pull-Mirror anlegen |
| Strg+R | GitHub-Repositories aktualisieren |

Bei ZIPs und Git-Backups wird der rechts geöffnete lokale Ordner als Speicherziel vorgeschlagen. Der Speicherdialog bleibt erhalten; nichts wird ungefragt überschrieben. Nach dem Download wird die lokale Ansicht aktualisiert. **Es gibt keine automatische Synchronisation lokaler Ordner, keinen lokalen Upload und kein Verschieben oder Löschen lokaler Dateien.** Gitea-Pull-Mirrors werden separat und nur nach Bestätigung angelegt. Die Tastenbelegung ist iGitty-spezifisch und keine vollständige Nachbildung von Total Commander.

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

Die App hält den GitHub-Token nur im Arbeitsspeicher und speichert ihn weder in Dateien noch in Anwendungseinstellungen. Für Git-Backups wird die Authentifizierung nur dem gestarteten Git-Prozess über dessen Umgebung übergeben; sie landet nicht in der Backup-Datei. **Ausnahme bei Gitea-Pull-Mirrors:** Wenn du der Token-Übergabe ausdrücklich zustimmst, wird der GitHub-Token an deinen lokalen Gitea-Server übergeben und dort für künftige Abgleiche gespeichert. Das Trennen von GitHub in iGitty entfernt ihn nicht aus Gitea.

## GitHub nach Gitea spiegeln

Ziel ist dein lokaler Gitea-Server unter **http://127.0.0.1:3000**. `127.0.0.1` bezeichnet den Rechner, auf dem iGitty läuft. Die Umgebungsvariable **`DBZS_HOME_API_TOKEN`** muss beim Start der App einen gültigen Gitea-API-Token enthalten. Die App liest ihn aus der Umgebung; er wird weder abgefragt noch in die EXE eingebaut oder von der App gespeichert. Der Token benötigt Zugriff auf das Zielkonto und das Erstellen bzw. Lesen von Repositories. Bei eingeschränkten Gitea-Tokens sind dafür typischerweise `read:user` und `write:repository` nötig; zusätzliche Serverregeln können gelten.

1. Prüfe unter **Gitea → Verbindung prüfen** die Anmeldung am lokalen Server.
2. Wähle links ein GitHub-Repository und drücke **F9 → Gitea**.
3. Prüfe Zielkonto und Repository-Name. Das angemeldete Gitea-Konto ist vorausgewählt; eine Organisation ist möglich, wenn dein Token dort Repositories erstellen darf. Das Ziel ist standardmäßig privat; bei einer privaten Quelle ist ein öffentliches Ziel gesperrt.
4. Für öffentliche Quellen ist kein GitHub-Token nötig. Für private Quellen musst du der Übergabe des aktuell verwendeten GitHub-Tokens an Gitea ausdrücklich zustimmen. Nutze dafür einen möglichst eng beschränkten Token mit Lesezugriff auf die Quelle.
5. Bestätige mit **Pull-Mirror anlegen**. Bereits vorhandene Ziel-Repositories werden abgelehnt, nicht überschrieben und nicht automatisch umgewandelt.

Gitea ruft danach selbst periodisch Änderungen von GitHub ab, auch wenn iGitty geschlossen ist. Das Intervall richtet sich nach dem Serverstandard; es lässt sich in den Mirror-Einstellungen von Gitea ändern. Die Spiegelung ist einseitig **GitHub → Gitea** und umfasst Git-Branches, Tags und Commits, nicht Issues, Pull Requests, Releases, Einstellungen oder lokale Ordner. Es erfolgt kein Push nach GitHub. Bei einem Timeout ist das Ergebnis möglicherweise unklar: Prüfe erst das Ziel in Gitea, bevor du erneut startest. Deaktiviere oder entferne den Mirror in Gitea, um weitere Abgleiche zu beenden; verwalte dort auch gespeicherte GitHub-Zugangsdaten.

Die Funktion ist für die Ausführung auf deinem Rechner vorgesehen. Ein echter Verbindungstest mit deinem lokalen Server ist nur dort möglich. Die mitgelieferten Tests verwenden ausschließlich simulierte API-Antworten. Hintergrund: [Gitea-Dokumentation zu Pull-Mirrors](https://docs.gitea.com/usage/repository/repo-mirror/).

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
