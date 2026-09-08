# Earth Burns — pipeline de données

Préparation des données de la dataviz **Earth Burns** : 46 ans (1979–2024) de météo
propice aux incendies, monde observé contre monde sans réchauffement anthropique, réduits
à quelques dizaines de mégaoctets animables dans un navigateur.

La documentation pédagogique est dans [`docs/`](docs/00-overview.md) ; le journal des
décisions dans [`docs/decisions.md`](docs/decisions.md).

## Installation

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/Scripts/python.exe -m pytest -q      # 90 tests, 94 % de couverture
```

## Données d'entrée

| Donnée | Où | État |
|---|---|---|
| FWI observé + contrefactuel (Dryad, 9,3 Go) | `data/raw/dryad/` | téléchargé, 101 empreintes vérifiées |
| GLDAS classes de végétation | `data/raw/gldas/` | téléchargé |
| Régions GFED (`GFED4.1s_1997.hdf5`) | `data/raw/gfed/` | téléchargé |
| GEFF-ERA5 1991 et 2018 (banc d'essai) | `data/raw/zenodo_geff/` | téléchargé |

## Exécution

```bash
PY=.venv/Scripts/python.exe
THR=data/interim/thresholds_dryad_1991-2020.nc
$PY -m earthburns.cli mask                       # masques → data/interim/masks.nc
$PY -m earthburns.cli dryad download             # nécessite DRYAD_CLIENT_ID/SECRET
$PY -m earthburns.cli thresholds --source dryad --allow-incomplete
$PY -m earthburns.cli monthly --world observed --thresholds $THR --allow-incomplete
$PY -m earthburns.cli monthly --world counterfactual --thresholds $THR --allow-incomplete
$PY -m earthburns.cli pack --world observed
$PY -m earthburns.cli pack --world counterfactual
```

`--allow-incomplete` est requis ici pour une raison précise, pas par confort : les fichiers
Dryad contiennent 365 pas de temps quelle que soit l'année, si bien que les douze années
bissextiles de la série n'ont pas de 31 décembre. Un jour manquant **entre** deux jours lus
reste refusé dans tous les cas.

Banc d'essai sans jeton, sur les années GEFF présentes :

```bash
$PY -m earthburns.cli thresholds --source zenodo --years 1991
$PY -m earthburns.cli monthly --source zenodo --years 2018 --thresholds data/interim/thresholds_zenodo_1991-1991.nc
$PY -m earthburns.cli pack --source zenodo
$PY scripts/plot_diagnostics.py                  # cartes de contrôle → data/processed/
```

Temps mesurés sur la série complète, poste à 16 cœurs logiques : 12 minutes pour la passe 1
sur les 30 années de référence, 16 minutes pour les deux passes 2 lancées en parallèle sur
46 ans, 4 minutes pour l'empaquetage. Environ **35 minutes** au total après téléchargement.

## Sorties

```
web/                                               l'application, modules ES sans build
data/interim/masks.nc                              masque brûlable, régions GFED, poids cos(lat)
data/interim/thresholds_<src>_<y0>-<y1>.nc         seuils p90/p95/p99 + couverture + validation
data/interim/monthly/<src>_<monde>_<an>.nc         jours extrêmes par mois (uint8)
data/interim/monthly/<src>_<monde>_<an>_extent.parquet  fractions et couverture quotidiennes
data/web/<src>/                                    blobs brotli + manifest.json pour le client
```

Les noms sont décidés dans un seul module, [`earthburns/layout.py`](earthburns/layout.py) :
relancer une année écrase exactement ce qu'elle remplace.

## Ce que le pipeline refuse

Il échoue plutôt que de produire une sortie plausible mais fausse : période de référence
incomplète ou jour dupliqué en passe 1, variable qui n'est pas du FWI, grille source à la
mauvaise résolution, année ou jour manquant à l'empaquetage, masque modifié sous des blobs
déjà écrits. Chacun de ces cas a d'abord été un bug silencieux, corrigé et documenté dans
[docs/decisions.md](docs/decisions.md).

## La visualisation

```bash
.venv/Scripts/python.exe scripts/serve_web.py --port 8123
```

Puis <http://127.0.0.1:8123>. Quatre lectures : notre monde, le monde sans réchauffement
anthropique, les deux côte à côte, et leur différence. Espace pour jouer, molette pour
zoomer, 0 pour revenir au monde entier. Détails d'implémentation dans
[docs/07-webgl-renderer.md](docs/07-webgl-renderer.md).

## Résultats

La série complète est calculée. Les chiffres, les contrôles et leurs limites sont dans
[docs/06-first-results.md](docs/06-first-results.md). En résumé, la part de surface brûlable
en météo extrême passe de 7,70 % sur 1979–1990 à 11,97 % sur 2014–2024, contre 7,13 % et
9,51 % dans un monde sans réchauffement anthropique.

## Références principales

- Yin C., Abatzoglou J. T., Jones M. W. et al. (2026), *Increasing synchronicity of global
  extreme fire weather*, Science Advances, doi:10.1126/sciadv.adx8813 ; données Dryad
  doi:10.5061/dryad.cfxpnvxkp (CC0).
- Vitolo C. et al. (2019), GEFF-ERA5, Scientific Data, doi:10.1038/sdata.2019.32 ; Zenodo 3540938.
- NASA GLDAS vegetation class mask ; GFED4.1s basis regions (van der Werf et al. 2017).
