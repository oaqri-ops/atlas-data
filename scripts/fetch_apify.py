"""Relevé hebdomadaire : lance l'actor Apify pour chaque ville et enregistre les annonces
dans data/raw/<ville>-<date>.csv.

Les sources (Avito et Mubawab depuis novembre 2026) sont réglées dans data/cities.json (clé "sources").
La colonne "source" du CSV permet à build_site.py de retirer les annonces publiées sur deux portails et de ne
pas comparer deux relevés de sources différentes. Si une source ne renvoie rien pour une ville, aucun
fichier n'est écrit : un relevé sans elle ferait bouger les médianes sans que le marché ait bougé.

Usage : APIFY_TOKEN=... python scripts/fetch_apify.py [--date AAAA-MM-JJ]
"""
import argparse
import csv
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.apify.com/v2"
FIELDS = ["id", "source", "district", "price_mad", "surface_m2", "bedrooms", "furnished", "bathrooms",
          "publication_date", "seller_type"]
MAX_ITEMS = 40000          # garde-fou par ville, toutes sources (Casablanca : environ 12 000 annonces sur Avito, 5 000 sur Mubawab)
RUN_TIMEOUT = 20 * 60      # secondes, par ville
PAGE = 5000                # annonces par requête de lecture du dataset


def api(method, path, token, payload=None, **params):
    url = f"{API}{path}?" + urllib.parse.urlencode({"token": token, **params})
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def run_actor(actor, token, location, sources):
    """Lance un run, attend sa fin, renvoie toutes ses annonces."""
    payload = {"locations": [location], "property_type": "apartment", "transaction": "buy",
               "sources": sources, "max_items": MAX_ITEMS}
    run = api("POST", f"/acts/{actor}/runs", token, payload, timeout=RUN_TIMEOUT)["data"]
    deadline = time.time() + RUN_TIMEOUT + 120
    while run["status"] in ("READY", "RUNNING"):
        if time.time() > deadline:
            sys.exit(f"{location} : le run {run['id']} ne s'est pas terminé à temps")
        run = api("GET", f"/actor-runs/{run['id']}", token, waitForFinish=60)["data"]
    if run["status"] != "SUCCEEDED":
        message = run.get("statusMessage") or run["status"]
        sys.exit(f"{location} : le run {run['id']} a échoué ({message}). Aucun fichier écrit.")
    items, offset = [], 0
    while True:
        page = api("GET", f"/datasets/{run['defaultDatasetId']}/items", token,
                   format="json", clean="true", offset=offset, limit=PAGE)
        items += page
        if len(page) < PAGE:
            return items, run.get("statusMessage") or ""
        offset += PAGE


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
    sources = cfg.get("sources") or ["avito"]
    os.makedirs(os.path.join(ROOT, "data", "raw"), exist_ok=True)
    # Toutes les villes d'abord, les fichiers ensuite : un échec n'écrit pas un relevé à moitié.
    results = []
    for city in cfg["cities"]:
        items, status = run_actor(cfg["actor"], token, city["location"], sources)
        if not items:
            sys.exit(f"{city['name']} : aucune annonce ({status}). Aucun fichier écrit.")
        found = {it.get("source") for it in items}
        missing = [s for s in sources if s not in found]
        if missing:
            sys.exit(f"{city['name']} : aucune annonce {', '.join(missing)} ({status}). Aucun fichier écrit.")
        results.append((city, items, status))
    for city, items, status in results:
        path = os.path.join(ROOT, "data", "raw", f"{city['slug']}-{args.date}.csv")
        with open(path, "w", newline="", encoding="utf8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(FIELDS)
            for it in items:
                w.writerow([cell(it.get("source_listing_id")), cell(it.get("source")), cell(it.get("district")),
                            cell(it.get("price_mad")), cell(it.get("surface_m2")), cell(it.get("bedrooms")),
                            cell(it.get("furnished")), cell(it.get("bathrooms")), cell(it.get("publication_date")),
                            cell(it.get("seller_type"))])
        print(f"{city['name']}: {len(items)} annonces -> {os.path.relpath(path, ROOT)} | {status}")


if __name__ == "__main__":
    main()
