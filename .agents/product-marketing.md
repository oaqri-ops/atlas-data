# Product Marketing Context

**Document version:** v1
**Last updated:** 2026-11-12

> Brouillon rédigé à partir du site (accueil, pages villes, FAQ, offre Pro), du dépôt et de l'actor Apify.
> Les lignes marquées **[À compléter]** demandent une information que seul le fondateur a.
> Les lignes marquées **[Hypothèse]** sont des déductions à valider avec de vrais clients.

## Product Overview
**One-liner:** Les prix au m² demandés de l'immobilier marocain, quartier par quartier, mis à jour chaque lundi ; et pour les agences, toutes les annonces de leur ville dans un fichier Excel chaque semaine.
**What it does:** Atlas Data relève chaque lundi les annonces publiques d'appartements à vendre (Avito, et Mubawab à partir du relevé du 16 novembre 2026) à Marrakech, Casablanca, Rabat et Tanger. Il retire les doublons et les annonces aberrantes, publie gratuitement les prix médians par ville et par quartier (162 pages, calculateur de budget, dashboard), et vend aux agences le fichier complet de leur ville avec les nouvelles annonces et les baisses de prix signalées.
**Product category:** Deux rayons différents :
- Grand public : « prix immobilier / prix au m² au Maroc » (à côté de Yakeey, Agenz, Mubawab).
- Agences : veille d'annonces, « pige immobilière » (à côté d'Atlevia Tech et du travail fait à la main sur les portails).
**Product type:** Site de données gratuit (acquisition SEO) + abonnement data B2B + prestations sur devis + API pour développeurs.
**Business model:**
- Gratuit : pages villes et quartiers, calculateur, dashboard (aperçu de 10 annonces), sans inscription.
- Atlas Data Pro : 29 € HT par mois, une ville au choix, sans engagement. Fichier Excel chaque lundi (référence, titre, agence, quartier, prix, surface, prix au m², chambres, meublé, date de publication, nouvelle annonce, baisse de prix, lien). Accès sur demande (formulaire), pas de paiement en ligne.
- Analyse sur mesure : sur devis, première analyse offerte.
- Développeurs : actor Apify « Morocco Real Estate Scraper », 1,50 $ pour 1 000 annonces (Sarouty, Avito, Mubawab).

## Target Audience
**Target companies:** Agences immobilières indépendantes et petits réseaux à Marrakech, Casablanca, Rabat et Tanger. **[Hypothèse]** 1 à 10 agents, sans outil de veille payant.
**Decision-makers:** Le gérant ou la gérante de l'agence (souvent aussi négociateur). **[À compléter]** Qui a demandé l'accès Pro jusqu'ici ?
**Primary use case:** Savoir chaque lundi ce qui est arrivé sur le marché de sa ville (nouvelles annonces, baisses de prix, annonces des confrères) sans passer des heures sur les portails.
**Jobs to be done:**
- Repérer les nouvelles annonces et les baisses de prix avant les autres agences (prospection de mandats, relance de vendeurs). **[Hypothèse : le job principal, à confirmer]**
- Situer le prix d'un bien face au marché du quartier, pour une estimation ou pour convaincre un vendeur de baisser son prix.
- Suivre l'offre des agences concurrentes dans son secteur.
**Use cases:**
- Rendez-vous d'estimation : « les 3 pièces de Guéliz sont affichés à 19 600 MAD/m² en médiane ».
- Négociation : montrer à un vendeur que son prix au m² est au-dessus du quartier.
- Revue du lundi : filtrer le fichier sur « nouvelle annonce » et « baisse de prix ».

**Audience gratuite (ne paie pas, mais fait le trafic) :** acheteurs, Marocains résidant à l'étranger (MRE), investisseurs particuliers qui cherchent « prix m² + quartier ». Elle sert le SEO, la notoriété et la crédibilité auprès des agences.

## Personas
| Persona | Cares about | Challenge | Value we promise |
|---------|-------------|-----------|------------------|
| Gérant d'agence (décideur, utilisateur) | Rentrer des mandats, ne pas rater une affaire, paraître expert face aux vendeurs | Le marché est éclaté entre plusieurs portails ; la veille se fait à la main, mal et en retard | Tout le marché de sa ville dans un fichier, chaque lundi, avec ce qui a changé |
| Négociateur | Avoir des arguments chiffrés en rendez-vous | Pas de référence de prix fiable par quartier | Médianes par quartier et par nombre de chambres, sources et méthode explicites |
| Acheteur, MRE (audience gratuite) | Ne pas surpayer, comprendre les quartiers à distance | Prix opaques, annonces hétérogènes | Prix médians demandés par quartier, calculateur de budget, gratuit |
| Développeur, data analyst | Données propres, API | Scraper soi-même les portails | Actor Apify prêt à l'emploi, sans données personnelles |

## Problems & Pain Points
**Core problem:** Les annonces sont dispersées sur plusieurs portails (Avito, Mubawab, Sarouty…), souvent en double, sans historique : une agence ne sait pas, chaque semaine, ce qui est nouveau ni ce qui a baissé.
**Why alternatives fall short:**
- Les portails eux-mêmes : une recherche par portail, pas d'export, pas de « ce qui a changé depuis lundi dernier ».
- Les référentiels de prix (Yakeey, Agenz) : une moyenne par ville ou quartier, sans les annonces derrière, sans méthode détaillée publique (à vérifier).
- La veille à la main : chronophage et incomplète.
**What it costs them:** **[À compléter]** Heures de veille par semaine ; mandats perdus faute d'avoir vu une annonce à temps.
**Emotional tension:** **[Hypothèse]** Peur de rater le bien qu'un confrère rentrera ; inconfort d'estimer « au feeling » devant un vendeur.

## Competitive Landscape
**Direct (agences) :** Atlevia Tech, application marocaine de pige multiportail pour agences, qui met en avant des alertes et le repérage des particuliers (vu sur Facebook et Instagram en novembre 2026 ; prix et couverture à vérifier). Elle va plus loin sur l'alerte en temps réel et le contact des particuliers. Atlas Data reste sur un fichier hebdomadaire simple, sans données personnelles.
**Direct (grand public) :** Yakeey et Agenz publient des référentiels de prix au m² par ville et quartier ; Mubawab a un guide des prix et une estimation en ligne. Leurs chiffres sont des estimations (Yakeey Marrakech : 7 577 DH/m² ; Agenz : 8 885 DH/m², relevés le 12 novembre 2026), Atlas Data publie des prix demandés (12 687 MAD/m²) : l'écart vient de la nature du chiffre et doit être expliqué, pas caché.
**Secondary :** Les fichiers internes et les tableurs tenus par les agences ; les groupes WhatsApp et Facebook d'agents.
**Indirect :** Ne rien suivre et travailler au réseau ; les estimations d'un notaire ou d'un expert.

## Differentiation
**Key differentiators:**
- Granularité : une médiane par quartier dès 8 annonces (162 villes et quartiers), par nombre de chambres.
- Fréquence : un relevé chaque lundi, avec les nouvelles annonces et les baisses de prix d'une semaine à l'autre.
- Plusieurs portails, une seule fois chaque bien : Avito et Mubawab dans le même fichier, doublons retirés (à partir du 16 novembre 2026).
- Transparence : prix demandés assumés comme tels, méthode publiée, chiffres vérifiables annonce par annonce dans le dashboard.
- Aucune donnée personnelle collectée.
- Prix d'entrée bas, sans engagement.
**How we do it differently:** Un fichier Excel ouvert, pas une application de plus à apprendre.
**Why that's better:** Zéro prise en main ; l'agence filtre, trie et partage comme elle veut.
**Why customers choose us:** **[À compléter]** Demander aux premiers clients Pro pourquoi ils ont dit oui.

## Objections
| Objection | Response |
|-----------|----------|
| « Ce sont des prix demandés, pas des prix de vente. » | C'est dit partout sur le site. Pour une agence, le prix demandé est le marché concurrent du jour ; pour une estimation, la médiane du quartier est un repère, pas un verdict. |
| « Les annonces, je les vois déjà sur Avito. » | Une par une, sur un seul portail. Le fichier les réunit toutes, Avito et Mubawab sans doublons, et signale ce qui est nouveau ou a baissé depuis lundi. |
| « Vos prix sont plus hauts que ceux de Yakeey ou Agenz. » | Eux estiment des valeurs, nous mesurons les prix affichés. Les deux sont utiles ; les nôtres se vérifient annonce par annonce. |
| « 29 € pour un fichier Excel ? » | **[À compléter]** Le comparer au temps de veille gagné et à un seul mandat rentré. |
| « Pourquoi en euros ? » | **[Hypothèse]** Frein probable pour une agence marocaine : afficher un prix en dirhams. |

**Anti-persona:** Les particuliers vendeurs ou acheteurs (gratuit suffisant) ; les promoteurs qui veulent des prix de transaction officiels ; les agences qui veulent les téléphones des vendeurs particuliers (non collectés, par choix).

## Switching Dynamics
**Push:** Veille manuelle sur plusieurs portails, annonces en double, aucun suivi des baisses de prix.
**Pull:** Le lundi matin, un fichier avec « nouvelles » et « baisses de prix » ; des chiffres par quartier à montrer en rendez-vous.
**Habit:** Habitude de parcourir Avito à la main ; réseau et bouche-à-oreille.
**Anxiety:** Fiabilité des chiffres, couverture partielle du marché, service récent et inconnu, paiement à l'étranger en euros.

## Customer Language
**How they describe the problem:** **[À compléter]** Mots exacts entendus dans les demandes d'accès Pro et les échanges par email.
**How they describe us:** **[À compléter]**
**Words to use:** prix demandé, prix médian au m², quartier, relevé du lundi, nouvelles annonces, baisses de prix, fichier Excel, sans engagement, annonces publiques.
**Words to avoid:** « prix du marché » ou « valeur » sans préciser (ce sont des prix demandés) ; « estimation » pour nos médianes ; « exhaustif », « tout le marché » (le relevé ne couvre pas tout) ; « plateforme », « IA » (rien ne le justifie).
**Glossary:**
| Term | Meaning |
|------|---------|
| Relevé | La collecte hebdomadaire du lundi |
| Annonce exploitable | Annonce gardée après retrait des doublons et des aberrations |
| Prix médian demandé | Médiane des prix au m² affichés, par ville ou quartier |
| Pige | Veille des annonces pour trouver des mandats (vocabulaire des agences) |

## Brand Voice
| Attribute | Means | Doesn't mean | Example line |
|-----------|-------|--------------|--------------|
| Précis | Des chiffres datés, sourcés, avec leur limite | Jargon statistique | « Une médiane par quartier n'est publiée qu'à partir de 8 annonces. » |
| Honnête | Dire ce que les chiffres ne disent pas | Se dénigrer | « Les prix demandés ne sont pas des prix de vente. » |
| Direct | Phrases courtes, l'utile d'abord | Sec ou froid | « Combien coûte le m² dans votre quartier ? » |
| Utile | Chaque page sert une décision (budget, estimation) | Remplissage SEO | « Entrez un budget et choisissez des quartiers. » |

**Tone by context:**
- Support : réponse directe du fondateur, signée, en français.
- Launch : factuel, ce qui change et pour qui.
- Errors : dire ce qui s'est passé et quoi faire (« rechargez la page »).
- Sales : chiffres de la ville du prospect, pas d'urgence artificielle.
- Social : un chiffre de quartier par post, la méthode en lien.
**Terms we own:** « relevé du lundi », « prix médian demandé ».
**Never use (and why):** faux témoignages ou logos (aucun client affiché à ce jour) ; « temps réel » (relevé hebdomadaire).

## Proof Points
**Metrics:** 21 505 annonces collectées, 13 039 exploitables au relevé du 9 novembre 2026 ; 4 villes ; 162 villes et quartiers avec une médiane ; relevé chaque lundi depuis octobre 2026. Avec Mubawab (simulation) : environ 19 600 annonces exploitables.
**Customers:** **[À compléter]** Nombre d'agences Pro ; accord pour les citer ?
**Testimonials:** Aucun pour l'instant. À recueillir auprès des premiers clients, avec leur accord.
**Value themes:**
| Theme | Proof |
|-------|-------|
| Couverture | 13 039 annonces exploitables par semaine, bientôt Avito + Mubawab |
| Fiabilité | Méthode publiée, doublons retirés, seuil de 8 annonces par quartier |
| Gain de temps | **[À compléter]** Temps de veille économisé selon les clients |

## Goals
**Business goal:** **[À compléter]** Objectif d'agences Pro à 3 et 12 mois.
**Conversion action:** Demande d'accès Pro (formulaire) ; secondaire : téléchargement du fichier d'exemple (Guéliz).
**Current metrics:** **[À compléter]** Aucun outil de mesure d'audience sur le site au 12 novembre 2026 ; demandes Pro reçues par email.

## Learnings
*Decisions and tested lessons. Newest first. Keep it to about 20 active entries.*
| Date | Learning | Evidence | Applies to | Status |
|------|----------|----------|------------|--------|
| 2026-11-12 | Ajouter Mubawab relève les médianes de 3 à 18 % selon la ville : à expliquer aux clients avant le relevé du 16 novembre. | Simulation sur le relevé du 9 novembre (Marrakech 12 687 → 15 014 MAD/m²) | Emails clients, pages villes | active |
| 2026-11-09 | Le passage de Sarouty à Avito a baissé les médianes de 18 à 32 % ; les clients ont été prévenus. | Relevé du 9 novembre 2026 | Communication sur les changements de source | active |

## Changelog
*Newest first. One line per revision: what changed and why.*
- v1 (2026-11-12) — Brouillon initial tiré du site, du dépôt et de l'actor Apify ; concurrents vérifiés le 12 novembre 2026.
