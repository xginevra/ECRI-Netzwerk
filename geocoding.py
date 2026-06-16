import pandas as pd
import requests
import time

# Datei laden
df = pd.read_csv("unternehmen_tabelle.csv")

# Falls Spalten fehlen
if 'latitude' not in df.columns:
    df['latitude'] = ''
if 'longitude' not in df.columns:
    df['longitude'] = ''

headers = {
    "User-Agent": "InteraktiveUnternehmenskarte"
}

def geocode(address):
    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": address,
        "format": "json"
    }

    try:
        r = requests.get(url, params=params, headers=headers)
        data = r.json()

        if data:
            return data[0]["lat"], data[0]["lon"]
    except:
        pass

    return "", ""

# Durch alle Firmen iterieren
for i, row in df.iterrows():
    address = str(row['adresse']).strip()

    if not address:
        continue

    query = address + ", Germany"

    lat, lon = geocode(query)

    df.loc[i, "latitude"] = lat
    df.loc[i, "longitude"] = lon

    print(f"{row['name']} → {lat}, {lon}")

    time.sleep(1)  # wichtig! API-Limit

# speichern
df.to_csv("unternehmen_final_mit_coords.csv", index=False)
