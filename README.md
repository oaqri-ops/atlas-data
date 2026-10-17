# atlas-data
Atlas Data — Moroccan Real Estate Intelligence &amp; Market Analytics

## Mise à jour des données

Chaque lundi, le workflow GitHub `Relevé hebdomadaire` (`.github/workflows/releve-hebdo.yml`) :

1. lance l'actor Apify `atlasdata-labs/sarouty-scraper-morocco-real-estate` pour chaque ville de `data/cities.json`
   et enregistre les annonces dans `data/raw/<ville>-<date>.csv` (`scripts/fetch_apify.py`) ;
2. régénère l'accueil (à partir de `scripts/templates/home.html`), les pages villes et quartiers, le dashboard,
   le pied de page et `sitemap.xml` (`scripts/build_site.py`) ;
3. publie le résultat sur `main`.

Le workflow a besoin du secret `APIFY_TOKEN` (Settings › Secrets and variables › Actions).
Il peut aussi être lancé à la main depuis l'onglet Actions (« Run workflow »).

Ajouter une ville : une ligne dans `data/cities.json`, avec `"generate": true`.
Pour modifier un texte fixe de l'accueil, éditer `scripts/templates/home.html` (pas `index.html`, réécrit chaque lundi).

En local :

```sh
APIFY_TOKEN=... python scripts/fetch_apify.py
python scripts/build_site.py
```
