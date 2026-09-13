# 02 : Grille, poids de surface et masques

## La grille canonique

ERA5 est une grille **à nœuds** : les valeurs sont définies aux latitudes 90, 89,75, …,
−90 (721 lignes) et aux longitudes 0, 0,25, …, 359,75 (1440 colonnes). Le pipeline impose
une orientation unique, dite canonique : latitude décroissante de +90 à −90, longitude
croissante de −180 à +179,75. `grid.to_canonical` renomme les dimensions (insensible à la
casse, `Latitude` comme `lat`), retourne l'axe des latitudes si besoin, recale les
longitudes 0–360 en −180–180 et **refuse** toute grille qui ne correspond pas. Ces
opérations sont de simples permutations d'index : xarray les applique paresseusement,
sans charger le fichier.

## Pondérer par la surface

Sur une grille régulière en degrés, une cellule à 60° de latitude couvre deux fois moins de
surface qu'à l'équateur. Toute statistique « fraction de surface » utilise donc le poids
cos(latitude), calculé une fois (`grid.cos_lat_weights`) et stocké dans `masks.nc` sous
`cell_weight`. Sans cette pondération, la Sibérie et le Canada pèseraient trop lourd dans
le compteur de simultanéité.

## Le masque « brûlable »

L'article restreint l'analyse aux *burnable wildland areas* : forêts, couvert mixte, bois,
arbustes et prairies, à l'exclusion des cultures, des sols nus et des zones urbaines. Sans
ce masque, le Sahara ou l'Arabie, où le FWI est structurellement énorme, domineraient la
carte.

Source : classes dominantes de végétation GLDAS (Noah, « Modified IGBP », 20 classes).
Correspondance retenue, configurable dans `config/pipeline.toml` :

| Code | Classe | Brûlable ? |
|---|---|---|
| 1–5 | forêts (aiguilles/feuilles, persistantes/caduques, mixtes) | oui |
| 6–7 | arbustes fermés / ouverts | oui |
| 8–9 | savanes boisées / savanes | oui |
| 10 | prairies | oui |
| 11 | zones humides permanentes | non |
| 12 | cultures | non |
| 13 | urbain | non |
| 14 | mosaïque cultures / végétation naturelle | **oui** (lu comme le « mixed cover » de l'article) |
| 15 | neige et glace | non |
| 16 | sols nus ou peu végétalisés | non |
| 18–19 | toundra boisée / mixte | **oui** (végétalisée, feux de toundra documentés) |
| 20 | toundra nue | non |
| 0 | eau / manquant | non |

Deux décisions restent des interprétations : la classe 14 et les toundras 18–19. Elles
sont isolées dans la configuration pour être ajustées si les notebooks des auteurs,
téléchargeables avec le jeton Dryad, tranchent autrement.

### Passer d'une grille à cellules à une grille à nœuds

GLDAS et GFED sont des grilles **à cellules** : centres à ±0,125°, ±0,375°… Chaque nœud
ERA5 tombe donc exactement au coin de quatre cellules. Deux règles, dans `mask.py` :

- **masque booléen** : vote des quatre voisines ; le nœud est brûlable si au moins la
  moitié le sont (`vote_threshold = 0.5`). Une voisine hors de l'emprise (GLDAS s'arrête à
  −60°, donc pas d'Antarctique ; la ligne 90° N n'a que deux voisines) compte comme
  non brûlable : le résultat est conservateur ;
- **identifiants de région** : la cellule nord-ouest, choix déterministe qui ne compte
  que sur les frontières entre régions.

Les deux règles gèrent le passage de la ligne de changement de date (−180 = 180).

### Résultat

Sur la grille canonique : **185 301 nœuds brûlables**, soit **19,8 % de la surface
terrestre pondérée** (les terres émergées représentent ~29 %). L'ordre de grandeur est
cohérent avec une carte mondiale de végétation naturelle hors déserts, glaces et cultures.

## Les régions GFED

Les 14 régions de base de la Global Fire Emissions Database (BONA, TENA, CEAM, NHSA, SHSA,
EURO, MIDE, NHAF, SHAF, BOAS, CEAS, SEAS, EQAS, AUST) sont lues dans
`GFED4.1s_1997.hdf5` (`ancill/basis_regions`, avec les noms en attributs) puis projetées
sur les nœuds. Elles servent au compteur de simultanéité : l'article définit un jour de
*synchronous fire weather* intrarégional quand au moins 30 % de la surface brûlable d'une
région dépasse son p90 le même jour.

## Sources

- NASA GLDAS, *Vegetation class / mask* : <https://ldas.gsfc.nasa.gov/gldas/vegetation-class-mask>
- Rodell M. et al., *The Global Land Data Assimilation System*, BAMS 85, 2004,
  doi:[10.1175/BAMS-85-3-381](https://doi.org/10.1175/BAMS-85-3-381)
- Giglio L. et al., *Analysis of daily, monthly, and annual burned area using the fourth
  generation GFED*, JGR Biogeosciences 118, 2013, doi:[10.1002/jgrg.20042](https://doi.org/10.1002/jgrg.20042)
- ECMWF, *ERA5: data documentation*, grille et conventions :
  <https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation>
