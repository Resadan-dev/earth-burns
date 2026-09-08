# 01 — Sources de données et accès

## Tableau récapitulatif

| Donnée | Rôle | Accès | Licence | Taille |
|---|---|---|---|---|
| FWI observé + contrefactuel 1979–2024, 0,25°, quotidien | cœur du projet | Dryad, **jeton API requis** | CC0 | 92 fichiers, 9,92 Go |
| FWI GEFF-ERA5 1979–2018 (Vitolo et al. 2019) | banc d'essai public, même grille | Zenodo, libre | CC BY 4.0 | ~440 Mo / an |
| GLDAS classes de végétation 0,25° (Noah, IGBP modifié) | masque « brûlable » | NASA LDAS, libre | domaine public | 125 Ko |
| Régions GFED (14 régions, dans GFED4.1s_1997.hdf5) | découpage régional, compteur de simultanéité | VU Amsterdam, libre | CC BY 4.0 | 47 Mo |
| Surface brûlée GFED5 (plus tard) | overlay « feux réels » | Zenodo 7668424 | CC BY 4.0 | 265 Mo |

## Dryad : pourquoi il faut un jeton, et comment l'obtenir

Le dépôt Dryad protège ses liens de téléchargement par un test anti-robot en JavaScript et
son API refuse tout téléchargement sans jeton (`401 Unauthorized, must have current bearer
token`, constaté le 2026-09-07). Le pipeline n'essaie pas de contourner cette protection :
il passe par l'API officielle.

Procédure, d'après la [documentation Dryad](https://github.com/datadryad/dryad-app/blob/main/documentation/apis/api_accounts.md) :

1. Créer un compte Dryad via ORCID sur <https://datadryad.org> et s'y connecter une fois.
2. Sur la page *My account* (<https://datadryad.org/account>), créer une **application API** :
   on obtient un `client_id` et un `client_secret`.
3. Exporter ces identifiants dans l'environnement (jamais dans le dépôt) :

   ```bash
   export DRYAD_CLIENT_ID=...
   export DRYAD_CLIENT_SECRET=...
   ```

   Le pipeline demande lui-même un jeton (valable 10 h) à `POST /oauth/token`.
   On peut aussi fournir directement `DRYAD_TOKEN`.
4. Lancer le téléchargement, qui reprend là où il s'est arrêté et vérifie chaque SHA-256 :

   ```bash
   .venv/Scripts/earthburns dryad download
   ```

   L'ordre est choisi pour démarrer la passe 1 au plus tôt : petits fichiers (README,
   notebooks), puis années de référence 1991–2020 du monde observé, puis le contrefactuel,
   puis le reste.

Alternative sans script : télécharger l'archive complète depuis la page du dataset dans un
navigateur, puis déposer les `.nc` dans `data/raw/dryad/`. La commande
`earthburns dryad status --verify` confirme l'intégrité de chaque fichier grâce aux
empreintes SHA-256 publiées dans le manifeste de l'API.

Le manifeste (`/api/v2/versions/435817/files`) reste public : c'est lui qui donne tailles,
empreintes et identifiants. Version 8 du dataset, mise à jour du 2026-04-09 : c'est celle
qui contient l'année 2009, absente des versions précédentes.

## Ce que contiennent réellement les fichiers Dryad

Téléchargés et vérifiés le 2026-09-08 : 92 NetCDF, 9,3 Go, 101 empreintes SHA-256 toutes
conformes. Leur structure réserve trois surprises, toutes traitées par le lecteur.

| Élément | Valeur |
|---|---|
| Variable | `fwi`, float32, attribut « FWI from daily summary, overwintering on » |
| Grille | 721 × 1440 nœuds, latitude 90 → −90, longitude **0 → 359,75** |
| Valeur manquante | `_FillValue = −9999`, décodée par xarray : l'océan arrive en NaN |
| Part manquante | 73 % de la grille, ce qui correspond aux mers |
| Découpage interne | blocs de 73 jours × 145 × 288, gzip niveau 9 |
| Axe temporel | **pas de coordonnée**, une variable `days` à part |

**Première surprise, le temps.** La dimension `time` n'a aucune coordonnée. Les dates
vivent dans une variable `days` dont l'unité est écrite `days_since_Jan11900`, une forme
qu'aucun décodeur CF ne reconnaît : xarray refuse même d'ouvrir le fichier. Le lecteur
ouvre donc en repli sans décodage temporel, puis interprète lui-même l'origine. C'est
exactement ce que font les auteurs dans leur notebook, avec `decode_times=False`.

**Deuxième surprise, les années bissextiles.** Chaque fichier contient exactement 365 pas
de temps, y compris pour 1992, 1996, 2000, 2004, 2008, 2012, 2016, 2020 et 2024. Les jours
sont contigus à partir du 1er janvier, donc le 29 février est bien présent : c'est le
**31 décembre qui manque**, douze fois sur la période 1979–2024. Le pipeline l'accepte, le
signale, et enregistre le nombre de jours réellement observés par mois pour que les
comptages restent lisibles. Un trou entre deux jours lus, lui, reste une erreur.

**Troisième surprise, le découpage.** Les blocs de 73 jours veulent être lus d'un coup :
en lisant par 32 jours, chaque bloc compressé est décompressé deux fois. Le lecteur
s'aligne désormais sur le découpage déclaré par le fichier, ce qui divise par deux le temps
de lecture, mesuré à 3,9 s au lieu de 7,7 s pour 146 jours.

## Ce que les notebooks des auteurs confirment

Le dépôt contient leurs sept notebooks. Ils tranchent des choix que j'avais dû interpréter :

- **Le seuil** : `threshold_1 = 90`, calculé par `ds_fwi.quantile(0.90, dim='time')` sur
  `range(1991, 2021)`. Période et méthode identiques aux miennes, la méthode par défaut de
  `quantile` étant l'interpolation linéaire, celle que mon estimateur par histogramme
  approche à la largeur de classe près.
- **La pondération** : ils calculent l'aire réelle de chaque cellule,
  `R² × cos(latitude) × Δlat × Δlon`. À pas constant, c'est proportionnel à cos(latitude),
  donc identique à ma pondération dès lors qu'on en fait un rapport.
- **La simultanéité** : « days of extreme FWI over 30 % area in each GFED region », ce qui
  confirme le seuil de 30 % et le découpage GFED.
- **Le masque** : ils appliquent `xr.where(vegetated.notnull(), fwi, nan)` à partir d'un
  fichier `vegetated_area.nc` dérivé de `GLDAS_domveg`. Ce fichier n'est **pas publié**,
  seulement le code qui le consomme. Ma liste de classes reste donc une reconstruction,
  documentée en D4, et non une copie de la leur.

## GEFF-ERA5 (Zenodo) : le banc d'essai

Vitolo C. et al., *A 1980–2018 global fire danger re-analysis dataset for the Canadian Fire
Weather Indices*, Scientific Data 6, 2019, doi:[10.1038/sdata.2019.32](https://doi.org/10.1038/sdata.2019.32).
Record Zenodo [3540938](https://zenodo.org/records/3540938), un fichier par an.

Même grille ERA5 que Dryad, mais trois différences à connaître :

- dimensions nommées `Time` / `Latitude` / `Longitude`, longitude de 0 à 359,75 ;
- le temps est un **numéro de jour** (1…365), pas une date : le lecteur reconstruit les
  dates à partir de l'année contenue dans le nom du fichier ;
- l'océan est codé **−3,4 × 10³⁸**, mais **avec** un attribut `_FillValue` que xarray
  décode : à travers `open_fwi_year`, un bloc de quatre jours contient déjà 3 658 308 NaN
  et zéro valeur négative. Le lecteur conserve néanmoins une règle « valeur négative =
  manquante », non pas comme substitut au décodage, mais comme garde-fou pour une source
  future dont l'attribut serait absent. Une version antérieure de ce document affirmait
  l'inverse ; c'était faux, et la décision D6 a été corrigée en conséquence.

Ce jeu ne contient pas d'hivernage du code de sécheresse (« no overwintering »), à la
différence de Dryad : les valeurs de printemps en climat froid diffèrent un peu. Il sert
uniquement à valider la mécanique du pipeline sur des données réelles.

## GLDAS : classes de végétation

NASA GLDAS, *Vegetation class / mask*, fichier `GLDASp5_domveg_NOAH3.6_025d.nc4`
(<https://ldas.gsfc.nasa.gov/gldas/vegetation-class-mask>). Grille de 600 × 1440 cellules,
centres à ±0,125°, de −59,875° à 89,875° (pas d'Antarctique). Classification « Modified
IGBP » à 20 classes, les codes sont listés dans `earthburns/mask.py`.

C'est la carte utilisée par l'article pour définir les « burnable wildland areas ».

## GFED : régions

Les 14 régions de base de GFED (BONA, TENA, CEAM, NHSA, SHSA, EURO, MIDE, NHAF, SHAF, BOAS,
CEAS, SEAS, EQAS, AUST) sont stockées dans chaque fichier annuel GFED4.1s sous
`ancill/basis_regions`, grille 720 × 1440 à centres ±0,125°. Nous utilisons le fichier
1997 (le plus petit, 47 Mo) : <https://www.geo.vu.nl/~gwerf/GFED/GFED4/>.
Référence : van der Werf G. R. et al., *Global fire emissions estimates during 1997–2016*,
Earth System Science Data 9, 2017, doi:[10.5194/essd-9-697-2017](https://doi.org/10.5194/essd-9-697-2017).

## Ce que le pipeline vérifie à l'entrée

- la grille est bien 721 × 1440 au pas de 0,25°, sinon erreur ;
- la variable FWI est identifiée par son nom ou comme unique variable 3-D ;
- l'axe temporel est converti en dates, et une année incomplète est refusée par défaut ;
- chaque fichier Dryad est comparé à son SHA-256 avant usage.
