# 04 — Passe 2 : comptage mensuel et étendue quotidienne

## Ce que la passe produit

Pour chaque monde (observé, contrefactuel), chaque année, chaque fichier est relu une fois
et deux produits sont dérivés dans la même boucle :

1. **Comptage mensuel** (`monthly.MonthlyExceedance`) : pour chaque mois, chaque cellule
   et chaque seuil (p90, p95, p99), le nombre de jours où `FWI > seuil`. Un octet par
   valeur suffit (0 à 31). Sortie : `data/interim/monthly/<source>_<monde>_<année>.nc`,
   variables `days_gt_p90`, `days_gt_p95`, `days_gt_p99` de dimensions (12, 721, 1440),
   compressées zlib (≈ 1,9 Mo par an).
2. **Étendue quotidienne** (`extent.daily_extent`) : pour chaque jour et chaque seuil, la
   fraction, pondérée par cos(latitude), de la surface **brûlable** dont le FWI dépasse le
   seuil, globalement et pour chacune des 14 régions GFED, **plus la couverture**. Sortie :
   une table Parquet écrite au même endroit et au même moment que les comptages,
   `data/interim/monthly/<source>_<monde>_<année>_extent.parquet`, 32 colonnes.

## Le piège du dénominateur

Diviser les cellules en dépassement par toute la surface brûlable paraît naturel, mais une
cellule sans donnée ce jour-là ne peut rien dépasser. Le chiffre baisse alors quand la
donnée manque, pas quand la météo se calme.

Mesuré sur l'année 2018 du banc d'essai :

| Mois | Couverture | Fraction sur surface totale | Fraction sur surface observée |
|---|---|---|---|
| Janvier | 0,577 | 0,096 | 0,167 |
| Avril | 0,680 | 0,061 | 0,089 |
| Juillet | 0,966 | 0,197 | 0,204 |
| Octobre | 0,768 | 0,082 | 0,105 |

Le rapport juillet/janvier vaut **2,05** avec le dénominateur brut et **1,23** avec le
dénominateur observé. Autrement dit, la moitié du cycle saisonnier apparent venait de la
disponibilité des données, pas du feu. La table publie donc les deux ingrédients :

- `global` et `region_k` : fraction de la surface brûlable **totale** (la définition de la
  littérature, comparable aux chiffres publiés) ;
- `coverage` et `region_k_cov` : part de cette surface qui avait une donnée ;
- la fraction sur surface **observée** est simplement le quotient des deux.

Le jeu Dryad, calculé sur ERA5 avec hivernage, devrait être proche de 1 partout ; c'est
précisément ce que la colonne `coverage` permettra de vérifier au lieu de le supposer.

## Pourquoi le mois

L'animation cible fait défiler 46 ans en 60 à 90 secondes, soit 12 à 24 mois par seconde.
Le pas mensuel est donc exactement la cadence d'affichage, et « nombre de jours extrêmes
dans le mois » est une grandeur lisible : 0 = rien, 31 = tout le mois en conditions
extrêmes. Les valeurs quotidiennes ne sont conservées qu'agrégées spatialement (série
d'étendue), ce qui divise le volume par ~30.

## Règles de comptage

- Comparaison **stricte** : `FWI > seuil`. Une valeur exactement égale au seuil n'est pas
  extrême (cohérent avec la définition d'un percentile dépassé).
- Un seuil NaN (cellule sans aucune valeur finie dans la référence) est remplacé par +∞ :
  la cellule ne compte jamais.
- Un FWI manquant (NaN, ou négatif dans les fichiers qui codent l'océan ainsi) n'est jamais
  compté. Dans le jeu GEFF, les régions froides ont des jours manquants en hiver : c'est
  attendu et cela n'affecte pas le compte des jours extrêmes.
- Chaque jour n'est accepté qu'une fois, et seulement s'il appartient à l'année du fichier.
  Par défaut une année incomplète fait échouer la passe (`--allow-incomplete` pour les
  essais).

## Le compteur de simultanéité

La série d'étendue est ce qui alimentera le compteur « X % de la surface brûlable en météo
extrême » et, par différence entre mondes, « dont Y points attribuables au réchauffement ».
Par construction, sur la période de référence, la moyenne annuelle du global pour p90
tourne autour de 10 % dans le monde observé ; dans le monde contrefactuel elle doit être
plus basse, et l'écart doit croître au fil des décennies. C'est le premier test de
plausibilité à faire sur les données Dryad.

Sur le banc d'essai (seuils tirés de la seule année 1991, année 2018 du jeu GEFF), avec
une couverture moyenne de 0,754 :

| Seuil | sur surface totale | sur surface observée |
|---|---|---|
| p90 | 10,6 % | 13,6 % |
| p95 | 6,6 % | 8,5 % |
| p99 | 2,8 % | 3,6 % |

L'article va plus loin en définissant un jour de *synchronous fire weather* intrarégional
quand ≥ 30 % de la surface brûlable d'une région dépasse p90 ; cette statistique se déduit
directement de la table (colonne `region_k` ≥ 0,30).

## Performances

Environ **20 s par année et par monde** (lecture ≈ 16 s), contre 60 s avant optimisation.
Le gain vient de deux mesures prises sur les vraies données : les quantités constantes
(aires pondérées, régions, dénominateurs) sont calculées une fois par exécution, et la
boucle travaille sur les 185 301 cellules brûlables plutôt que sur le million de cellules
de la grille. Résultats identiques au bit près sur les 72 couples jour × seuil testés.

Pour 46 ans × 2 mondes : environ **30 minutes**. Le parallélisme par processus a été mesuré
et ne donne qu'un facteur 2 sur cette machine, la limite étant la bande passante mémoire et
la décompression NetCDF, pas le nombre de cœurs.

## Sources

- Définition de la synchronicité régionale : Yin et al. 2026, *Methods*.
- Pondération par cos(latitude) pour des moyennes spatiales sur grille régulière : voir par
  exemple la note NCAR *Climate Data Guide, Regridding and area weighting*
  (<https://climatedataguide.ucar.edu/climate-tools/regridding-overview>).
