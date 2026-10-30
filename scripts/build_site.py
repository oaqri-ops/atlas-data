"""Génère les pages villes et quartiers à partir du dernier relevé de chaque ville.

Lit data/cities.json et data/raw/<ville>-<date>.csv, écrit :
  - <ville>/index.html et <ville>/<quartier>/index.html (villes avec "generate": true)
  - data/stats/<ville>.json
  - la section « Les prix par ville » de l'accueil, les données du dashboard (toutes les villes),
    le menu « Prix par ville » du pied de page de toutes les pages, et sitemap.xml.
Les pages existantes ne sont jamais supprimées.

Usage : python scripts/build_site.py
"""
import csv
import datetime
import glob
import html
import json
import math
import os
import re
import statistics
import unicodedata
from urllib.parse import urlencode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://atlas-data.fr"
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre"]
MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
                "sept.", "oct.", "nov.", "déc."]
NBSP = " "
BED_PLURAL = {1: "les 1 chambre", 2: "les 2 chambres", 3: "les 3 chambres", 4: "les 4 chambres et plus"}

# Nettoyage : un loyer mensuel publié comme une vente, une surface absente ou hors norme
# (immeuble, terrain) ou un prix au m² impossible faussent la médiane d'un petit quartier.
MIN_PRICE = 100_000
MIN_SURFACE = 15
MAX_SURFACE = 1_000
PPM2_RANGE = (2_000, 100_000)


# ---------- données ----------

def load_config():
    with open(os.path.join(ROOT, "data", "cities.json"), encoding="utf8") as f:
        return json.load(f)


def latest_raw(slug):
    files = sorted(glob.glob(os.path.join(ROOT, "data", "raw", f"{slug}-*.csv")))
    if not files:
        return None, None
    path = files[-1]
    return path, re.search(r"(\d{4}-\d{2}-\d{2})\.csv$", path).group(1)


def previous_raw(slug, date):
    """Relevé précédent de la ville (le plus récent avant date), ou (None, None)."""
    files = [f for f in sorted(glob.glob(os.path.join(ROOT, "data", "raw", f"{slug}-*.csv")))
             if re.search(r"(\d{4}-\d{2}-\d{2})\.csv$", f).group(1) < date]
    if not files:
        return None, None
    return files[-1], re.search(r"(\d{4}-\d{2}-\d{2})\.csv$", files[-1]).group(1)


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def read_listings(path, cfg):
    """Toutes les annonces du relevé ; kept=True pour celles qui entrent dans les statistiques."""
    names = cfg["district_names"]
    rows, seen = [], set()
    with open(path, encoding="utf8") as f:
        for r in csv.DictReader(f):
            district = " ".join((r.get("district") or "").split())
            district = names.get(district, district)
            price, surface = to_int(r.get("price_mad")), to_int(r.get("surface_m2"))
            ppm2 = price / surface if price and surface else None
            bedrooms = to_int(r.get("bedrooms"))
            kept = bool(ppm2 and price >= MIN_PRICE and MIN_SURFACE <= surface <= MAX_SURFACE
                        and PPM2_RANGE[0] <= ppm2 <= PPM2_RANGE[1])
            key = (district.lower(), price, surface, bedrooms)
            if kept and key in seen:
                kept = False
            seen.add(key)
            rows.append({"id": r.get("id") or "", "district": district, "price": price, "surface": surface,
                         "ppm2": ppm2, "bedrooms": bedrooms, "furnished": r.get("furnished") or "",
                         "bathrooms": to_int(r.get("bathrooms")), "published": (r.get("publication_date") or "")[:10],
                         "kept": kept})
    return rows


def clean(path, cfg):
    rows = read_listings(path, cfg)
    return len(rows), [r for r in rows if r["kept"]]


def summarize(rows):
    return {
        "n": len(rows),
        "median": round(statistics.median(r["ppm2"] for r in rows)),
        "median_price": round(statistics.median(r["price"] for r in rows)),
        "median_surface": round(statistics.median(r["surface"] for r in rows)),
        "min": round(min(r["ppm2"] for r in rows)),
        "max": round(max(r["ppm2"] for r in rows)),
    }


def bedroom_groups(rows):
    groups = {}
    for r in rows:
        b = r["bedrooms"]
        if b is None or b < 1:
            continue
        groups.setdefault(min(b, 4), []).append(r)
    return {k: summarize(v) for k, v in sorted(groups.items()) if len(v) >= 5}


def city_stats(city, cfg):
    path, date = latest_raw(city["slug"])
    raw, rows = clean(path, cfg)
    excluded = set(cfg["excluded_districts"])
    by_q = {}
    for r in rows:
        if r["district"] not in excluded:
            by_q.setdefault(r["district"], []).append(r)
    ranked, small = [], []
    for name, qrows in by_q.items():
        q = summarize(qrows)
        q.update(name=name, slug=slugify(name), rows=qrows)
        (ranked if q["n"] >= cfg["min_listings_per_quartier"] else small).append(q)
    ranked.sort(key=lambda q: -q["median"])
    small.sort(key=lambda q: (-q["n"], q["name"]))
    for i, q in enumerate(ranked):
        q["rank"] = i + 1
    stats = summarize(rows)
    stats.update(raw=raw, date=date, rows=rows, ranked=ranked, small=small)
    stats["changes"] = changes_since_previous(city, cfg, stats)
    return stats


# Une variation de médiane n'est publiée qu'au-delà de ce nombre d'annonces dans chaque relevé :
# en dessous, quelques annonces entrées ou sorties suffisent à la déplacer.
MIN_LISTINGS_FOR_TREND = 15


def changes_since_previous(city, cfg, st):
    """Ce qui a changé depuis le relevé précédent : annonces nouvelles, retirées, prix modifiés.

    Les annonces sont reliées d'un relevé à l'autre par leur identifiant Sarouty. Seules les annonces
    exploitables du relevé courant comptent comme nouvelles ; une annonce retirée est une annonce
    exploitable du relevé précédent qui n'apparaît plus du tout.
    """
    prev_path, prev_date = previous_raw(city["slug"], st["date"])
    if not prev_path:
        return None
    prev_all = read_listings(prev_path, cfg)
    prev_ids = {r["id"] for r in prev_all if r["id"]}
    prev_kept = {r["id"]: r for r in prev_all if r["kept"] and r["id"]}
    cur_path, _ = latest_raw(city["slug"])
    cur_ids = {r["id"] for r in read_listings(cur_path, cfg) if r["id"]}
    excluded = set(cfg["excluded_districts"])

    def scope(rows, district):
        return [r for r in rows if district is None or r["district"] == district]

    def block(district=None):
        cur = scope(st["rows"], district)
        prev = scope(list(prev_kept.values()), district)
        new = [r for r in cur if r["id"] and r["id"] not in prev_ids]
        gone = [r for r in prev if r["id"] not in cur_ids]
        cuts, rises = [], []
        for r in cur:
            p = prev_kept.get(r["id"])
            if p and p["price"] and r["price"] and r["price"] != p["price"]:
                move = {"id": r["id"], "district": r["district"], "surface": r["surface"], "bedrooms": r["bedrooms"],
                        "before": p["price"], "after": r["price"], "pct": r["price"] / p["price"] - 1}
                (cuts if r["price"] < p["price"] else rises).append(move)
        cuts.sort(key=lambda m: m["pct"])
        trend = None
        if len(cur) >= MIN_LISTINGS_FOR_TREND and len(prev) >= MIN_LISTINGS_FOR_TREND:
            before = statistics.median(r["ppm2"] for r in prev)
            trend = {"before": round(before), "after": round(statistics.median(r["ppm2"] for r in cur)),
                     "pct": statistics.median(r["ppm2"] for r in cur) / before - 1}
        return {"new": len(new), "gone": len(gone), "cuts": cuts, "rises": rises, "trend": trend}

    days = (datetime.date.fromisoformat(st["date"]) - datetime.date.fromisoformat(prev_date)).days
    out = block()
    out.update(prev_date=prev_date, days=days,
               quartiers={q["name"]: block(q["name"]) for q in st["ranked"] if q["name"] not in excluded})
    return out


# ---------- mise en forme ----------

def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def n(v):
    return f"{round(v):,}".replace(",", NBSP)


def millions(v):
    return f"{v / 1e6:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " M"


def pct(v):
    p = round(v * 100)
    return ("+" if p >= 0 else "−") + f"{abs(p)}{NBSP}%"


def ordinal(i):
    return "1<sup>er</sup>" if i == 1 else f"{i}<sup>e</sup>"


def long_date(d):
    y, m, day = map(int, d.split("-"))
    return f"{'1er' if day == 1 else day} {MONTHS[m - 1]} {y}"


def short_month(d):
    y, m, _ = map(int, d.split("-"))
    return f"{MONTHS_SHORT[m - 1]} {y}"


def prep(name, cfg):
    p = cfg["district_prepositions"].get(name)
    if p:
        return p
    if name.startswith("Les "):
        return "aux " + name[4:]
    if name.startswith("Le "):
        return "au " + name[3:]
    return "à " + name


def named(name, cfg):
    p = prep(name, cfg)
    for a, b in (("aux ", "les "), ("au ", "le "), ("à la ", "la "), ("à ", "")):
        if p.startswith(a):
            return b + p[len(a):]
    return name


def of_form(name, cfg):
    """« de l'Hivernage », « des Princesses », « du Maarif », « de Guéliz »."""
    p = prep(name, cfg)
    for a, b in (("aux ", "des "), ("au ", "du "), ("à la ", "de la "), ("à l'", "de l'"), ("à ", "de ")):
        if p.startswith(a):
            return b + p[len(a):]
    return "de " + p


def cap(s):
    return s[:1].upper() + s[1:]


def e(s):
    return html.escape(str(s), quote=True)


# ---------- gabarits ----------

def read_template(name):
    with open(os.path.join(ROOT, "scripts", "templates", name), encoding="utf8") as f:
        return f.read()


def head(title, description, path, ld, og_type="article"):
    url = SITE + path
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#ffffff">
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{url}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:locale" content="fr_FR">
  <meta property="og:site_name" content="Atlas Data">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:image" content="{SITE}/og-image.png">
  <meta property="og:url" content="{url}">
  <meta name="twitter:card" content="summary_large_image">
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/favicon-48.png" sizes="48x48" type="image/png">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&family=Roboto:ital,wght@0,400..800;1,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/site.css">
  <link rel="stylesheet" href="/assets/components.css">
  <script src="/assets/components.js" defer></script>
</head>
<body>
"""


def breadcrumb_ld(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": SITE + path}
        for i, (name, path) in enumerate(items)]}


def dataset_ld(name, description, path, place, date):
    return {"@type": "Dataset", "name": name, "description": description, "url": SITE + path,
            "temporalCoverage": date, "spatialCoverage": {"@type": "Place", "name": place},
            "creator": {"@type": "Organization", "name": "Atlas Data", "url": SITE + "/"},
            "isAccessibleForFree": True, "inLanguage": "fr"}


def crumbs(items):
    parts = [f'<a href="{p}">{e(t)}</a>' for t, p in items[:-1]]
    parts.append(f'<span aria-current="page">{e(items[-1][0])}</span>')
    return '<nav class="crumbs" aria-label="Fil d\'Ariane">' + '<span aria-hidden="true">/</span>'.join(parts) + "</nav>"


def rank_list(city, ranked, city_median, current=None):
    """Classement en barres, avec un trait vertical à la médiane de la ville."""
    top = ranked[0]["median"]
    ref = f'<b class="ref" style="left:{min(city_median / top * 100, 100):.1f}%"></b>'
    items = []
    for q in ranked:
        me = q is current
        items.append(f'<li class="{"me" if me else ""}"><a href="/{city["slug"]}/{q["slug"]}/"'
                     f'{" aria-current=\"page\"" if me else ""}><span>{e(q["name"])}</span>'
                     f'<span class="bar"><i style="width:{q["median"] / top * 100:.1f}%"></i>{ref}</span>'
                     f'<span class="v">{n(q["median"])}</span></a></li>')
    return f'<ul class="rank{" has-me" if current else ""}">' + "".join(items) + "</ul>"


def rank_legend(city, city_median):
    return (f'<span class="rank-legend"><b class="ref-key" aria-hidden="true"></b>'
            f'médiane de {e(city["name"])} ({n(city_median)} MAD/m²)</span>')


def strip_chart(q, scale):
    lanes = [0, -14, 14, -28, 28, -42, 42, -56, 56]
    last = {}
    pts = []
    for r in sorted(q["rows"], key=lambda r: r["ppm2"]):
        x = min(r["ppm2"] / scale * 100, 99.5)
        lane = next((l for l in lanes if x - last.get(l, -10) >= 1.6), lanes[len(pts) % len(lanes)])
        last[lane] = x
        out = " out" if r["ppm2"] > scale else ""
        pts.append(f'<i class="pt{out}" style="--x:{x:.2f}%;--y:{lane}px"></i>')
    ticks = "".join(f'<span style="left:{i * 25}%">{n(scale * i / 4)}</span>' for i in range(5))
    label = (f'Prix au m² des {q["n"]} annonces {e(q["prep"])}, de {n(q["min"])} à {n(q["max"])} MAD, '
             f'médiane {n(q["median"])} MAD.')
    over = sum(1 for r in q["rows"] if r["ppm2"] > scale)
    foot = "Chaque point est une annonce, placée selon son prix demandé, en MAD/m²."
    if over:
        foot += f" {over} annonce{'s' if over > 1 else ''} au-delà de {n(scale)} MAD/m² {'sont placées' if over > 1 else 'est placée'} en bord de graphique."
    return (f'<div class="card" role="img" aria-label="{label}"><div class="strip" aria-hidden="true">'
            f'<div class="axis-line"></div>{"".join(pts)}'
            f'<div class="med" style="--x:{min(q["median"] / scale * 100, 99.5):.2f}%"><span>Médiane {n(q["median"])}</span></div></div>'
            f'<div class="strip-scale" aria-hidden="true"><div class="ticks">{ticks}</div></div>'
            f'<p class="card-foot" aria-hidden="true">{foot}</p></div>')


def budget_rows(rows, median, budgets):
    out = []
    for b in budgets:
        k = sum(1 for r in rows if r["price"] <= b)
        out.append(f'<tr><th scope="row">{n(b)}</th><td class="num">≈ {n(b / median)} m²</td>'
                   f'<td class="num">{k} sur {len(rows)}</td></tr>')
    return "".join(out)


def bedroom_table(groups):
    label = {1: "1 chambre", 2: "2 chambres", 3: "3 chambres", 4: "4 chambres et plus"}
    rows = "".join(f'<tr><th scope="row">{label[k]}</th><td class="num">{g["n"]}</td>'
                   f'<td class="num">{n(g["median_price"])}</td><td class="num">{n(g["median"])}</td></tr>'
                   for k, g in groups.items())
    return ('<div class="card"><div class="table-wrap"><table><caption class="sr-only">Prix médians demandés par nombre de chambres</caption>'
            '<thead><tr><th scope="col">Type</th><th scope="col" class="num">Annonces</th>'
            '<th scope="col" class="num">Prix médian (MAD)</th><th scope="col" class="num">MAD/m²</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div><p class="card-foot">Types comptant au moins 5 annonces.</p></div>')


def plural(k, one, many, zero=None):
    if k == 0 and zero:
        return zero
    return f"{k} {one if k == 1 else many}"


def since(ch):
    """« depuis le 17 octobre » : date du relevé précédent, sans l'année."""
    return f"depuis le {long_date(ch['prev_date']).rsplit(' ', 1)[0]}"


def between(ch, date):
    """« Entre les relevés du 17 et du 19 octobre 2026, à 2 jours d'intervalle »."""
    a, b = long_date(ch["prev_date"]), long_date(date)
    if a.rsplit(" ", 1)[1] == b.rsplit(" ", 1)[1]:
        a = a.rsplit(" ", 1)[0]
        if a.split(" ", 1)[1] == b.split(" ", 2)[1]:
            a = a.split(" ", 1)[0]
    gap = "une semaine" if ch["days"] == 7 else f"{ch['days']} jour{'s' if ch['days'] > 1 else ''}"
    return f"Entre les relevés du {a} et du {b}, à {gap} d'intervalle"


def change_summary(b):
    """« 7 nouvelles annonces, 2 retirées et aucune baisse de prix »."""
    return (f"{plural(b['new'], 'nouvelle annonce', 'nouvelles annonces', 'aucune nouvelle annonce')}, "
            f"{plural(b['gone'], 'retirée', 'retirées', 'aucune retirée')} et "
            f"{plural(len(b['cuts']), 'baisse de prix', 'baisses de prix', 'aucune baisse de prix')}")


def trend_text(t, where):
    if not t:
        return ""
    if t["before"] == t["after"]:
        return f" La médiane {where} est inchangée, à {n(t['after'])} MAD/m²."
    return (f" La médiane {where} passe de {n(t['before'])} à {n(t['after'])} MAD/m² "
            f"({pct(t['pct'])}).")


def since_line(ch, b, where, anchor=None):
    """Ligne courte sous les chiffres clés d'une page ville ou quartier."""
    if not ch:
        return ""
    more = f' <a href="{anchor}">Le détail</a>' if anchor else ""
    return (f'\n        <p class="since"><strong>{cap(since(ch))} :</strong> {change_summary(b)}.'
            f'{trend_text(b["trend"], where)}{more}</p>')


def bed_label(b):
    return f"{b} ch." if b else "appartement"


def changes_block(city, st):
    ch = st["changes"]
    if not ch:
        return ""
    cname = city["name"]
    tiles = (f'<div class="moves">'
             f'<div><strong>{ch["new"]}</strong><span>{"nouvelle annonce" if ch["new"] == 1 else "nouvelles annonces"}</span></div>'
             f'<div><strong>{ch["gone"]}</strong><span>{"annonce retirée" if ch["gone"] == 1 else "annonces retirées"}</span></div>'
             f'<div class="down"><strong>{len(ch["cuts"])}</strong><span>{"baisse de prix" if len(ch["cuts"]) == 1 else "baisses de prix"}</span></div>'
             f'<div class="up"><strong>{len(ch["rises"])}</strong><span>{"hausse de prix" if len(ch["rises"]) == 1 else "hausses de prix"}</span></div>'
             f'</div>')
    if ch["cuts"]:
        rows = "".join(f'<tr><th scope="row">{e(m["district"] or "Non précisé")}</th><td>{bed_label(m["bedrooms"])}, {n(m["surface"])} m²</td>'
                       f'<td class="num"><s>{n(m["before"])}</s> {n(m["after"])}</td><td class="num down">{pct(m["pct"])}</td></tr>'
                       for m in ch["cuts"][:6])
        more = len(ch["cuts"]) - 6
        cuts = ('<div class="table-wrap"><table class="cuts-table"><caption class="sr-only">Baisses de prix entre les deux relevés</caption>'
                '<thead><tr><th scope="col">Quartier</th><th scope="col">Bien</th><th scope="col" class="num">Prix demandé (MAD)</th><th scope="col" class="num">Écart</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div>'
                + (f'<p class="card-foot">Et {plural(more, "autre baisse", "autres baisses")} : la liste complète, avec le lien de chaque annonce, est dans la version Pro.</p>' if more > 0 else
                   '<p class="card-foot">Le lien de chaque annonce est dans la version Pro.</p>'))
    else:
        cuts = f'<p class="card-foot">Aucune annonce n\'a baissé son prix {since(ch)}.</p>'
    active = [(q, b) for q, b in ch["quartiers"].items() if b["new"] or b["gone"] or b["cuts"] or b["rises"]]
    by_q = ""
    if active:
        rows = "".join(f'<tr><th scope="row"><a href="/{city["slug"]}/{slugify(q)}/">{e(q)}</a></th><td class="num">{b["new"]}</td>'
                       f'<td class="num">{b["gone"]}</td><td class="num">{len(b["cuts"])}</td></tr>' for q, b in active)
        by_q = ('<div class="card"><div class="table-wrap"><table><caption class="sr-only">Mouvements par quartier</caption>'
                '<thead><tr><th scope="col">Quartier</th><th scope="col" class="num">Nouvelles</th><th scope="col" class="num">Retirées</th>'
                f'<th scope="col" class="num">Baisses</th></tr></thead><tbody>{rows}</tbody></table></div>'
                '<p class="card-foot">Quartiers classés ayant au moins un mouvement.</p></div>')
    return f"""
    <section class="block" id="evolution" aria-labelledby="evolution-title">
      <div class="shell block-grid">
        <div class="block-copy">
          <h2 id="evolution-title">Ce qui a changé {e(since(ch))}</h2>
          <p>{between(ch, st['date'])} : {change_summary(ch)}.{trend_text(ch['trend'], 'de ' + e(cname))}</p>
          <p>Les annonces sont suivies d'un relevé à l'autre par leur référence Sarouty. Une annonce retirée peut avoir été vendue, louée ou simplement dépubliée. Une variation de médiane reflète aussi les annonces qui entrent et sortent du relevé : ce n'est pas une évolution des prix de vente.</p>
        </div>
        <div class="moves-col">
          <div class="card">{tiles}{cuts}</div>
          {by_q}
        </div>
      </div>
    </section>
"""


def city_header(city):
    """En-tête des pages d'une ville : « Calculer mon budget » mène au calculateur de cette ville."""
    return read_template("header.html").replace('href="/marrakech/#budget"', f'href="/{city["slug"]}/#budget"')


def footer(cfg):
    return set_city_nav(read_template("footer.html"), cfg)


def city_nav(cfg):
    items = "".join(f'<li><a href="/{c["slug"]}/">{e(c["name"])}</a></li>' for c in cfg["cities"])
    return f'<nav aria-labelledby="f-quartiers"><h2 id="f-quartiers">Prix par ville</h2><ul>{items}</ul></nav>'


def set_city_nav(page, cfg):
    page = re.sub(r'<nav aria-labelledby="f-quartiers">.*?</nav>', lambda m: city_nav(cfg), page, count=1, flags=re.S)
    items = "".join(f'<li><a href="/{c["slug"]}/">{e(c["name"])}</a></li>' for c in cfg["cities"])
    return re.sub(r'(<nav aria-labelledby="adf-q"><h2 id="adf-q">)[^<]*(</h2><ul>).*?(</ul></nav>)',
                  lambda m: m.group(1) + "Prix par ville" + m.group(2) + items + m.group(3), page, count=1, flags=re.S)


# ---------- pages ----------

def quartier_page(city, st, q, cfg):
    name, cname, date = q["name"], city["name"], st["date"]
    path = f"/{city['slug']}/{q['slug']}/"
    ranked = st["ranked"]
    q["prep"] = prep(name, cfg)
    delta = q["median"] / st["median"] - 1
    k1m = sum(1 for r in q["rows"] if r["price"] <= 1_000_000)
    budgets = [1_000_000, 1_500_000, 2_000_000, 3_000_000] + ([5_000_000] if q["median_price"] > 2_500_000 else [])
    scale = max(40_000, math.ceil(sorted(r["ppm2"] for r in st["rows"])[int(len(st["rows"]) * 0.95)] / 20_000) * 20_000)
    groups = bedroom_groups(q["rows"])
    position = ("le quartier le plus cher" if q["rank"] == 1 else
                f"le {ordinal(q['rank'])} quartier le plus cher") + f" de {cname}"
    if len(ranked) == 1:
        lede_rank = f"{name} est le seul quartier de {cname} à compter au moins {cfg['min_listings_per_quartier']} annonces dans ce relevé. "
    else:
        lede_rank = f"{name} est {position} parmi les {len(ranked)} quartiers qui comptent au moins {cfg['min_listings_per_quartier']} annonces. "
    lede = (f"{lede_rank}Voici ce que disent les prix demandés de {q['n']} annonces d'appartements à vendre, "
            f"relevées le {long_date(date)}.")

    title = f"Prix m² {name}, {cname} : {n(q['median'])} MAD/m² ({short_month(date)})"
    desc = (f"Prix au m² des appartements à vendre {q['prep']} ({cname}) : {n(q['median'])} MAD/m² en médiane "
            f"sur {q['n']} annonces. Budget et comparaison des quartiers.")
    ld = {"@context": "https://schema.org", "@graph": [
        breadcrumb_ld([("Accueil", "/"), (f"Prix au m² à {cname}", f"/{city['slug']}/"), (f"Prix au m² {q['prep']}", path)]),
        dataset_ld(f"Prix demandés des appartements à vendre {q['prep']}, {cname} ({MONTHS[int(date[5:7]) - 1]} {date[:4]})",
                   f"Prix médian demandé au m², répartition des prix et surface accessible selon le budget, calculés sur {q['n']} annonces "
                   f"d'appartements à vendre {q['prep']} ({cname}) relevées sur Sarouty le {long_date(date)}.",
                   path, f"{name}, {cname}, Maroc", date)]}

    if k1m == 0:
        budget_text = f"Mais aucune annonce ne demandait 1 million de MAD ou moins le {long_date(date)}."
    else:
        budget_text = f"{k1m} annonce{'s' if k1m > 1 else ''} sur {q['n']} demandai{'ent' if k1m > 1 else 't'} 1 million de MAD ou moins le {long_date(date)}."

    if groups:
        top_k, top_g = max(groups.items(), key=lambda kv: kv[1]["n"])
        lbl = {1: "le 1 chambre", 2: "le 2 chambres", 3: "le 3 chambres", 4: "le 4 chambres et plus"}[top_k]
        bed_title = f"Le type le plus courant&nbsp;: {lbl}"
        bed_text = (f"{cap(BED_PLURAL[top_k])} représentent {top_g['n']} annonce{'s' if top_g['n'] > 1 else ''} sur {q['n']}. "
                    f"Prix médian demandé : {n(top_g['median_price'])} MAD pour {n(top_g['median_surface'])} m², "
                    f"soit {n(top_g['median'])} MAD/m².")
        bed_block = bedroom_table(groups)
    else:
        bed_title = "Selon le nombre de chambres"
        bed_text = "Aucun type de bien ne compte au moins 5 annonces dans ce quartier : trop peu pour une médiane par nombre de chambres."
        bed_block = "<div></div>"

    if len(ranked) > 1:
        i = q["rank"] - 1
        neighbours = []
        if i > 0:
            neighbours.append(f"{named(ranked[i - 1]['name'], cfg)} ({n(ranked[i - 1]['median'])} MAD/m²)")
        if i < len(ranked) - 1:
            neighbours.append(f"{named(ranked[i + 1]['name'], cfg)} ({n(ranked[i + 1]['median'])} MAD/m²)")
        where = (f"entre {neighbours[0]} et {neighbours[1]}" if len(neighbours) == 2 else
                 f"devant {neighbours[0]}" if i == 0 else f"derrière {neighbours[0]}")
        cmp_text = (f"{name} est {'le quartier le plus cher' if i == 0 else 'le ' + ordinal(q['rank']) + ' quartier le plus cher'} "
                    f"des {len(ranked)}, {where}. Son prix médian demandé est {pct(delta)} par rapport à la médiane de {cname}.")
    else:
        cmp_text = f"Son prix médian demandé est {pct(delta)} par rapport à l'ensemble de {cname} ({n(st['median'])} MAD/m²)."

    sample = (f'\n        <p class="sample-note">Avec {q["n"]} annonces, ces chiffres donnent un ordre de grandeur : '
              f'une seule annonce peut déplacer sensiblement la médiane.</p>') if q["n"] < 15 else ""

    faq = [
        (f"Quel est le prix au m² d'un appartement {q['prep']} ?",
         f"Au {long_date(date)}, le prix médian demandé est de {n(q['median'])} MAD/m² sur {q['n']} annonces d'appartements à vendre, "
         f"soit {pct(delta)} par rapport à la médiane de {cname} ({n(st['median'])} MAD/m²)."),
        (f"Combien coûte un appartement {q['prep']} ?",
         f"Le prix médian demandé est de {n(q['median_price'])} MAD, pour une surface médiane de {n(q['median_surface'])} m²."),
        (f"Que peut-on acheter avec 1 million de dirhams {q['prep']} ?",
         f"Au prix médian demandé, environ {n(1_000_000 / q['median'])} m². {budget_text}"),
        ("Ces prix sont-ils des prix de vente ?",
         "Non. Ce sont les prix demandés dans les annonces, avant négociation. Ils décrivent l'offre publiée, pas le prix final signé chez le notaire."),
    ]
    faq_html = "".join(f"<details><summary>{e(qq)}</summary><p>{e(a)}</p></details>" for qq, a in faq)
    mail = "mailto:othman@atlas-data.fr?subject=" + "Acc%C3%A8s%20Pro%20Atlas%20Data%20-%20" + slugify(name)

    return head(title, desc, path, ld) + city_header(city) + f"""  <main id="main">
    <section class="page-hero" aria-labelledby="page-title">
      <div class="shell">
        {crumbs([("Accueil", "/"), (cname, f"/{city['slug']}/"), (name, path)])}
        <h1 id="page-title">Prix au m² {e(q['prep'])}, {e(cname)}</h1>
        <p class="hero-lede">{lede}</p>
        <div class="facts">
          <div class="hl"><span>Prix médian demandé</span><strong>{n(q['median'])}</strong><small>MAD/m²</small></div>
          <div><span>Annonces analysées</span><strong>{q['n']}</strong><small>appartements à vendre</small></div>
          <div><span>Écart à la médiane de {e(cname)}</span><strong>{pct(delta)}</strong><small>ville : {n(st['median'])} MAD/m²</small></div>
          <div><span>Prix médian d'un appartement</span><strong>{millions(q['median_price'])}</strong><small>MAD, pour {n(q['median_surface'])} m² en médiane</small></div>
        </div>{since_line(st['changes'], st['changes']['quartiers'].get(name), 'du quartier') if st['changes'] and st['changes']['quartiers'].get(name) else ''}{sample}
      </div>
    </section>

    <section class="block" aria-labelledby="budget-title">
      <div class="shell block-grid">
        <div class="block-copy">
          <h2 id="budget-title">Que permet votre budget {e(q['prep'])}&nbsp;?</h2>
          <p>Au prix médian demandé, 1 million de MAD correspond à environ {n(1_000_000 / q['median'])} m². {budget_text}</p>
          <a class="btn btn-primary" href="/{city['slug']}/">Comparer les quartiers de {e(cname)}</a>
        </div>
        <div class="card">
          <div class="table-wrap"><table>
            <caption class="sr-only">Surface et nombre d'annonces {e(q['prep'])} selon le budget</caption>
            <thead><tr><th scope="col">Budget (MAD)</th><th scope="col" class="num">Surface</th><th scope="col" class="num">Annonces</th></tr></thead>
            <tbody>{budget_rows(q['rows'], q['median'], budgets)}</tbody>
          </table></div>
          <p class="card-foot">Surface au prix médian demandé ; annonces dont le prix demandé est inférieur ou égal au budget. <a href="/dashboard.html?{e(urlencode({'ville': city['slug'], 'quartier': name}))}">Voir les annonces {e(q['prep'])} dans le dashboard</a></p>
        </div>
      </div>
    </section>

    <section class="block" aria-labelledby="repartition-title">
      <div class="shell block-grid">
        <div class="block-copy"><h2 id="repartition-title">La répartition des prix</h2><p>{e(cap(q['prep']))}, les prix demandés vont de {n(q['min'])} à {n(q['max'])} MAD/m². Deux appartements d'un même quartier peuvent afficher des prix au m² très différents : l'adresse seule ne suffit pas à situer un bien.</p></div>
        {strip_chart(q, scale)}
      </div>
    </section>

    <section class="block" aria-labelledby="chambres-title">
      <div class="shell block-grid">
        <div class="block-copy"><h2 id="chambres-title">{bed_title}</h2><p>{bed_text}</p></div>
        {bed_block}
      </div>
    </section>

    <section class="block" aria-labelledby="comparaison-title">
      <div class="shell block-grid">
        <div class="block-copy">
          <h2 id="comparaison-title">{e(name)} face aux autres quartiers</h2>
          <p>{cmp_text}</p>
          <a class="btn btn-ghost" href="/{city['slug']}/">Tous les quartiers de {e(cname)}</a>
        </div>
        <div class="card">
          {rank_list(city, ranked, st['median'], q)}
          <p class="card-foot">Prix médian demandé en MAD/m², quartiers d'au moins {cfg['min_listings_per_quartier']} annonces. {rank_legend(city, st['median'])}</p>
        </div>
      </div>
    </section>

    <section class="block" id="questions" aria-labelledby="faq-title">
      <div class="shell faq-grid">
        <h2 id="faq-title">{e(name)} : vos questions</h2>
        <div class="faq-list">{faq_html}</div>
      </div>
    </section>

    <section class="pro-band" aria-labelledby="pro-title">
      <div class="shell">
        <div><h2 id="pro-title">Vous êtes une agence {e(q['prep'])}&nbsp;?</h2><p>Chaque lundi, toutes les annonces Sarouty de {e(cname)} dans un fichier Excel : titre, agence, prix, surface, lien, et les nouvelles annonces de la semaine signalées. 29 € HT par mois, sans engagement.</p></div>
        <div class="pro-actions"><a class="btn btn-primary" href="/exemples/atlas-data-pro-exemple-gueliz.xlsx" download>Télécharger un exemple</a><a class="btn btn-ghost" data-pro-contact data-ville="{e(cname)}" href="{mail}">Demander l'accès Pro</a></div>
      </div>
    </section>

    <section class="block" aria-label="Méthode">
      <div class="shell">
        <p class="note"><strong>Méthode.</strong> Relevé du {long_date(date)} sur Sarouty : {q['n']} annonces d'appartements à vendre {e(q['prep'])}, parmi {st['n']} annonces exploitables à {e(cname)}. Prix au m² = prix demandé / surface publiée. Les prix demandés ne sont pas des prix de vente, et le relevé ne couvre pas l'ensemble du marché. Données mises à jour chaque semaine. <a href="/#methode">En savoir plus sur la méthode</a>.</p>
      </div>
    </section>
  </main>

""" + footer(cfg)


# ---------- pages villes : calculateur, graphique, constats, FAQ ----------

CALC_BUDGET = 1_000_000
CALC_MANY_QUARTIERS = 10   # boutons de quartier au-delà desquels le mobile affiche un menu
CALC_CMP_VISIBLE = 8       # quartiers visibles dans « Le même budget dans les autres quartiers »


def city_calc_section(city, st, cfg):
    """Calculateur de surface selon le budget (#budget), rendu pour 1 million de MAD et le quartier le plus cher.
    assets/city.js le met à jour quand le visiteur change le budget ou le quartier."""
    ranked, cname = st["ranked"], city["name"]
    calc = calc_city(city, st, cfg)
    calc["slug"] = city["slug"]
    first = ranked[0]["name"] if ranked else "__all"
    d = calc["data"][first]
    count = sum(1 for p in d["prices"] if p <= CALC_BUDGET)
    where = "" if first == "__all" else " dans ce quartier"
    if count:
        real = (f'<p class="result-real is-some" id="result-real"><strong>{plural(count, "annonce", "annonces")} à ce prix. </strong>'
                f'Sur les {d["n"]} annonces{" de la ville" if first == "__all" else " de ce quartier"}, {count} '
                f'{"demandaient" if count > 1 else "demandait"} {n(CALC_BUDGET)} MAD ou moins le {calc["short"]}.</p>')
    else:
        real = (f'<p class="result-real is-none" id="result-real"><strong>Aucune annonce à ce prix. </strong>'
                f'Ce chiffre est théorique : la moins chère{where} demandait {n(d["prices"][0])} MAD le {calc["short"]}.</p>')
    chips = "".join(f'<label class="chip"><input type="radio" name="quartier" value="{e(q["name"])}"{" checked" if i == 0 else ""}>'
                    f'<span>{e(q["name"])}</span></label>' for i, q in enumerate(ranked))
    chips += (f'<label class="chip"><input type="radio" name="quartier" value="__all"{"" if ranked else " checked"}>'
              '<span>Toute la ville</span></label>')
    # Au-delà de CALC_MANY_QUARTIERS, un menu déroulant remplace les boutons sur mobile.
    many = len(ranked) + 1 > CALC_MANY_QUARTIERS
    select = ""
    if many:
        opts = "".join(f'<option value="{e(q["name"])}"{" selected" if i == 0 else ""}>{e(q["name"])}</option>' for i, q in enumerate(ranked))
        select = (f'<select class="quartier-select" id="quartier-select" aria-label="Quartier">{opts}'
                  '<option value="__all">Toute la ville</option></select>')
    cmp = ""
    if len(ranked) >= 2:
        top_m2 = max(CALC_BUDGET / q["median"] for q in ranked)
        lis = [f'<li><button type="button" data-q="{e(q["name"])}" aria-pressed="{"true" if i == 0 else "false"}">'
               f'<span>{e(q["name"])}</span><span class="cmp-bar"><i style="width:{CALC_BUDGET / q["median"] / top_m2 * 100:.1f}%"></i></span>'
               f'<span class="cmp-val">{n(CALC_BUDGET / q["median"])} m²</span></button></li>' for i, q in enumerate(ranked)]
        # Les CALC_CMP_VISIBLE premiers quartiers restent visibles, les autres sont repliés.
        more = ""
        if len(lis) > CALC_CMP_VISIBLE + 2:
            rest = len(lis) - CALC_CMP_VISIBLE
            more = (f'<details class="cmp-more"><summary>Voir les {rest} autres quartiers</summary>'
                    f'<ul class="cmp">{"".join(lis[CALC_CMP_VISIBLE:])}</ul></details>')
            lis = lis[:CALC_CMP_VISIBLE]
        cmp = (f'<h3 id="cmp-title">Le même budget dans les autres quartiers</h3><ul class="cmp" id="cmp">{"".join(lis)}</ul>{more}')
    data = json.dumps({k: calc[k] for k in ("slug", "name", "short", "quartiers", "data")},
                      ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""
    <section class="block" id="budget" aria-labelledby="budget-title">
      <div class="shell block-grid">
        <div class="block-copy">
          <h2 id="budget-title">Combien de m² pour votre budget à {e(cname)}&nbsp;?</h2>
          <p>Entrez un budget et choisissez un quartier : le calcul utilise le prix médian demandé au m² des annonces du relevé du {long_date(st['date'])}. Ce sont des prix demandés, pas des prix de vente.</p>
        </div>
        <div class="calc" role="region" aria-label="Calculateur de surface selon le budget">
          <div class="calc-inputs">
            <label class="field-label" for="budget-input">Votre budget</label>
            <div class="budget"><input id="budget-input" type="text" inputmode="numeric" autocomplete="off" value="{n(CALC_BUDGET)}"><span>MAD</span></div>
            <div class="presets" role="group" aria-label="Budgets fréquents">
              <button type="button" data-budget="500000" aria-pressed="false">500 000</button><button type="button" data-budget="1000000" aria-pressed="true">1 000 000</button><button type="button" data-budget="2000000" aria-pressed="false">2 000 000</button><button type="button" data-budget="3000000" aria-pressed="false">3 000 000</button>
            </div>
            <fieldset class="quartiers{' many' if many else ''}"><legend class="field-label">Quartier</legend><div class="chips" id="chips">{chips}</div>{select}</fieldset>
          </div>
          <div class="calc-result" aria-live="polite">
            <p class="result-lead" id="result-lead">{e(d['prep'])}, ce budget correspond à environ</p>
            <p class="result-m2" id="result-m2">{n(CALC_BUDGET / d['median'])}<small>&nbsp;m²</small></p>
            <p class="result-basis" id="result-basis">au prix médian demandé de {n(d['median'])} MAD/m², calculé sur {d['n']} annonces.</p>
            {real}
          </div>
          <div class="calc-compare">{cmp}<p class="calc-note" id="calc-note">{calc['note']}</p></div>
        </div>
      </div>
      <script type="application/json" id="calc-data">{data}</script>
    </section>
"""


def city_insights(st, cfg):
    """Constats calculés sur le relevé : écart de surface pour 1 million, dispersion du plus gros quartier, meublé."""
    ranked = st["ranked"]
    m2 = lambda v: round(CALC_BUDGET / v)
    out = []
    if len(ranked) >= 2:
        top, bot = ranked[0], ranked[-1]
        out.append((f"{m2(bot['median']) - m2(top['median'])} m² d'écart pour le même budget",
                    f"Pour 1 million de MAD, environ {m2(top['median'])} m² {top['prep']} contre {m2(bot['median'])} m² {bot['prep']}, au prix médian demandé."))
    if ranked:
        biggest = max(ranked, key=lambda q: q["n"])
        within = len(ranked) >= 2 and biggest["max"] - biggest["min"] > ranked[0]["median"] - ranked[-1]["median"]
        out.append(("Le bien compte plus que l'adresse",
                    f"{cap(biggest['prep'])}, les prix demandés vont de {n(biggest['min'])} à {n(biggest['max'])} MAD/m²"
                    + (", un écart plus large que celui entre les quartiers." if within else ".")))
    furn = [r["ppm2"] for r in st["rows"] if r["furnished"] == "1"]
    unfurn = [r["ppm2"] for r in st["rows"] if r["furnished"] == "0"]
    if len(furn) >= 5 and len(unfurn) >= 5:
        fp = round((statistics.median(furn) / statistics.median(unfurn) - 1) * 100)
        if fp >= 5:
            out.append(("Le meublé se paie", f"Les appartements meublés affichent un prix médian au m² supérieur d'environ {fp}{NBSP}% aux non meublés, sur les annonces qui le précisent."))
        elif fp <= -5:
            out.append(("Le meublé ne se paie pas", f"Les appartements meublés affichent un prix médian au m² inférieur d'environ {-fp}{NBSP}% aux non meublés, sur les annonces qui le précisent."))
        else:
            out.append(("Meublé ou non, peu d'écart", f"Le prix médian au m² des appartements meublés est proche de celui des non meublés ({pct(fp / 100)}), sur les annonces qui le précisent."))
    return "".join(f"<div><h3>{e(h)}</h3><p>{e(p)}</p></div>" for h, p in out)


def city_chart_section(city, st, cfg, rank_text):
    """Classement des quartiers en graphique (#analyse) : médianes, ou dispersion de chaque annonce."""
    ranked = st["ranked"]
    if not ranked:
        return f"""
    <section class="block" id="analyse" aria-labelledby="classement-title">
      <div class="shell"><div class="section-head"><h2 id="classement-title">Le classement des quartiers</h2><p>{rank_text}</p></div></div>
    </section>
"""
    over = [(q, sum(1 for r in q["rows"] if r["ppm2"] > HOME_SCALE)) for q in ranked]
    over = [(q, k) for q, k in over if k]
    foot = (f"Échelle de 0 à {n(HOME_SCALE)} MAD/m². Médiane de {e(city['name'])} : {n(st['median'])} MAD/m². "
            "En mode dispersion, chaque point est une annonce")
    if over:
        total = sum(k for _, k in over)
        parts = [f"{plural(k, 'annonce', 'annonces')} {of_form(q['name'], cfg)}" for q, k in over]
        foot += (f" ; {'les ' if total > 1 else 'l’'}{join_fr(parts)} au-delà de {n(HOME_SCALE)} MAD/m² "
                 f"{'sont placées' if total > 1 else 'est placée'} en bord de graphique.")
    else:
        foot += "."
    ticks = "".join(f'<span style="--x:{x:.2f}%">{n(HOME_SCALE * x / 100)}</span>' for x in (0, 25, 50, 75, 100))
    insights = city_insights(st, cfg)
    return f"""
    <section class="block" id="analyse" aria-labelledby="classement-title">
      <div class="shell">
        <div class="section-head"><h2 id="classement-title">Le classement des quartiers</h2><p>{rank_text}</p></div>
        <div class="chart" id="chart" data-mode="median">
          <div class="chart-top">
            <p>Passez en mode dispersion pour voir chaque annonce : l'écart à l'intérieur d'un quartier est souvent plus grand qu'entre deux quartiers.</p>
            <div class="switch" role="group" aria-label="Affichage du graphique">
              <button type="button" data-mode="median" aria-pressed="true">Prix médians</button>
              <button type="button" data-mode="distribution" aria-pressed="false">Dispersion</button>
            </div>
          </div>
          <div class="axis" aria-hidden="true"><span>Quartier</span><div class="axis-ticks">{ticks}</div><span class="axis-end">Médiane au m²</span></div>
          <ol class="mlist">
{home_mlist(city, st)}
          </ol>
          <div class="chart-foot">
            <p>{foot}</p>
            <div class="legend" aria-hidden="true"><span><i class="l-dot"></i>Annonce</span><span><i class="l-line"></i>Médiane</span></div>
          </div>
        </div>{f'''
        <div class="insights">{insights}</div>''' if insights else ''}
      </div>
    </section>
"""


def city_faq(city, st, cfg):
    """FAQ acheteur de la ville (#questions) et son JSON-LD FAQPage."""
    ranked, cname, date = st["ranked"], city["name"], st["date"]
    m2 = lambda v: round(CALC_BUDGET / v)
    minimum = cfg["min_listings_per_quartier"]
    q1 = f"Au {long_date(date)}, le prix médian demandé est de {n(st['median'])} MAD/m² sur les {st['n']} annonces d'appartements à vendre exploitables."
    if len(ranked) >= 2:
        top, bot = ranked[0], ranked[-1]
        q1 += (f" Il varie selon le quartier, de {n(bot['median'])} MAD/m² {bot['prep']} à {n(top['median'])} MAD/m² {top['prep']}, "
               f"parmi les quartiers comptant au moins {minimum} annonces.")
        q2 = (f"Parmi les quartiers comptant au moins {minimum} annonces, {named(top['name'], cfg)} affiche le prix médian demandé le plus élevé, "
              f"à {n(top['median'])} MAD/m², devant {join_fr([f'{named(q['name'], cfg)} ({n(q['median'])} MAD/m²)' for q in ranked[1:3]])}.")
    elif ranked:
        q2 = (f"Dans ce relevé, seul {named(ranked[0]['name'], cfg)} compte au moins {minimum} annonces, avec un prix médian demandé de "
              f"{n(ranked[0]['median'])} MAD/m². Les autres quartiers ont trop peu d'annonces pour une médiane fiable.")
    else:
        q2 = f"Aucun quartier de {cname} ne compte encore au moins {minimum} annonces dans ce relevé : trop peu pour comparer les médianes."
    q3 = (f"Au prix médian demandé, environ {join_fr([f'{m2(q['median'])} m² {q['prep']}' for q in ranked])}. "
          if ranked else f"Au prix médian demandé de la ville, environ {m2(st['median'])} m². ")
    q3 += "Les petites surfaces étant souvent plus chères au m², peu d'annonces affichent réellement ce prix dans les quartiers les plus chers."
    faq = [(f"Quel est le prix au m² d'un appartement à {cname} ?", q1),
           (f"Quel est le quartier le plus cher de {cname} ?", q2),
           (f"Que peut-on acheter avec 1 million de dirhams à {cname} ?", q3),
           ("Ces prix sont-ils des prix de vente ?",
            "Non. Ce sont les prix demandés dans les annonces, avant négociation. Ils décrivent l'offre publiée et ses écarts entre quartiers, pas le prix final signé chez le notaire.")]
    html_ = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in faq)
    ld = {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                                              for q, a in faq]}
    section = f"""
    <section class="block" id="questions" aria-labelledby="faq-title">
      <div class="shell faq-grid">
        <h2 id="faq-title">Prix immobilier à {e(cname)} : vos questions</h2>
        <div class="faq-list">{html_}</div>
      </div>
    </section>
"""
    return section, ld


def city_page(city, st, cfg):
    cname, date, ranked = city["name"], st["date"], st["ranked"]
    path = f"/{city['slug']}/"
    for q in ranked:
        q["prep"] = prep(q["name"], cfg)
    title = f"Prix au m² à {cname} par quartier ({short_month(date)}) - Atlas Data"
    if len(ranked) >= 2:
        span = f"de {n(ranked[-1]['median'])} MAD/m² {prep(ranked[-1]['name'], cfg)} à {n(ranked[0]['median'])} MAD/m² {prep(ranked[0]['name'], cfg)}"
    else:
        span = f"{n(st['median'])} MAD/m² en médiane"
    desc = (f"Prix au m² des appartements à {cname} : {span}, prix demandés sur {st['n']} annonces. "
            "Calculez la surface accessible avec votre budget.")
    ld = {"@context": "https://schema.org", "@graph": [
        breadcrumb_ld([("Accueil", "/"), (f"Prix au m² à {cname}", path)]),
        {"@type": "ItemList", "name": f"Prix au m² par quartier à {cname}", "itemListElement": [
            {"@type": "ListItem", "position": q["rank"], "name": f"Prix au m² {prep(q['name'], cfg)}",
             "url": f"{SITE}/{city['slug']}/{q['slug']}/"} for q in ranked]},
        dataset_ld(f"Prix des appartements à vendre à {cname} par quartier ({MONTHS[int(date[5:7]) - 1]} {date[:4]})",
                   f"Prix demandés de {st['n']} annonces d'appartements à vendre à {cname}, relevées sur Sarouty le {long_date(date)}. "
                   f"Médianes par quartier pour les secteurs comptant au moins {cfg['min_listings_per_quartier']} annonces.",
                   path, f"{cname}, Maroc", date)]}
    faq_section, faq_ld = city_faq(city, st, cfg)
    ld["@graph"].append(faq_ld)

    if ranked:
        facts_extra = (f'<div><span>Quartier le plus cher</span><strong>{n(ranked[0]["median"])}</strong><small>MAD/m², {e(ranked[0]["name"])}</small></div>'
                       + (f'<div><span>Quartier le moins cher</span><strong>{n(ranked[-1]["median"])}</strong><small>MAD/m², {e(ranked[-1]["name"])}</small></div>'
                          if len(ranked) > 1 else
                          f'<div><span>Prix médian d\'un appartement</span><strong>{millions(st["median_price"])}</strong><small>MAD, pour {n(st["median_surface"])} m² en médiane</small></div>'))
    else:
        facts_extra = ""
    if len(ranked) >= 2:
        spread = ranked[0]["median"] / ranked[-1]["median"] - 1
        rank_text = (f"Entre {named(ranked[0]['name'], cfg)} et {named(ranked[-1]['name'], cfg)}, le prix médian demandé au m² varie de {round(spread * 100)}{NBSP}%. "
                     f"Seuls les quartiers comptant au moins {cfg['min_listings_per_quartier']} annonces sont classés : en dessous, une seule annonce suffirait à déplacer la médiane.")
    elif ranked:
        rank_text = (f"Dans ce relevé, seul {ranked[0]['name']} compte au moins {cfg['min_listings_per_quartier']} annonces. "
                     f"Les autres quartiers de {cname} sont listés plus bas avec leur nombre d'annonces, sans médiane.")
    else:
        rank_text = f"Aucun quartier de {cname} ne compte encore au moins {cfg['min_listings_per_quartier']} annonces dans ce relevé."

    table_rows = "".join(
        f'<tr><th scope="row"><a href="/{city["slug"]}/{q["slug"]}/">{e(q["name"])}</a></th><td class="num">{n(q["median"])}</td>'
        f'<td class="num">≈ {n(1_000_000 / q["median"])} m²</td><td class="num">{q["n"]}</td></tr>' for q in ranked)
    table_rows += (f'<tr><th scope="row">Toute la ville</th><td class="num">{n(st["median"])}</td>'
                   f'<td class="num">≈ {n(1_000_000 / st["median"])} m²</td><td class="num">{st["n"]}</td></tr>')
    small = [q for q in st["small"] if q["n"] >= 3]
    small_block = ""
    if small:
        lis = "".join(f"<li>{e(q['name'])} <span>{q['n']} annonces</span></li>" for q in small)
        small_block = f"""
    <section class="block" aria-labelledby="autres-title">
      <div class="shell block-grid">
        <div class="block-copy"><h2 id="autres-title">Les autres quartiers</h2><p>Ces quartiers comptent entre 3 et {cfg['min_listings_per_quartier'] - 1} annonces dans ce relevé : trop peu pour publier une médiane fiable. Ils entreront dans le classement dès qu'un relevé hebdomadaire en comptera assez.</p></div>
        <div class="card"><ul class="small-list">{lis}</ul></div>
      </div>
    </section>
"""

    return head(title, desc, path, ld, "website") + city_header(city) + f"""  <main id="main">
    <section class="page-hero" aria-labelledby="page-title">
      <div class="shell">
        {crumbs([("Accueil", "/"), (cname, path)])}
        <h1 id="page-title">Prix immobilier à {e(cname)}, quartier par quartier</h1>
        <p class="hero-lede">Le prix médian demandé au m² des appartements à vendre à {e(cname)}, à partir de {st['n']} annonces relevées sur Sarouty le {long_date(date)}. Les chiffres sont mis à jour chaque semaine.</p>
        <div class="facts">
          <div class="hl"><span>Prix médian à {e(cname)}</span><strong>{n(st['median'])}</strong><small>MAD/m²</small></div>
          <div><span>Annonces analysées</span><strong>{st['n']}</strong><small>appartements à vendre</small></div>
          {facts_extra}
        </div>{since_line(st['changes'], st['changes'], 'de ' + e(cname), '#evolution') if st['changes'] else ''}
      </div>
    </section>
{city_calc_section(city, st, cfg)}{city_chart_section(city, st, cfg, rank_text)}{changes_block(city, st)}
    <section class="block" aria-labelledby="tableau-title">
      <div class="shell">
        <h2 id="tableau-title" style="margin-bottom:20px">Ce que permet 1 million de MAD</h2>
        <div class="card"><div class="table-wrap"><table>
          <caption class="sr-only">Prix médian demandé au m², surface accessible avec 1 million de MAD et nombre d'annonces, par quartier</caption>
          <thead><tr><th scope="col">Quartier</th><th scope="col" class="num">MAD/m²</th><th scope="col" class="num">Pour 1 M MAD</th><th scope="col" class="num">Annonces</th></tr></thead>
          <tbody>{table_rows}</tbody>
        </table></div></div>
      </div>
    </section>
{small_block}{faq_section}
    <section class="block" aria-label="Méthode">
      <div class="shell">
        <p class="note"><strong>Méthode.</strong> Relevé du {long_date(date)} sur Sarouty : {st['raw']} annonces collectées, {st['n']} exploitables après retrait des doublons, des loyers publiés comme des ventes, des surfaces de plus de {n(MAX_SURFACE)} m² et des prix au m² hors de la fourchette {n(PPM2_RANGE[0])} à {n(PPM2_RANGE[1])} MAD. Prix au m² = prix demandé / surface publiée. Les prix demandés ne sont pas des prix de vente. <a href="/#methode">En savoir plus sur la méthode</a>.</p>
      </div>
    </section>
  </main>
  <script src="/assets/city.js" defer></script>

""" + footer(cfg)


# ---------- accueil (étude Marrakech) ----------

HOME_SCALE = 40_000


def join_fr(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " et " + items[-1]


def home_mlist(city, st):
    rows = []
    grid = "".join(f'<i style="--x:{x:.2f}%"></i>' for x in (0, 25, 50, 75, 100))
    for q in st["ranked"]:
        dots = []
        for i, r in enumerate(sorted(q["rows"], key=lambda r: r["ppm2"])):
            out = r["ppm2"] > HOME_SCALE
            x = 98.95 if out else r["ppm2"] / HOME_SCALE * 100
            dots.append(f'<i class="dot{" outlier" if out else ""}" style="--x:{x:.2f}%;--y:{6 + (7 * i) % 22}px"></i>')
        rows.append(f'<li class="mrow" style="--median:{q["median"] / HOME_SCALE * 100:.2f}%">\n'
                    f'  <div class="mrow-name"><a href="/{city["slug"]}/{q["slug"]}/">{e(q["name"])}</a><span>{q["n"]} annonces</span></div>\n'
                    f'  <div class="mrow-plot" aria-hidden="true"><div class="mrow-grid">{grid}</div><div class="mrow-bar"></div><div class="mrow-pin"></div>'
                    f'<div class="mrow-dots">{"".join(dots)}</div></div>\n'
                    f'  <div class="mrow-price"><strong>{n(q["median"])}</strong> MAD/m²</div>\n</li>')
    return "\n".join(rows)


def bedroom_note(rows):
    beds = bedroom_groups(rows)
    if 1 in beds and 3 in beds:
        return (f"Calcul au prix médian demandé au m². En pratique, les petites surfaces coûtent souvent plus cher au m² : "
                f"environ {n(round(beds[1]['median'], -3))} MAD pour un 1 chambre contre {n(round(beds[3]['median'], -3))} MAD pour un 3 chambres, sur l'ensemble de la ville.")
    return "Calcul au prix médian demandé au m², sur les annonces du dernier relevé."


def calc_city(c, st, cfg):
    """Données du calculateur d'une page ville : quartiers classés, prix demandés, note sur les petites surfaces."""
    ranked = st["ranked"]
    for q in ranked:
        q["prep"] = prep(q["name"], cfg)
    data = {q["name"]: {"median": q["median"], "n": q["n"], "prep": cap(q["prep"]),
                        "prices": sorted(r["price"] for r in q["rows"])} for q in ranked}
    data["__all"] = {"median": st["median"], "n": st["n"], "prep": f"Sur l'ensemble de {c['name']}",
                     "prices": sorted(r["price"] for r in st["rows"])}
    return {"name": c["name"], "date": long_date(st["date"]), "short": long_date(st["date"]).rsplit(" ", 1)[0], "n": st["n"],
            "quartiers": [q["name"] for q in ranked], "data": data, "note": bedroom_note(st["rows"])}


PRO_SAMPLE_ROWS = 6


def home_cities(cfg, all_stats):
    return [(c, all_stats[c["slug"]]) for c in cfg["cities"] if c["slug"] in all_stats]


def home_week(cities):
    """Tableau du héros : annonces, nouvelles annonces et baisses de prix de chaque ville au dernier relevé."""
    rows, tot = [], [0, 0, 0]
    for c, st in cities:
        ch = st["changes"]
        new, cuts = (ch["new"], len(ch["cuts"])) if ch else (None, None)
        tot[0] += st["n"]
        tot[1] += new or 0
        tot[2] += cuts or 0
        cell = lambda v: "-" if v is None else str(v)
        rows.append(f'              <tr><th scope="row"><a href="/{c["slug"]}/">{e(c["name"])}</a></th><td>{n(st["n"])}</td>'
                    f'<td>{cell(new)}</td><td{" class=\"cut\"" if cuts else ""}>{cell(cuts)}</td></tr>')
    total = (f'<tr><th scope="row">Total</th><td>{n(tot[0])}</td><td>{tot[1]}</td><td{" class=\"cut\"" if tot[2] else ""}>{tot[2]}</td></tr>')
    with_changes = [(c, st) for c, st in cities if st["changes"]]
    if with_changes:
        c, st = with_changes[0]
        span = between(st["changes"], st["date"])
        foot = (f"Nouvelles annonces et baisses de prix : {span[0].lower() + span[1:]}. "
                "Prix demandés, pas prix de vente.")
    else:
        foot = "Premier relevé : les nouvelles annonces et les baisses de prix apparaîtront au relevé suivant."
    return "\n".join(rows), total, foot


def city_card(c, st, cfg):
    """Carte ville de l'accueil : médiane, annonces, quartiers, mouvements depuis le relevé précédent."""
    # Même périmètre que le bloc « Les autres quartiers » de la page ville : 3 annonces ou plus
    ranked, small = st["ranked"], [q for q in st["small"] if q["n"] >= 3]
    minimum = cfg["min_listings_per_quartier"]
    quartiers = plural(len(ranked), "classé", "classés") + (
        f", {plural(len(small), 'autre', 'autres')} avec 3 à {minimum - 1} annonces" if small else "")
    rows = [("Annonces", n(st["n"])), ("Quartiers", quartiers)]
    if len(ranked) >= 2:
        rows += [("Le plus cher", f"{ranked[0]['name']}, {n(ranked[0]['median'])} MAD/m²"),
                 ("Le moins cher", f"{ranked[-1]['name']}, {n(ranked[-1]['median'])} MAD/m²")]
    elif ranked:
        rows.append(("Seul quartier classé", f"{ranked[0]['name']}, {n(ranked[0]['median'])} MAD/m² ({ranked[0]['n']} annonces)"))
    dl = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in rows)
    return (f'          <li><a class="city-card" href="/{c["slug"]}/"><span class="qcard-name">{e(c["name"])}</span>'
            f'<span class="qcard-price"><strong>{n(st["median"])}</strong> <span>MAD/m², prix médian demandé</span></span>'
            f'<dl>{dl}</dl>{home_moves(st)}<small>Relevé du {long_date(st["date"])}</small></a></li>')


def preview_rows(cities):
    """Lignes de l'aperçu Pro : annonces récentes du relevé, colonnes publiques seulement.
    Titre, agence et lien ne sont pas dans les données du site : les cellules restent vides, masquées en CSS."""
    pool = [(c, r) for c, st in cities for r in st["rows"] if r["published"]]
    pool.sort(key=lambda cr: (cr[1]["published"], cr[1]["id"]), reverse=True)
    picked, seen = [], set()
    for c, r in pool:                       # l'annonce la plus récente de chaque ville d'abord
        if c["slug"] not in seen:
            picked.append((c, r)); seen.add(c["slug"])
    for c, r in pool:
        if len(picked) >= PRO_SAMPLE_ROWS:
            break
        if (c, r) not in picked:
            picked.append((c, r))
    masked = '<td class="masked {k}"><span></span><span class="sr-only">Version Pro</span></td>'
    return "\n".join(
        f'              <tr>{masked.format(k="t")}{masked.format(k="a")}<td>{e(c["name"])}</td><td>{e(r["district"] or "Non précisé")}</td>'
        f'<td class="num">{n(r["surface"])} m²</td><td class="num">{n(r["price"])}</td><td class="num">{n(r["ppm2"])}</td>{masked.format(k="l")}</tr>'
        for c, r in picked[:PRO_SAMPLE_ROWS])


def render_home(cfg, all_stats):
    cities = home_cities(cfg, all_stats)
    dates = sorted({st["date"] for _, st in cities})
    date = dates[-1]
    when = f"au relevé du {long_date(date)}" if len(dates) == 1 else f"aux derniers relevés, du {long_date(dates[0])} au {long_date(date)}"
    total = sum(st["n"] for _, st in cities)
    raw = sum(st["raw"] for _, st in cities)
    city_list = join_fr([c["name"] for c, _ in cities])
    week_rows, week_total, week_foot = home_week(cities)

    faq = [
        ("D'où viennent les données, et à quelle fréquence ?",
         f"Des annonces publiques d'appartements à vendre publiées sur Sarouty à {city_list}, relevées chaque lundi. "
         "Les chiffres du site et le fichier Pro viennent du même relevé."),
        ("Collectez-vous des données personnelles ?",
         "Non. Le relevé ne collecte ni nom, ni téléphone, ni email d'agent ou de particulier. Le fichier Pro reprend l'annonce telle qu'elle est publiée : "
         "titre, agence, prix, surface, quartier et lien."),
        ("Sous quel format arrive le fichier Pro ?",
         "Un fichier Excel (.xlsx) par ville, chaque lundi. Colonnes : référence Sarouty, titre, agence, quartier, prix demandé, surface, prix au m², "
         "chambres, meublé, date de publication, nouvelle annonce, baisse de prix et lien. Le fichier d'exemple de Guéliz montre le format exact."),
        ("Quelle différence entre l'accès gratuit et la version Pro ?",
         "Les pages villes et quartiers, le calculateur de budget et le dashboard sont gratuits et sans inscription, avec un aperçu de 10 annonces. "
         "La version Pro, à 29 € HT par mois, envoie chaque lundi toutes les annonces Sarouty de la ville choisie, avec leur titre, leur agence et leur lien, "
         "dans un fichier Excel."),
    ]
    faq_html = "\n".join(f"          <details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in faq)

    org = {"@type": "Organization", "@id": SITE + "/#org", "name": "Atlas Data", "url": SITE + "/", "email": "othman@atlas-data.fr",
           "description": "Données et analyses du marché immobilier marocain, à partir d'annonces publiques.", "areaServed": "MA"}
    pro = {"@type": "Product", "@id": SITE + "/#pro", "name": "Atlas Data Pro", "brand": {"@id": SITE + "/#org"},
           "description": (f"Chaque lundi, toutes les annonces d'appartements à vendre publiées sur Sarouty dans une ville au choix ({join_fr([c['name'] for c, _ in cities]).replace(' et ', ' ou ')}), "
                           "dans un fichier Excel : titre, agence, prix demandé, surface, prix au m², lien, nouvelles annonces et baisses de prix signalées."),
           "offers": {"@type": "Offer", "url": SITE + "/#offres", "price": "29.00", "priceCurrency": "EUR",
                      "availability": "https://schema.org/InStock", "seller": {"@id": SITE + "/#org"},
                      "priceSpecification": {"@type": "UnitPriceSpecification", "price": "29.00", "priceCurrency": "EUR",
                                             "valueAddedTaxIncluded": False, "unitText": "mois",
                                             "referenceQuantity": {"@type": "QuantitativeValue", "value": 1, "unitCode": "MON"}}}}
    ld = {"@context": "https://schema.org", "@graph": [
        org,
        {"@type": "WebSite", "@id": SITE + "/#site", "url": SITE + "/", "name": "Atlas Data", "inLanguage": "fr", "publisher": {"@id": SITE + "/#org"}},
        pro,
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]}
    or_list = join_fr([c["name"] for c, _ in cities]).replace(" et ", " ou ")
    tokens = {
        "META_DESC": e(f"Pour les agences : chaque lundi, toutes les annonces d'appartements à vendre de {or_list} dans un fichier Excel, "
                       "avec les nouvelles annonces et les baisses de prix."),
        "OG_DESC": e(f"{n(total)} annonces d'appartements à vendre {when}, ville par ville : prix demandés, nouvelles annonces et baisses de prix, "
                     "chaque lundi dans un fichier Excel."),
        "LD_JSON": json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"),
        "HERO_LEDE": (f"Pour les agences et les professionnels de l'immobilier à {e(city_list)} : {n(total)} annonces d'appartements à vendre {when}, "
                      "avec les nouvelles annonces et les baisses de prix signalées. Ce sont les prix demandés sur Sarouty, pas des prix de vente."),
        "WEEK_INTRO": f"Relevé du {long_date(date)}, annonces exploitables par ville.",
        "WEEK_ROWS": week_rows,
        "WEEK_TOTAL": week_total,
        "WEEK_FOOT": week_foot,
        "VILLES_P": (f"Prix médian demandé au m² des appartements à vendre, {when}. Une médiane par quartier n'est publiée qu'à partir de "
                     f"{cfg['min_listings_per_quartier']} annonces. Chaque page ville détaille ses quartiers, avec un calculateur de budget."),
        "CITY_CARDS": "\n".join(city_card(c, st, cfg) for c, st in cities),
        "PREVIEW_ROWS": preview_rows(cities),
        "PREVIEW_FOOT": f"Extrait du relevé du {long_date(date)} : {PRO_SAMPLE_ROWS} annonces parmi {n(total)}. Prix demandés, pas prix de vente.",
        "CITY_LIST": e(city_list),
        "MIN_Q": str(cfg["min_listings_per_quartier"]),
        "FINEPRINT": (f"Relevé du {long_date(date)}, mis à jour chaque lundi : {n(raw)} annonces collectées dans {len(cities)} villes, {n(total)} exploitables après retrait des doublons, "
                      "des loyers publiés comme des ventes, des surfaces absentes ou hors norme et des prix au m² aberrants. Les prix demandés ne sont pas des prix de vente. "
                      "Le relevé ne couvre pas l'ensemble du marché."),
        "FAQ": faq_html,
    }
    page = read_template("home.html")
    for k, v in tokens.items():
        page = page.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", page)
    assert not left, left
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf8") as f:
        f.write(page)


# ---------- accueil, pied de page, sitemap ----------

def home_moves(st):
    ch = st and st.get("changes")
    if not ch:
        return ""
    return (f'<span class="qcard-moves">{plural(ch["new"], "nouvelle annonce", "nouvelles annonces", "Aucune nouvelle annonce")}'
            f', {plural(len(ch["cuts"]), "baisse de prix", "baisses de prix", "aucune baisse de prix")} {e(since(ch))}</span>')


def city_medians(cfg, all_stats):
    for c in cfg["cities"]:
        st = all_stats.get(c["slug"])
        if st:
            yield c, st["median"]
        elif c.get("published"):
            yield c, c["published"]["median"]


def city_menus(cfg, all_stats):
    """Menu « Villes » de l'en-tête (bureau, mobile), avec la médiane de chaque ville."""
    cities = list(city_medians(cfg, all_stats))
    items = "".join(f'<li><a href="/{c["slug"]}/"><span>{e(c["name"])}</span><small>{n(m)} MAD/m²</small></a></li>'
                    for c, m in cities)
    menu = (f'<details class="nav-cities"><summary>Villes</summary><ul>{items}'
            '<li class="nav-cities-all"><a href="/dashboard.html">Toutes les annonces dans le dashboard</a></li></ul></details>')
    mobile = '<p class="mobile-nav-title">Prix par ville</p>' + "".join(
        f'<a class="mobile-nav-city" href="/{c["slug"]}/">{e(c["name"])} <small>{n(m)} MAD/m²</small></a>'
        for c, m in cities)
    return menu, mobile


def set_city_menus(page, menus):
    menu, mobile = menus
    page = re.sub(r"<!-- villes-menu -->.*?<!-- /villes-menu -->",
                  lambda _: f"<!-- villes-menu -->{menu}<!-- /villes-menu -->", page, flags=re.S)
    return re.sub(r"<!-- villes-mobile -->.*?<!-- /villes-mobile -->",
                  lambda _: f"<!-- villes-mobile -->{mobile}<!-- /villes-mobile -->", page, flags=re.S)


def update_footers(cfg, all_stats):
    menus = city_menus(cfg, all_stats)
    for path in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        if os.sep + "scripts" + os.sep in path:
            continue
        s = open(path, encoding="utf8").read()
        t = set_city_menus(set_city_nav(s, cfg), menus)
        if t != s:
            open(path, "w", encoding="utf8").write(t)


def update_sitemap(generated):
    path = os.path.join(ROOT, "sitemap.xml")
    old = dict(re.findall(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", open(path, encoding="utf8").read()))
    urls = {SITE + "/": None, SITE + "/dashboard.html": None}
    for p in glob.glob(os.path.join(ROOT, "**", "index.html"), recursive=True):
        rel = os.path.relpath(os.path.dirname(p), ROOT).replace(os.sep, "/")
        urls[SITE + "/" + ("" if rel == "." else rel + "/")] = None
    urls.update({SITE + k: v for k, v in generated.items()})
    order = sorted(urls, key=lambda u: (u.count("/"), u))
    lines = [f"  <url><loc>{u}</loc><lastmod>{urls[u] or old.get(u, '2026-10-17')}</lastmod></url>" for u in order]
    open(path, "w", encoding="utf8").write('<?xml version="1.0" encoding="UTF-8"?>\n'
                                           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                           + "\n".join(lines) + "\n</urlset>\n")


def update_dashboard(cfg):
    cities, rows = [], []
    for c in cfg["cities"]:
        path, date = latest_raw(c["slug"])
        if not path:
            continue
        cities.append({"slug": c["slug"], "name": c["name"], "date": date, "date_label": long_date(date)})
        for r in read_listings(path, cfg):
            rows.append({"city": c["slug"], "source_listing_id": r["id"], "district": r["district"] or "indéfini",
                         "price_mad": r["price"], "surface_m2": r["surface"], "bedrooms": r["bedrooms"],
                         "bathrooms": r["bathrooms"], "furnished": {"1": True, "0": False}.get(r["furnished"]),
                         "publication_date": r["published"] or None, "suspect_category": not r["kept"],
                         "price_per_m2": round(r["ppm2"], 2) if r["ppm2"] else None})
    data = json.dumps({"cities": cities, "rows": rows}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    path = os.path.join(ROOT, "dashboard.html")
    s = open(path, encoding="utf8").read()
    s = re.sub(r'(<script type="application/json" id="market-dataset">).*?(</script>)',
               lambda m: m.group(1) + data + m.group(2), s, count=1, flags=re.S)
    open(path, "w", encoding="utf8").write(s)


def write(path, content):
    full = os.path.join(ROOT, path.strip("/"), "index.html")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf8") as f:
        f.write(content)


def main():
    cfg = load_config()
    all_stats, generated = {}, {}
    os.makedirs(os.path.join(ROOT, "data", "stats"), exist_ok=True)
    for city in cfg["cities"]:
        if not city.get("generate") or not latest_raw(city["slug"])[0]:
            continue
        st = city_stats(city, cfg)
        all_stats[city["slug"]] = st
        write(f"/{city['slug']}/", city_page(city, st, cfg))
        generated[f"/{city['slug']}/"] = st["date"]
        for q in st["ranked"]:
            write(f"/{city['slug']}/{q['slug']}/", quartier_page(city, st, q, cfg))
            generated[f"/{city['slug']}/{q['slug']}/"] = st["date"]
        public = {k: v for k, v in st.items() if k not in ("rows", "ranked", "small")}
        public["quartiers"] = [{k: v for k, v in q.items() if k not in ("rows", "prep")} for q in st["ranked"]]
        public["autres_quartiers"] = [{"name": q["name"], "n": q["n"]} for q in st["small"]]
        with open(os.path.join(ROOT, "data", "stats", f"{city['slug']}.json"), "w", encoding="utf8") as f:
            json.dump(public, f, ensure_ascii=False, indent=1)
        print(f"{city['name']}: {st['n']}/{st['raw']} annonces exploitables, médiane {st['median']} MAD/m², "
              f"{len(st['ranked'])} quartiers : {', '.join(q['name'] + ' (' + str(q['n']) + ')' for q in st['ranked'])}")
    if all_stats:
        render_home(cfg, all_stats)
    else:
        print("ATTENTION : aucun relevé exploitable, accueil non régénéré.")
    update_dashboard(cfg)
    update_footers(cfg, all_stats)
    update_sitemap(generated)


if __name__ == "__main__":
    main()
