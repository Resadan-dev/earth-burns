# 07 — Le rendu WebGL

Application web sans dépendance ni étape de build : des modules ES natifs, un shader
écrit à la main, et un petit serveur Python pour le développement. Un peu plus de 1 100
lignes au total, dont 121 de GLSL.

```
web/index.html      structure
web/styles.css      direction visuelle
web/src/data.js     chargement et indexation du paquet
web/src/shaders.js  GLSL, projection et rampes de couleur
web/src/renderer.js WebGL2, textures, dessin
web/src/main.js     horloge, modes, interactions
scripts/serve_web.py serveur de développement
```

Lancer : `.venv/Scripts/python.exe scripts/serve_web.py --port 8123`, puis ouvrir
<http://127.0.0.1:8123>.

## Pourquoi aucune bibliothèque

Le besoin est étroit : une projection, une rampe, une interpolation entre deux images.
Aucune bibliothèque cartographique ne fait exactement cela sans imposer son modèle de
tuiles ou de couches, et toutes pèsent plus lourd que les 121 lignes de shader qui
suffisent ici. La contrepartie assumée est qu'il faut écrire la projection soi-même.

## Servir des blobs brotli sans décodeur

Les blobs sont compressés sur le disque. Le serveur les envoie avec l'en-tête
`Content-Encoding: br`, si bien que le navigateur les décompresse lui-même et que
`fetch` rend des octets bruts. Aucun décodeur en JavaScript, aucune copie de plus.

Le serveur est **multi-thread**. En mono-thread, les six requêtes parallèles du
démarrage se mettaient en file et la page paraissait bloquée ; c'était le premier bug
rencontré. Mesuré après correction : 238 ms pour le plus gros bloc, moins d'une seconde
pour les 14 Mo du démarrage.

## Du tableau creux à la texture

Le paquet ne contient que les 185 301 cellules brûlables, pas le million de la grille.
Chaque mois est donc dispersé une fois dans une grille pleine 1440 × 721 puis envoyé
comme texture à un canal. La dispersion écrit **`jours + 1`**, ce qui laisse la valeur 0
libre pour signifier « hors du masque ». C'est ce détail d'un octet qui permet de
dessiner les continents sans embarquer une couche de terres séparée : le shader
distingue la mer d'une terre au repos.

Quatre textures sont maintenues, deux mondes fois deux mois. Le mélange entre le mois
courant et le suivant se fait dans le shader, si bien qu'une seule dispersion par
changement de mois suffit, soit une vingtaine par seconde et non soixante.

## La projection

Equal Earth, inversée par itération de Newton dans le fragment shader. Le choix n'est
pas esthétique : la comparaison porte sur des **surfaces** de terres qui brûlent, et une
projection non équivalente comme Mercator gonflerait précisément les forêts boréales dont
parle une partie de l'histoire. Huit itérations suffisent largement à la précision d'un
pixel.

Chaque pixel remonte à sa longitude et sa latitude, puis lit la texture. Les pixels hors
du domaine prennent la couleur du fond, ce qui dessine la silhouette caractéristique de
la projection sans géométrie.

## Les trois lectures

| Mode | Ce qu'il montre |
|---|---|
| Notre monde | le monde observé seul |
| Sans réchauffement | le contrefactuel seul |
| Côte à côte | deux planisphères **complets**, l'un au-dessus de l'autre |
| La différence | observé moins contrefactuel, rampe divergente |

La vue côte à côte a d'abord été implémentée comme un balayage vertical au milieu de
l'écran. C'était une erreur de conception : à gauche de la ligne on voyait les Amériques
du monde observé et à droite l'Asie du contrefactuel, soit une comparaison entre deux
lieux, pas entre deux mondes. Elle dessine désormais deux cartes entières.

## Ce que l'interface refuse de faire

Quand la décennie demandée n'est pas encore chargée, l'horloge s'arrête et un bandeau
« loading this decade » apparaît. C'est délibéré : les compteurs viennent de la série
d'étendue, chargée en entier au démarrage, alors que la carte dépend d'un bloc qui peut
être en vol. Sans ce bandeau, une carte vide côtoyait des chiffres justes, ce qui se lit
comme « il ne s'est rien passé » au lieu de « ce n'est pas encore arrivé ». Le bug a été
trouvé en sautant à une décennie non chargée juste après le démarrage.

L'animation ne saute jamais un mois qu'elle n'a pas pu dessiner : le temps n'avance que
lorsque les textures correspondent au mois affiché.

## La dénominateur, encore

Le shader divise les jours par le nombre de jours **réellement observés** dans le mois,
transmis par le paquet. Les années bissextiles des fichiers Dryad n'ont pas de
31 décembre, si bien qu'un décembre sur quatre compte 30 jours. Sans cette division, ces
mois paraîtraient 3 % plus calmes qu'ils ne le sont.

## Interactions

- **Espace** joue et met en pause, les **flèches** avancent d'un mois.
- **Molette** pour zoomer autour du curseur, **glisser** pour déplacer, **0** pour
  revenir à la vue mondiale.
- Le curseur temporel couvre les 552 mois, gradué par décennie.

## Sources

- Šavrič B., Patterson T., Jenny B. (2018), *The Equal Earth map projection*,
  International Journal of Geographical Information Science,
  doi:[10.1080/13658816.2018.1504949](https://doi.org/10.1080/13658816.2018.1504949)
- Formules directes et inverse : <https://equal-earth.com>
