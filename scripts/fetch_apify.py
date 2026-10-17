"""Relevé hebdomadaire : lance l'actor Sarouty sur Apify pour chaque ville et
enregistre les annonces dans data/raw/<ville>-<date>.csv.

Usage : APIFY_TOKEN=... python scripts/fetch_apify.py [--date AAAA-MM-JJ]
"""
import argparse
import csv
import datetime
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ["id", "district", "price_mad", "surface_m2", "bedrooms", "furnished", "bathrooms", "publication_date"]


def run_actor(actor, token, location):
    url = (f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
           f"?token={token}&timeout=280&format=json&clean=true")
    payload = {"locations": [location], "property_type": "apartment", "transaction": "buy", "max_items": 3000}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=320) as resp:
        return json.load(resp)


def cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args()
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        sys.exit("APIFY_TOKEN manquant")
    cfg = json.load(open(os.path.join(ROOT, "data", "cities.json"), encoding="utf8"))
    os.makedirs(os.path.join(ROOT, "data", "raw"), exist_ok=True)
    for city in cfg["cities"]:
        items = run_actor(cfg["actor"], token, city["location"])
        path = os.path.join(ROOT, "data", "raw", f"{city['slug']}-{args.date}.csv")
        with open(path, "w", newline="", encoding="utf8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(FIELDS)
            for it in items:
                w.writerow([cell(it.get("source_listing_id")), cell(it.get("district")), cell(it.get("price_mad")),
                            cell(it.get("surface_m2")), cell(it.get("bedrooms")), cell(it.get("furnished")),
                            cell(it.get("bathrooms")), cell(it.get("publication_date"))])
        print(f"{city['name']}: {len(items)} annonces -> {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
