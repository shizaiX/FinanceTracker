# Finanzen – Finanztracker fürs Handy

Moderne, schlanke Finanz-Web-App (PWA), optimiert für die Nutzung am Smartphone.
Alle Daten bleiben lokal im Browser (localStorage) – kein Konto, kein Server.

## Funktionen

- **Übersicht** – „Noch verfügbar diesen Monat“, Tagesbudget, heute ausgegeben, Sparquote,
  noch fällige Fixkosten, Vergleich zum Vormonat, Budgets, demnächst fällige Zahlungen,
  Sparziele und letzte Buchungen
- **Fixe Einnahmen & Ausgaben** – Gehalt, Miete, Abos, Versicherungen … mit Rhythmus
  (wöchentlich, monatlich, vierteljährlich, halbjährlich, jährlich), Start-/Enddatum und Pausieren.
  Zeigt, wie viel monatlich nach Fixkosten übrig bleibt
- **Tägliche Ausgaben** – schnelles Erfassen über den „+“-Button mit Kategorien, Notiz-Vorschlägen
  und Datum; Liste nach Tagen gruppiert, Suche über alle Monate, Filter nach Typ/Kategorie,
  Fixposten optional einblendbar
- **Sparziele** – Zielbetrag, Zieldatum, nötige Monatsrate, Ein-/Auszahlungen mit Verlauf,
  Prognose anhand der bisherigen Sparrate
- **Budgets** – Monatslimits pro Kategorie mit Warnung („Zu schnell“, „Überschritten“)
- **Statistik** – auswählbare Diagramme: Kategorien (Ausgaben/Einnahmen), Ein- vs. Ausgaben,
  kumulierter Monatsverlauf vs. Vormonat, Vermögensentwicklung, Sparquote, Kategorie-Trend
  (mit Budgetlinie) und Ausgaben nach Wochentag – für 3 Monate bis 2 Jahre
- **Sonstiges** – Hell/Dunkel/System-Design, Währung, Beträge verbergen, eigene Kategorien,
  JSON-Backup (Export/Import), CSV-Export, Beispieldaten, Rückgängig beim Löschen,
  offline nutzbar und zum Startbildschirm hinzufügbar

## Entwicklung

```bash
npm install
npm run dev      # Dev-Server (auch im lokalen Netz erreichbar → am Handy testen)
npm run build    # Produktions-Build nach dist/
npm run preview  # Build lokal ansehen
```

## Deployment

Der Workflow `.github/workflows/deploy.yml` veröffentlicht die App bei jedem Push auf `main`
über GitHub Pages. Dafür einmalig unter *Settings → Pages → Source* „GitHub Actions“ wählen.
Der Build nutzt relative Pfade und läuft daher auch auf jedem anderen statischen Hosting.

Am Handy die Seite öffnen und „Zum Home-Bildschirm hinzufügen“ wählen – dann startet sie wie eine App.

**Tech:** React 19, TypeScript, Vite, Recharts, lucide-react.
