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

Ajouter une ville : une ligne dans `data/cities.json`, avec `"generate": true`. Elle apparaît ensuite
dans le calculateur de l'accueil, le menu « Villes » et le pied de page.

## Évolution d'un relevé à l'autre

`build_site.py` compare le dernier relevé de chaque ville au précédent (`data/raw/`), en reliant les
annonces par leur référence Sarouty : nouvelles annonces, annonces retirées, baisses et hausses de prix,
et variation de la médiane quand chaque relevé compte au moins 15 annonces (`MIN_LISTINGS_FOR_TREND`).
Le résultat s'affiche sur les pages villes (section « Ce qui a changé »), les pages quartiers et les
cartes villes de l'accueil, et il est enregistré dans `data/stats/<ville>.json` (clé `changes`).
Garder au moins les deux derniers CSV de chaque ville.

## Interface

`DESIGN.md` décrit le système visuel (couleurs, typographie, composants, règles). Le menu « Villes » et
le formulaire de demande d'accès Pro sont dans `assets/components.css` et `assets/components.js`.

Formulaire Pro : en haut de `assets/components.js`, renseigner `whatsapp` (numéro international sans
« + », ex. `212600000000`) pour afficher un bouton WhatsApp, et/ou `endpoint` (URL Formspree, Getform…)
pour recevoir les demandes sans passer par la messagerie du visiteur. Tant que les deux sont vides, le
formulaire ouvre un email prérempli et affiche l'adresse à copier.
Pour modifier un texte fixe de l'accueil, éditer `scripts/templates/home.html` (pas `index.html`, réécrit chaque lundi).

En local :

```sh
APIFY_TOKEN=... python scripts/fetch_apify.py
python scripts/build_site.py
```
