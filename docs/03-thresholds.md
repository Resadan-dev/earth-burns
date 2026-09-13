# 03 : Passe 1, les seuils locaux (p90, p95, p99)

## Pourquoi un seuil par cellule, et pas un seuil mondial

Un FWI de 30 est banal dans le bush australien et exceptionnel en Scandinavie. Comparer
chaque cellule à **sa propre climatologie** est ce qui permet de voir le Canada ou la
Sibérie « s'allumer » au même titre que la Méditerranée. L'article définit l'extrême comme
le dépassement du 90ᵉ percentile local calculé sur la période de référence 1991–2020, sur
le monde observé ; nous reprenons exactement cette définition et ajoutons p95 et p99 pour
les paliers visuels.

Le **même seuil est appliqué aux deux mondes**. C'est volontaire : si l'on recalculait un
seuil propre au contrefactuel, chaque monde aurait par construction 10 % de jours extrêmes
et la différence disparaîtrait. Avec un seuil commun, le monde sans réchauffement dépasse
moins souvent, et c'est cet écart que la dataviz montre.

## Le problème de mémoire

Un percentile exact demande de trier, pour chaque cellule, ses ~10 957 valeurs
quotidiennes (30 ans). Pour 1 038 240 cellules cela représente 45 Go en float32, ou des
dizaines de relectures des fichiers compressés. Ni l'un ni l'autre n'est raisonnable sur
un poste de travail.

## La solution : un histogramme par cellule, en flux

`histogram.StreamingHistogram` conserve pour chaque cellule un histogramme à classes fixes :

- classes de **0,2** entre 0 et 80 (là où vivent presque tous les seuils),
- classes de **1,0** entre 80 et 300,
- une classe de débordement au-delà de 300 (valeurs observées jusqu'à ~280 dans les déserts).

Soit 621 classes × 1 038 240 cellules en `uint16` = **1,29 Go** en mémoire, et une seule
lecture des fichiers. Chaque jour, `numpy.searchsorted` place le million de valeurs dans
leur classe et une indexation directe incrémente les compteurs : chaque cellule n'apparaît
qu'une fois par jour, donc l'incrément vectorisé est exact.

Le percentile est ensuite lu dans les comptes cumulés : on repère la classe qui contient le
rang cherché et on interpole linéairement à l'intérieur, en supposant les valeurs
uniformément réparties dans la classe. Le rang suit la convention « linear » de
`numpy.percentile` (interpolation entre les statistiques d'ordre k et k+1), ce qui rend la
comparaison avec le calcul exact directe. **L'erreur est bornée par la largeur de la
classe** : au plus 0,2 unité de FWI sous 80, au plus 1,0 au-dessus.

## Validation intégrée

Pendant la même passe, 3 000 cellules tirées au hasard (graine fixée) conservent leur série
complète (3 000 × 10 957 × 4 octets ≈ 130 Mo). À la fin, le percentile exact de ces cellules
est comparé à l'estimation et le rapport est écrit dans les attributs du fichier de seuils.

Résultat du banc d'essai sur l'année 1991 seule (365 valeurs par cellule) :

| Seuil | erreur max | erreur moyenne | p99 de l'erreur |
|---|---|---|---|
| p90 | 0,54 | 0,049 | 0,30 |
| p95 | 0,64 | 0,064 | 0,40 |
| p99 | 0,52 | 0,074 | 0,41 |

Les maxima viennent des cellules dont le seuil tombe dans les classes larges (FWI > 80) :
l'erreur reste sous la borne théorique de 1,0. Avec 30 ans de données l'interpolation
s'affine encore. Le tableau sera mis à jour après la passe sur Dryad 1991–2020.

Une subtilité mise au jour par les tests : le seuil estimé peut se situer légèrement
au-dessus de la vraie valeur (à l'intérieur de la classe). Une journée dont le FWI vaut
exactement le percentile n'est donc pas forcément comptée comme extrême. Sur des données
réelles continues, l'effet est négligeable ; sur des données synthétiques constantes il est
visible, d'où le test `test_pipeline_small.py` qui le documente.

## Performances mesurées

Sur le fichier GEFF-ERA5 1991 (chunks NetCDF d'un jour, gzip 9) : 16 s pour lire et
histogrammer 365 jours, 25 s pour extraire les trois quantiles. Extrapolation pour
1991–2020 : environ 8 min de lecture et le même temps de calcul final.

## Ce que la passe vérifie

Les seuils conditionnent tout le reste, donc la passe refuse ce qu'elle ne peut pas
justifier. Chaque jour lu est enregistré : un jour vu deux fois (le même fichier passé
deux fois, un doublon de téléchargement) lève une erreur, et une période de référence
trouée aussi, sauf `--allow-incomplete`. Le décompte réel, la première et la dernière date
et la liste des jours manquants sont écrits dans les attributs du fichier de seuils, si
bien qu'on peut toujours savoir sur quoi une climatologie a été calculée.

Sans cette vérification, un fichier tronqué produisait des seuils biaisés sans un mot,
alors que la passe 2 refusait exactement la même entrée.

## Sorties

`data/interim/thresholds_<source>_<y0>-<y1>.nc` :

| Variable | Dimensions | Contenu |
|---|---|---|
| `threshold` | quantile, lat, lon | seuils float32 (NaN si aucune valeur finie) |
| `count` | lat, lon | nombre de jours finis par cellule |
| `overflow` | lat, lon | 1 si la cellule a vu des valeurs ≥ 300 |
| attributs | | fichiers utilisés, couverture temporelle, rapport de validation (JSON) |

## Sources

- Définition de l'extrême et période de référence : Yin et al. 2026, section *Methods*
  (<https://pmc.ncbi.nlm.nih.gov/articles/PMC12915598/>).
- Convention de quantile : documentation `numpy.percentile`, méthode `linear`
  (Hyndman & Fan 1996, définition 7).
- Approche par histogrammes pour les quantiles en flux : Ben-Haim & Tom-Tov, *A Streaming
  Parallel Decision Tree Algorithm*, JMLR 11, 2010 (l'idée d'estimer des quantiles à partir
  d'histogrammes compacts).
