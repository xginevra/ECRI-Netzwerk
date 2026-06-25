"""
Geocoding-Script für lokale CSV-Datei
=========================================

Was macht das Script?
- Liest deine CSV-Datei ein
- Für jede Zeile: Adresse wird via Nominatim (OpenStreetMap, kostenlos,
  kein API-Key nötig) in Koordinaten (latitude/longitude) umgewandelt
- Schreibt eine neue CSV mit zusätzlichen latitude/longitude-Spalten

Diese neue CSV kannst du danach in Supabase importieren (Table Editor ->
Insert -> Import data from CSV), oder die bestehende Tabelle aktualisieren.

Voraussetzungen
----------------
Python-Paket installieren:
   pip install requests

Nutzung
-------
   python geocode_csv.py eingabe.csv ausgabe.csv

Das Script ist sicher mehrfach ausführbar: Zeilen mit bereits gefüllten
latitude/longitude in der Eingabedatei werden übersprungen (außer mit --force).
"""

import sys
import csv
import time
import requests

# ──────────────────────────────────────────────
# 👉 SPALTENNAMEN ANPASSEN falls nötig
# ──────────────────────────────────────────────
ID_COLUMN = "id"                # Spalte mit der eindeutigen ID (nur fürs Logging)
ADDRESS_COLUMN = "Adresse"      # Spalte mit der Adresse
NAME_COLUMN = "Unternehmen"     # Spalte mit dem Firmennamen (nur fürs Logging)
LAT_COLUMN = "latitude"
LON_COLUMN = "longitude"

# In dieser CSV ist die Adresse als "Straße Nr; PLZ Ort" formatiert
# (Semikolon statt Komma). Nominatim funktioniert zuverlässiger mit
# Kommas — diese Bereinigung wird aber NUR für die Geocoding-Anfrage
# verwendet (siehe clean_address()). Die Original-Adresse mit ";" bleibt
# in der Output-CSV unverändert erhalten, es wird nur eine Kopie bereinigt.
FIX_ADDRESS_SEPARATOR = True
# ──────────────────────────────────────────────

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_DELAY_SECONDS = 1.0   # Nominatim erlaubt max. 1 Anfrage/Sekunde
USER_AGENT = "unternehmenskarte-geocoder/1.0 (kontakt@example.com)"

FORCE_RECODE = "--force" in sys.argv


def clean_address(address: str) -> str:
    """Bereinigt die Adresse für zuverlässigeres Geocoding."""
    if not address:
        return address
    cleaned = address.strip()
    if FIX_ADDRESS_SEPARATOR:
        cleaned = cleaned.replace(";", ",")
    # Mehrfache Leerzeichen/Kommas glätten
    cleaned = " ".join(cleaned.split())
    return cleaned


def geocode_address(address: str, retries: int = 2):
    """Fragt Nominatim nach Koordinaten für eine Adresse. Gibt (lat, lon) oder None zurück."""
    if not address or not address.strip():
        return None

    address = clean_address(address)
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(retries + 1):
        try:
            response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
            if response.status_code == 403:
                print("   ⚠ 403 Forbidden von Nominatim. Das passiert meist wenn:")
                print("     - der USER_AGENT zu generisch ist (oben im Script anpassen)")
                print("     - zu viele Anfragen zu schnell gesendet wurden")
                print("     Versuch's ggf. mit einem spezifischeren USER_AGENT.")
                return None
            if response.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"   ⏳ Rate-Limit erreicht, warte {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            results = response.json()
            if not results:
                return None
            return float(results[0]["lat"]), float(results[0]["lon"])
        except (requests.RequestException, KeyError, ValueError, IndexError) as e:
            print(f"   ⚠ Fehler beim Geocoding: {e}")
            return None

    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print("Nutzung: python geocode_csv.py eingabe.csv ausgabe.csv")
        sys.exit(1)

    input_path, output_path = args

    print(f"Lese '{input_path}'...")
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames)

    if ADDRESS_COLUMN not in fieldnames:
        print(f"❌ Spalte '{ADDRESS_COLUMN}' nicht gefunden. Verfügbare Spalten:")
        print(f"   {fieldnames}")
        sys.exit(1)

    # latitude/longitude-Spalten anlegen falls nicht vorhanden
    if LAT_COLUMN not in fieldnames:
        fieldnames.append(LAT_COLUMN)
    if LON_COLUMN not in fieldnames:
        fieldnames.append(LON_COLUMN)

    print(f"{len(rows)} Zeilen geladen.\n")

    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, row in enumerate(rows, start=1):
        row_id = row.get(ID_COLUMN, "?")
        name = row.get(NAME_COLUMN, f"Zeile {i}")
        address = row.get(ADDRESS_COLUMN)

        has_coords = row.get(LAT_COLUMN) and row.get(LON_COLUMN)
        if has_coords and not FORCE_RECODE:
            skip_count += 1
            continue

        if not address:
            print(f"[{i}/{len(rows)}] (id={row_id}) {name}: keine Adresse vorhanden, übersprungen.")
            row[LAT_COLUMN] = row.get(LAT_COLUMN, "")
            row[LON_COLUMN] = row.get(LON_COLUMN, "")
            skip_count += 1
            continue

        print(f"[{i}/{len(rows)}] (id={row_id}) {name}: geocode '{address}'...")
        coords = geocode_address(address)

        if coords is None:
            print(f"   ✗ Keine Koordinaten gefunden.")
            row[LAT_COLUMN] = ""
            row[LON_COLUMN] = ""
            fail_count += 1
        else:
            lat, lon = coords
            row[LAT_COLUMN] = lat
            row[LON_COLUMN] = lon
            print(f"   ✓ {lat:.5f}, {lon:.5f}")
            success_count += 1

        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\nSchreibe Ergebnis nach '{output_path}'...")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\n── Zusammenfassung ──")
    print(f"✓ Erfolgreich geocodet: {success_count}")
    print(f"↷ Übersprungen (schon vorhanden / keine Adresse): {skip_count}")
    print(f"✗ Fehlgeschlagen: {fail_count}")
    print(f"\nFertig! Ergebnis liegt in: {output_path}")


if __name__ == "__main__":
    main()
