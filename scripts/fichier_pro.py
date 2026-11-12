"""Fichier Pro du lundi : toutes les annonces d'une ville dans un Excel, une seule fois chacune.

Le fichier reprend les annonces du relevé de la ville (Avito et Mubawab), avec le titre, l'agence et le lien,
et retire les doublons avec la même règle que le site (build_site.read_listings) :
- dans un même portail : même quartier, prix, surface et chambres ;
- entre deux portails : même quartier, prix et surface ; l'annonce Avito est gardée.
Les quartiers de Mubawab sont ramenés aux noms d'Avito (data/cities.json), comme sur le site.

« Nouvelle cette semaine » et « Baisse de prix » comparent avec le fichier précédent de la même ville,
dont l'état est gardé dans <sortie>/.etat/. Le premier fichier d'une ville n'a donc pas ces deux colonnes remplies.

Les fichiers sont écrits HORS du dépôt (par défaut ~/atlas-data-pro) : le dépôt est publié tel quel sur
atlas-data.fr, un fichier Pro qui y serait ajouté deviendrait public.

Usage :
  APIFY_TOKEN=... python scripts/fichier_pro.py --ville marrakech
      prend le dernier run réussi de l'actor pour cette ville (celui du relevé du lundi)
  APIFY_TOKEN=... python scripts/fichier_pro.py --toutes
  APIFY_TOKEN=... python scripts/fichier_pro.py --ville marrakech --dataset <ID du dataset>
  python scripts/fichier_pro.py --ville marrakech --input annonces.json   (export JSON du dataset, sans token)
Options : --date AAAA-MM-JJ (date du relevé, par défaut la date du run ou aujourd'hui), --sortie DOSSIER
"""
import argparse
import csv
import datetime
import json
import os
import sys
import tempfile

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site  # noqa: E402
from fetch_apify import FIELDS, api, cell  # noqa: E402

ROOT = build_site.ROOT
DEFAULT_OUT = os.path.expanduser("~/atlas-data-pro")
PAGE = 1000
NAVY, TINT, NEW_FILL = "0F1A33", "EEF1FA", "E3F3EF"
SOURCE_LABELS = {"avito": "Avito", "mubawab": "Mubawab", "sarouty": "Sarouty"}
COLUMNS = [  # (en-tête, largeur, format)
    ("Portail", 10, None), ("Réf.", 12, None), ("Titre", 60, None), ("Agence", 26, None), ("Quartier", 18, None),
    ("Prix demandé (MAD)", 18, "#,##0"), ("Surface (m²)", 12, None), ("Prix au m² (MAD)", 16, "#,##0"),
    ("Chambres", 10, None), ("Meublé", 10, None), ("Publiée le", 12, "DD/MM/YYYY"),
    ("Nouvelle cette semaine", 14, None), ("Baisse de prix", 20, None), ("Lien vers l’annonce", 60, None),
]


# ---------- données ----------

def dataset_items(dataset_id, token):
    items, offset = [], 0
    while True:
        page = api("GET", f"/datasets/{dataset_id}/items", token, format="json", clean="true", offset=offset, limit=PAGE)
        items += page
        if len(page) < PAGE:
            return items
        offset += PAGE


def latest_run_dataset(cfg, city, token):
    """Dataset du dernier run réussi lancé pour cette ville avec les sources du relevé (data/cities.json)."""
    sources = sorted(cfg.get("sources") or ["avito"])
    runs = api("GET", f"/acts/{cfg['actor']}/runs", token, desc="true", limit=100, status="SUCCEEDED")["data"]["items"]
    for run in runs:
        record = api("GET", f"/key-value-stores/{run['defaultKeyValueStoreId']}/records/INPUT", token)
        if record.get("locations") == [city["location"]] and sorted(record.get("sources") or []) == sources:
            return run["defaultDatasetId"], run["startedAt"][:10]
    sys.exit(f"{city['name']} : aucun run réussi récent avec les sources {sources}. Utilisez --dataset.")


def tag_listings(items, city, date, cfg):
    """Passe les annonces par build_site.read_listings (mêmes quartiers et mêmes doublons que le site)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"{city['slug']}-{date}.csv")
        with open(path, "w", newline="", encoding="utf8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(FIELDS)
            for it in items:
                w.writerow([cell(it.get("source_listing_id")), cell(it.get("source")), cell(it.get("district")),
                            cell(it.get("price_mad")), cell(it.get("surface_m2")), cell(it.get("bedrooms")),
                            cell(it.get("furnished")), cell(it.get("bathrooms")), cell(it.get("publication_date")),
                            cell(it.get("seller_type"))])
        rows = build_site.read_listings(path, cfg)
    assert len(rows) == len(items)
    return rows


def signature(r):
    return f"{r['district'].lower()}|{r['price']}|{r['surface']}"


def load_state(out, slug, date):
    """État du fichier précédent de la ville (le plus récent avant date), ou None."""
    folder = os.path.join(out, ".etat")
    if not os.path.isdir(folder):
        return None, None
    found = sorted(f for f in os.listdir(folder) if f.startswith(slug + "-") and f.endswith(".json") and f[len(slug) + 1:-5] < date)
    if not found:
        return None, None
    with open(os.path.join(folder, found[-1]), encoding="utf8") as f:
        return json.load(f), found[-1][len(slug) + 1:-5]


def save_state(out, slug, date, kept):
    folder = os.path.join(out, ".etat")
    os.makedirs(folder, exist_ok=True)
    state = {"sources": sorted({r["source"] for r, _ in kept}), "keys": {r["key"]: r["price"] for r, _ in kept},
             "signatures": sorted({signature(r) for r, _ in kept})}
    with open(os.path.join(folder, f"{slug}-{date}.json"), "w", encoding="utf8") as f:
        json.dump(state, f, ensure_ascii=False)


# ---------- fichier ----------

def pub_date(value):
    try:
        return datetime.datetime.strptime((value or "")[:10], "%Y-%m-%d")
    except ValueError:
        return None


def build_rows(items, tagged, prev):
    kept, dups = [], 0
    for it, r in zip(items, tagged):
        if r.get("dup"):
            dups += 1
            continue
        kept.append((r, it))
    prev_keys = (prev or {}).get("keys", {})
    prev_sigs = set((prev or {}).get("signatures", []))
    # Un portail absent du fichier précédent (ajout de Mubawab) : ses annonces ne sont pas « nouvelles » pour autant
    prev_sources = set((prev or {}).get("sources") or {k.split(":")[0] for k in prev_keys})
    rows, new_count, cut_count = [], 0, 0
    for r, it in kept:
        new = cut = None
        if prev is not None:
            # Nouvelle : ni la même annonce, ni le même bien publié sur l'autre portail, la semaine précédente
            new = (r["source"] in prev_sources and r["key"] not in prev_keys and signature(r) not in prev_sigs) or None
            before = prev_keys.get(r["key"])
            if before and r["price"] and r["price"] < before:
                cut = f"{build_site.n(r['price'] - before)} MAD ({round((r['price'] / before - 1) * 100)} %)".replace("-", "−")
        new_count += bool(new)
        cut_count += bool(cut)
        seller = (it.get("seller_type") or "").lower()
        agency = it.get("agency_name") or ("Particulier" if seller == "private" else None)
        furnished = {True: "Oui", False: "Non"}.get(it.get("furnished"))
        rows.append({"new": bool(new), "values": [
            SOURCE_LABELS.get(r["source"], r["source"]), r["id"], it.get("title"), agency, r["district"] or None,
            r["price"], r["surface"], round(r["ppm2"]) if r["ppm2"] else None, r["bedrooms"], furnished,
            pub_date(it.get("publication_date")),
            ("Oui" if new else None) if prev is not None and r["source"] in prev_sources else None,
            (cut or "-") if prev is not None else None, it.get("listing_url")]})
    # Nouvelles annonces d'abord, puis les plus récentes
    rows.sort(key=lambda x: (not x["new"], -(x["values"][10].timestamp() if x["values"][10] else 0)))
    added = sorted({r["source"] for r, _ in kept} - prev_sources) if prev is not None else []
    return kept, rows, dups, new_count, cut_count, added


def write_workbook(path, city, date, sources, rows, dups, new_count, cut_count, prev_date, added=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Annonces {city['name']}"[:31]
    head_font, head_fill = Font(bold=True, color=NAVY), PatternFill("solid", fgColor=TINT)
    for col, (title, width, _) in enumerate(COLUMNS, 1):
        c = ws.cell(1, col, title)
        c.font, c.fill = head_font, head_fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = width
    new_fill = PatternFill("solid", fgColor=NEW_FILL)
    for i, row in enumerate(rows, 2):
        for col, value in enumerate(row["values"], 1):
            c = ws.cell(i, col, value)
            fmt = COLUMNS[col - 1][2]
            if fmt and value is not None:
                c.number_format = fmt
            if row["new"]:
                c.fill = new_fill
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(rows) + 1}"

    names = build_site.join_fr([SOURCE_LABELS.get(s, s) for s in sources])
    info = wb.create_sheet("À lire")
    info.column_dimensions["A"].width, info.column_dimensions["B"].width = 24, 100
    lines = [
        ("Atlas Data Pro", f"{city['name']}, relevé du {build_site.long_date(date)}"),
        None,
        ("Contenu", f"{len(rows)} annonces d’appartements à vendre à {city['name']} publiées sur {names}."),
        ("Doublons", f"{dups} annonces retirées : le même bien publié deux fois (même quartier, même prix, même surface). "
                     "Quand il est sur Avito et sur Mubawab, c’est l’annonce Avito qui est gardée." if len(sources) > 1 else
                     f"{dups} annonces retirées : le même bien publié deux fois (même quartier, prix, surface et chambres)."),
        ("Nouvelle cette semaine", f"« Oui » si l’annonce n’était pas dans le fichier du {build_site.long_date(prev_date)}. "
                                   f"{new_count} cette semaine, surlignées en vert."
                                   + (f" {build_site.join_fr([SOURCE_LABELS.get(s, s) for s in added])} arrive dans le fichier cette semaine : "
                                      "ses annonces ne sont pas marquées comme nouvelles." if added else "") if prev_date else
                                   "Premier fichier de cette ville : les nouvelles annonces et les baisses de prix apparaîtront au prochain relevé."),
        ("Baisse de prix", f"Écart avec le prix du fichier précédent, en MAD et en %. {cut_count} cette semaine." if prev_date else "Voir ci-dessus."),
        ("Prix", "Prix demandés dans les annonces, pas des prix de vente. Prix au m² = prix demandé / surface publiée."),
        ("Agence", "Nom de l’agence tel qu’affiché sur l’annonce. « Particulier » pour un vendeur particulier sur Avito ; "
                   "vide quand le portail ne l’indique pas dans ses résultats (Mubawab). Aucun nom, téléphone ou email de personne n’est collecté."),
        ("Contact", "othman@atlas-data.fr"),
    ]
    for i, line in enumerate(lines, 1):
        if not line:
            continue
        info.cell(i, 1, line[0]).font = Font(bold=True)
        info.cell(i, 2, line[1]).alignment = Alignment(wrap_text=True, vertical="top")
    info.cell(1, 2).font = Font(bold=True)
    wb.save(path)


def make_file(cfg, city, items, date, out):
    sources = sorted({(it.get("source") or "").lower() for it in items if it.get("source")})
    tagged = tag_listings(items, city, date, cfg)
    prev, prev_date = load_state(out, city["slug"], date)
    kept, rows, dups, new_count, cut_count, added = build_rows(items, tagged, prev)
    path = os.path.join(out, f"atlas-data-pro-{city['slug']}-{date}.xlsx")
    write_workbook(path, city, date, sources, rows, dups, new_count, cut_count, prev_date, added)
    save_state(out, city["slug"], date, kept)
    print(f"{city['name']} : {len(rows)} annonces ({dups} doublons retirés, {new_count} nouvelles, {cut_count} baisses) -> {path}")
    return path


def main():
    ap = argparse.ArgumentParser(description="Fichier Pro du lundi, par ville.")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--ville", help="slug de la ville (marrakech, casablanca, rabat, tanger)")
    who.add_argument("--toutes", action="store_true", help="toutes les villes de data/cities.json")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--dataset", help="ID du dataset Apify (une seule ville)")
    src.add_argument("--input", help="export JSON du dataset (une seule ville)")
    ap.add_argument("--date", help="date du relevé, AAAA-MM-JJ")
    ap.add_argument("--sortie", default=DEFAULT_OUT, help=f"dossier de sortie (par défaut {DEFAULT_OUT})")
    args = ap.parse_args()

    out = os.path.abspath(os.path.expanduser(args.sortie))
    if out == ROOT or out.startswith(ROOT + os.sep):
        sys.exit("Le dossier de sortie est dans le dépôt, qui est publié sur atlas-data.fr : choisissez un dossier ailleurs.")
    os.makedirs(out, exist_ok=True)

    cfg = build_site.load_config()
    by_slug = {c["slug"]: c for c in cfg["cities"]}
    cities = list(by_slug.values()) if args.toutes else [by_slug.get(args.ville) or sys.exit(f"Ville inconnue : {args.ville}")]
    if (args.dataset or args.input) and len(cities) > 1:
        sys.exit("--dataset et --input ne valent que pour une ville (--ville).")

    token = os.environ.get("APIFY_TOKEN")
    for city in cities:
        date = args.date
        if args.input:
            with open(args.input, encoding="utf8") as f:
                items = json.load(f)
        else:
            if not token:
                sys.exit("APIFY_TOKEN manquant (ou utilisez --input avec un export JSON).")
            if args.dataset:
                dataset = args.dataset
            else:
                dataset, run_date = latest_run_dataset(cfg, city, token)
                date = date or run_date
            items = dataset_items(dataset, token)
        if not items:
            sys.exit(f"{city['name']} : aucune annonce.")
        make_file(cfg, city, items, date or datetime.date.today().isoformat(), out)


if __name__ == "__main__":
    main()
