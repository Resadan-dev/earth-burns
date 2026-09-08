# 06 — Premiers résultats sur la série complète

Calculé le 2026-09-08 sur les 92 fichiers Dryad, 1979–2024, seuils locaux p90 issus de la
période 1991–2020 du monde observé et appliqués aux deux mondes.

## La part du monde brûlable en météo extrême

Moyenne annuelle de la fraction de surface brûlable, pondérée par la latitude, dont le FWI
dépasse son 90e percentile local :

| Période | Notre monde | Sans réchauffement anthropique | Écart |
|---|---|---|---|
| 1979–1990 | 7,70 % | 7,13 % | +0,57 point |
| 1991–2002 | 8,44 % | 7,41 % | +1,03 point |
| 2003–2013 | 10,37 % | 8,65 % | +1,72 point |
| 2014–2024 | 11,97 % | 9,51 % | +2,46 point |

En 2024, dernière année de la série, 14,09 % contre 11,14 %. L'écart a été multiplié par
plus de quatre en quarante-six ans, et il croît de façon presque monotone.

Par construction, la moyenne du monde observé sur 1991–2020 doit avoisiner 10 %, puisque le
seuil est le 90e percentile de cette période. C'est un contrôle utile : la valeur obtenue,
9,4 %, en est proche, l'écart restant venant de la pondération par la surface et du masque.

## Les tendances

| Série | Pente | Erreur type |
|---|---|---|
| Notre monde | +1,274 point par décennie | 0,075 |
| Sans réchauffement | +0,727 point par décennie | 0,062 |

Le rapport des deux pentes place **43 % de la tendance observée** du côté du réchauffement
anthropique. Ce chiffre est une lecture directe de ce jeu de données, pas une reproduction
de la méthode d'attribution de l'article, qui procède autrement.

Un point mérite d'être dit franchement : **le monde contrefactuel monte lui aussi**. Ce
n'est pas une anomalie. Le contrefactuel ne retire que le signal de premier ordre lissé sur
vingt ans, moyenné sur vingt modèles CMIP6. Il laisse en place la variabilité interne, tout
écart entre la réponse d'ERA5 et celle des modèles, et les changements d'usage des sols.
Présenter le monde bleu comme « la planète stable » serait donc faux. Ce que la comparaison
autorise, c'est de dire que l'écart entre les deux croît, pas que l'un serait immobile.

## La simultanéité régionale

Nombre de jours par an où au moins 30 % de la surface brûlable d'une région dépasse son
p90, critère de l'article, dans le monde observé :

| Région GFED | 1979–1990 | 2013–2024 | Facteur |
|---|---|---|---|
| Amérique du Sud, hémisphère sud | 4,0 | 59,7 | 14,9 |
| Asie centrale | 2,8 | 25,6 | 9,3 |
| Afrique, hémisphère sud | 7,1 | 40,2 | 5,7 |
| Moyen-Orient | 19,9 | 61,9 | 3,1 |
| Amérique du Nord tempérée | 9,8 | 29,6 | 3,0 |
| Amérique centrale | 13,3 | 39,1 | 2,9 |
| Europe | 17,9 | 44,3 | 2,5 |
| Afrique, hémisphère nord | 25,3 | 56,0 | 2,2 |

Toutes les régions de ce tableau ont plus que doublé, ce qui recoupe la conclusion publiée
d'un doublement dans la plupart des régions du monde. La progression de l'Amérique du Sud
australe, presque quinze fois, est la plus spectaculaire de la série.

## Où l'écart se loge

Sur la dernière décennie, notre monde compte en moyenne **8,5 jours extrêmes de plus par an
et par cellule brûlable** que le monde sans réchauffement. La carte de cet écart montre des
maxima sur l'Amazonie, l'Amérique centrale, le pourtour méditerranéen, l'ouest de l'Amérique
du Nord et l'Australie.

Elle montre aussi des zones **bleues**, principalement en Afrique centrale et australe, où
notre monde compte *moins* de jours extrêmes que le contrefactuel. Ce n'est pas un artefact
de calcul : le signal climatique retiré comprend aussi des changements de précipitations,
qui vont localement dans le sens d'une humidité accrue. Une dataviz honnête doit les
montrer plutôt que de les écrêter, sous peine de transformer une carte en argument.

## Vérifications passées

- Les 101 fichiers Dryad ont une empreinte SHA-256 conforme au manifeste.
- La couverture des données sur le masque brûlable est de **99,98 %, tous les jours de tous
  les ans**, l'hivernage éliminant les trous hivernaux qui affectaient le banc d'essai.
- Le paquet web se décode à l'identique de sa source, comparaison faite frame à frame sur
  l'année 1979.
- L'axe des dates compte 16 790 jours pour 16 801 jours calendaires, soit exactement les
  11 ruptures attendues des 31 décembre absents.
- Le contrôle de plausibilité de 2020 place en tête l'Amérique du Sud australe, l'Amazonie,
  l'Amérique du Nord tempérée et l'Asie boréale, soit le Pantanal, la côte ouest américaine
  et la Sibérie, qui ont effectivement marqué cette année-là.

## Le paquet web

| Élément | Valeur |
|---|---|
| Taille totale | 72 Mo |
| Blobs | 35 |
| Cellules brûlables | 185 301 |
| Images mensuelles | 552 par monde et par seuil |
| Série d'étendue | 16 790 jours × 3 seuils × 30 colonnes |
| Temps d'empaquetage | 4 minutes pour les deux mondes |
