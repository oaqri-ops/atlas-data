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
import glob
import html
import json
import math
import os
import re
import statistics
import unicodedata

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
    return stats


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
  <link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/site.css">
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


def rank_list(city, ranked, current=None):
    top = ranked[0]["median"]
    items = []
    for q in ranked:
        me = q is current
        items.append(f'<li class="{"me" if me else ""}"><a href="/{city["slug"]}/{q["slug"]}/"'
                     f'{" aria-current=\"page\"" if me else ""}><span>{e(q["name"])}</span>'
                     f'<span class="bar"><i style="width:{q["median"] / top * 100:.1f}%"></i></span>'
                     f'<span class="v">{n(q["median"])}</span></a></li>')
    return '<ul class="rank">' + "".join(items) + "</ul>"


def strip_chart(q, scale):
    lanes = [0, -14, 14, -28, 28, -42, 42]
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

    return head(title, desc, path, ld) + read_template("header.html") + f"""  <main id="main">
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
        </div>{sample}
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
          <p class="card-foot">Surface au prix médian demandé ; annonces dont le prix demandé est inférieur ou égal au budget.</p>
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
          {rank_list(city, ranked, q)}
          <p class="card-foot">Prix médian demandé en MAD/m², quartiers d'au moins {cfg['min_listings_per_quartier']} annonces.</p>
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
        <div><h2 id="pro-title">Vous êtes une agence {e(q['prep'])}&nbsp;?</h2><p>Recevez chaque semaine toutes les annonces du quartier dans un fichier Excel, avec titres, agences et liens d'origine, nouvelles annonces et baisses de prix. 29 € HT par mois, sans engagement.</p></div>
        <a class="btn btn-primary" href="{mail}">Demander l'accès Pro</a>
      </div>
    </section>

    <section class="block" aria-label="Méthode">
      <div class="shell">
        <p class="note"><strong>Méthode.</strong> Relevé du {long_date(date)} sur Sarouty : {q['n']} annonces d'appartements à vendre {e(q['prep'])}, parmi {st['n']} annonces exploitables à {e(cname)}. Prix au m² = prix demandé / surface publiée. Les prix demandés ne sont pas des prix de vente, et le relevé ne couvre pas l'ensemble du marché. Données mises à jour chaque semaine. <a href="/#methode">En savoir plus sur la méthode</a>.</p>
      </div>
    </section>
  </main>

""" + footer(cfg)


def city_page(city, st, cfg):
    cname, date, ranked = city["name"], st["date"], st["ranked"]
    path = f"/{city['slug']}/"
    title = f"Prix immobilier {cname} par quartier ({short_month(date)}) - Atlas Data"
    if len(ranked) >= 2:
        span = f"de {n(ranked[-1]['median'])} MAD/m² {prep(ranked[-1]['name'], cfg)} à {n(ranked[0]['median'])} MAD/m² {prep(ranked[0]['name'], cfg)}"
        desc = f"Prix au m² des appartements à {cname} : {span}. {st['n']} annonces, mises à jour chaque semaine."
    else:
        desc = f"Prix au m² des appartements à vendre à {cname} : {n(st['median'])} MAD/m² en médiane sur {st['n']} annonces, mises à jour chaque semaine."
    ld = {"@context": "https://schema.org", "@graph": [
        breadcrumb_ld([("Accueil", "/"), (f"Prix au m² à {cname}", path)]),
        {"@type": "ItemList", "name": f"Prix au m² par quartier à {cname}", "itemListElement": [
            {"@type": "ListItem", "position": q["rank"], "name": f"Prix au m² {prep(q['name'], cfg)}",
             "url": f"{SITE}/{city['slug']}/{q['slug']}/"} for q in ranked]},
        dataset_ld(f"Prix des appartements à vendre à {cname} par quartier ({MONTHS[int(date[5:7]) - 1]} {date[:4]})",
                   f"Prix demandés de {st['n']} annonces d'appartements à vendre à {cname}, relevées sur Sarouty le {long_date(date)}. "
                   f"Médianes par quartier pour les secteurs comptant au moins {cfg['min_listings_per_quartier']} annonces.",
                   path, f"{cname}, Maroc", date)]}

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

    rank_block = (f'<div class="card">{rank_list(city, ranked)}<p class="card-foot">Prix médian demandé en MAD/m², relevé du {long_date(date)}.</p></div>'
                  if ranked else "<div></div>")
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

    return head(title, desc, path, ld, "website") + read_template("header.html") + f"""  <main id="main">
    <section class="page-hero" aria-labelledby="page-title">
      <div class="shell">
        {crumbs([("Accueil", "/"), (cname, path)])}
        <h1 id="page-title">Prix immobilier à {e(cname)}, quartier par quartier</h1>
        <p class="hero-lede">Le prix médian demandé au m² des appartements à vendre à {e(cname)}, à partir de {st['n']} annonces relevées sur Sarouty le {long_date(date)}. Les chiffres sont mis à jour chaque semaine.</p>
        <div class="facts">
          <div class="hl"><span>Prix médian à {e(cname)}</span><strong>{n(st['median'])}</strong><small>MAD/m²</small></div>
          <div><span>Annonces analysées</span><strong>{st['n']}</strong><small>appartements à vendre</small></div>
          {facts_extra}
        </div>
      </div>
    </section>

    <section class="block" aria-labelledby="classement-title">
      <div class="shell block-grid">
        <div class="block-copy">
          <h2 id="classement-title">Le classement des quartiers</h2>
          <p>{rank_text}</p>
        </div>
        {rank_block}
      </div>
    </section>

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
{small_block}
    <section class="block" aria-label="Méthode">
      <div class="shell">
        <p class="note"><strong>Méthode.</strong> Relevé du {long_date(date)} sur Sarouty : {st['raw']} annonces collectées, {st['n']} exploitables après retrait des doublons, des loyers publiés comme des ventes, des surfaces de plus de {n(MAX_SURFACE)} m² et des prix au m² hors de la fourchette {n(PPM2_RANGE[0])} à {n(PPM2_RANGE[1])} MAD. Prix au m² = prix demandé / surface publiée. Les prix demandés ne sont pas des prix de vente. <a href="/#methode">En savoir plus sur la méthode</a>.</p>
      </div>
    </section>
  </main>

""" + footer(cfg)


# ---------- accueil, pied de page, sitemap ----------

def cities_section(cfg, all_stats):
    cards = []
    for c in cfg["cities"]:
        if c.get("generate"):
            st = all_stats[c["slug"]]
            median, count, nq, date = st["median"], st["n"], len(st["ranked"]), st["date"]
        else:
            p = c["published"]
            median, count, nq, date = p["median"], p["n"], p["quartiers"], p["date"]
        cards.append(
            f'<li><a class="qcard" href="/{c["slug"]}/"><span class="qcard-name">{e(c["name"])}</span>'
            f'<span class="qcard-price"><strong>{n(median)}</strong> <span>MAD/m²</span></span>'
            f'<span class="qcard-foot"><span>{count} annonces · {nq} quartier{"s" if nq > 1 else ""}</span></span>'
            f'<span class="qcard-foot"><span>Relevé du {long_date(date)}</span></span></a></li>')
    return ("<!-- villes:start -->\n"
            '    <section class="section" id="villes" aria-labelledby="villes-title">\n'
            '      <div class="shell">\n'
            '        <div class="section-head"><h2 id="villes-title">Les prix par ville</h2>'
            "<p>Prix médian demandé au m² des appartements à vendre. Les pages ville détaillent chaque quartier et sont mises à jour chaque semaine.</p></div>\n"
            f'        <ul class="qcards">{"".join(cards)}</ul>\n'
            "      </div>\n"
            "    </section>\n"
            "    <!-- villes:end -->")


def update_home(cfg, all_stats):
    path = os.path.join(ROOT, "index.html")
    s = open(path, encoding="utf8").read()
    block = cities_section(cfg, all_stats)
    if "<!-- villes:start -->" in s:
        s = re.sub(r"<!-- villes:start -->.*?<!-- villes:end -->", lambda m: block, s, flags=re.S)
    else:
        anchor = '    <section class="section" aria-label="Fonctionnalités">'
        s = s.replace(anchor, "    " + block + "\n\n" + anchor, 1)
    open(path, "w", encoding="utf8").write(s)


def update_footers(cfg):
    for path in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True):
        if os.sep + "scripts" + os.sep in path:
            continue
        s = open(path, encoding="utf8").read()
        t = set_city_nav(s, cfg)
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
    update_home(cfg, all_stats)
    update_dashboard(cfg)
    update_footers(cfg)
    update_sitemap(generated)


if __name__ == "__main__":
    main()
