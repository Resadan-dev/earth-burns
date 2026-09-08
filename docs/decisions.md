# Journal des décisions

Format court : contexte → décision → conséquence. Les entrées marquées **à revalider**
dépendent des notebooks des auteurs, accessibles une fois le jeton Dryad obtenu.

## D1 — Grille canonique unique (2026-09-07)
Deux produits d'entrée (Dryad, GEFF) et deux masques (GLDAS, GFED) arrivent avec des
orientations différentes. → Tout est ramené à lat +90→−90, lon −180→+179,75, et toute
grille non conforme est refusée. → Plus aucune réindexation en aval ; un test vérifie
l'alignement avec des valeurs qui encodent leur position.

## D2 — Percentiles par histogramme plutôt qu'exacts (2026-09-07)
Exact = 45 Go en RAM ou relectures multiples. → Histogramme à classes fixes (0,2 sous 80,
1,0 jusqu'à 300), une passe, 1,3 Go. → Erreur bornée par la largeur de classe, mesurée sur
3 000 cellules à chaque exécution et écrite dans les métadonnées.

## D3 — Un seul seuil pour les deux mondes (2026-09-07)
Le seuil vient du monde observé, période 1991–2020, comme dans l'article. → Le monde
contrefactuel est jugé avec le même seuil. → L'écart entre mondes est visible ; un seuil
propre à chaque monde l'annulerait par construction.

## D4 — Classes GLDAS brûlables : 1–10, 14, 18, 19 — **à revalider**
L'article parle de « forests, mixed cover, woodlands, shrublands, grasslands ». → La classe
14 (mosaïque cultures/naturel) est lue comme « mixed cover », les toundras boisée et mixte
sont incluses. → 185 301 nœuds, 19,8 % de la surface pondérée. Configurable dans
`config/pipeline.toml`.

## D5 — Vote à 4 voisins pour passer des cellules aux nœuds (2026-09-07)
Les masques sont à cellules (centres ±0,125°), ERA5 à nœuds. → Un nœud est brûlable si au
moins 2 de ses 4 cellules le sont ; hors emprise = non brûlable. → Conservateur, symétrique,
sans dépendance à une bibliothèque de regrillage.

## D6 — Valeur négative = manquante dans le lecteur (2026-09-07, **corrigée**)
Rédigée sur la croyance que le jeu GEFF n'avait pas de `_FillValue` décodable. Vérification
faite : l'attribut existe et xarray le décode, donc aucune valeur négative n'atteint la
règle. → La règle est conservée comme garde-fou explicite pour une source future sans
attribut, pas comme mécanisme principal. → Leçon retenue : une affirmation sur la forme des
données se vérifie sur les données, pas sur leur documentation.

## D7 — Pas de contournement de l'anti-bot Dryad (2026-09-07)
Le lien de téléchargement est derrière un défi JavaScript et l'API exige un jeton. → Le
pipeline utilise uniquement l'API officielle avec le jeton d'une application créée par
l'utilisateur ; les fichiers déposés à la main sont acceptés après vérification SHA-256.
→ Le téléchargement dépend d'une action de l'utilisateur, documentée dans
[01-data-sources.md](01-data-sources.md).

## D8 — Comptage mensuel en uint8, pas de valeurs quotidiennes spatialisées (2026-09-07)
L'animation tourne à 12–24 mois/s. → On conserve le nombre de jours au-dessus de p90/p95/p99
par mois, et les séries quotidiennes uniquement agrégées (global + 14 régions). → Volume
divisé par ~30, sans perte pour la narration prévue.

## D9 — Découpage par décennie côté web (2026-09-07)
Charger 552 images à 0,25° saturerait la mémoire GPU mobile. → Blobs brotli par décennie
et par seuil, cellules brûlables seulement, frame-major. → ~1,1 Mo pour 12 mois × 3 seuils
sur le banc d'essai, soit 60–80 Mo estimés pour 46 ans × 2 mondes, chargés à la demande.

## D10 — Accumulateurs mutables, tout le reste immuable (2026-09-07)
La règle maison interdit la mutation. → Exception explicite et documentée pour
`StreamingHistogram` et `MonthlyExceedance`, dont l'unique rôle est d'accumuler en place.
→ Les fonctions publiques renvoient des copies ; les tests de reprise (`from_counts`)
garantissent que l'état interne reste reconstructible.


## D11 — Deux dénominateurs pour l'étendue, plus la couverture (2026-09-07)
Diviser les cellules en dépassement par **toute** la surface brûlable fait baisser le
chiffre quand la donnée manque, pas quand la météo se calme. Mesuré sur 2018 (GEFF) : la
couverture passe de 0,577 en janvier à 0,966 en juillet, si bien que le rapport
juillet/janvier valait 2,05 avec le dénominateur brut contre 1,23 avec le dénominateur
observé. → La table publie `global` (surface totale), `coverage` (part avec donnée) et
leurs équivalents par région ; la fraction sur surface observée est le quotient des deux.
→ Le cycle saisonnier affiché n'est plus un artefact de disponibilité.

## D12 — Un seul module décide des noms de fichiers (2026-09-07)
Chaque commande épelait ses propres noms puis les retrouvait par glob et expression
régulière, si bien qu'une reprise partielle laissait cohabiter deux tables d'étendue et
que la plus ancienne gagnait. → `layout.py` nomme tout, et l'étendue est écrite par année
comme les comptages. → Une reprise écrase exactement ce qu'elle remplace.

## D13 — L'index de cellules est partagé, donc verrouillé (2026-09-07)
Les blobs web ne stockent que les cellules brûlables : changer le masque après en avoir
empaqueté un rend les anciens illisibles sans aucun signe. → `write_grid` refuse un index
de taille différente tant qu'un monde figure au manifeste, sauf `--force`. → Le paquet
reste cohérent ou l'échec est immédiat.

## D14 — Identification stricte de la variable FWI (2026-09-07)
Le repli « la seule variable 3-D » acceptait un fichier ne contenant que le code de
sécheresse et le traitait comme du FWI. → Seul un nom connu est accepté ; le repli existe
encore mais doit être demandé explicitement. → Un test vérifie désormais le choix parmi
six variables 3-D, ce que l'ancien test ne pouvait pas faire.

## D15 — La passe 1 vérifie ce qu'elle a lu (2026-09-07)
Elle ignorait les dates : un fichier tronqué ou dupliqué biaisait tous les seuils en
silence, alors que la passe 2 refusait la même entrée. → Chaque jour est enregistré, un
doublon lève une erreur, une période incomplète aussi sauf `--allow-incomplete`, et le
décompte est écrit dans les métadonnées du fichier de seuils.


## D16 — Décoder soi-même l'axe temporel des fichiers Dryad (2026-09-08)
Leur unité `days_since_Jan11900` n'est pas conforme CF et fait échouer l'ouverture xarray.
→ Ouverture avec repli sans décodage temporel, puis lecture d'une variable compagnon
portant des décalages en jours depuis une origine, forme CF classique comprise. → Les deux
sources et les fichiers synthétiques passent par le même chemin, sans branche par produit.

## D17 — Une année courte en fin de course n'est pas une erreur (2026-09-08)
Les fichiers Dryad contiennent 365 pas quels que soient les jours du calendrier, si bien
que douze années perdent leur 31 décembre. Refuser ces années aurait imposé
`--allow-incomplete` en permanence, donc désarmé la vérification. → Distinction explicite :
un jour manquant **entre deux jours lus** reste une erreur, un arrêt anticipé est toléré,
signalé, et le nombre de jours observés par mois est enregistré dans la sortie. → La
vérification garde son pouvoir de détection sans crier au loup sur une convention.

## D18 — L'axe des dates est publié, plus déduit (2026-09-08)
La série d'étendue supposait un jour par ligne depuis la première date. Avec douze 31
décembre absents, cette hypothèse décalait silencieusement toutes les dates suivantes.
→ Le paquet web embarque désormais les décalages en jours, un entier par ligne, et le
manifeste compte les ruptures. → L'hypothèse positionnelle disparaît au lieu d'être
vérifiée, ce qui supprime la classe de bug plutôt qu'un cas.

## D19 — Lire par blocs alignés sur le fichier (2026-09-08)
Les fichiers Dryad sont découpés par 73 jours ; lire par 32 décompressait deux fois chaque
bloc. → La taille de lecture vient désormais du découpage déclaré par le fichier lui-même.
→ Moitié moins de temps de lecture, sans constante codée en dur.


## D20 — Compression brotli au niveau 9, pas 11 (2026-09-08)
Mesuré sur un vrai bloc de dix ans, 22,2 Mo bruts : niveau 9 donne 3,77 Mo en 3,1 s,
niveau 11 donne 3,44 Mo en 50,2 s. → Niveau 9 par défaut, réglable par `--quality`. → Le
paquet complet passe de 25 minutes à 4 minutes pour 10 Mo de plus sur 72, soit 0,4 Mo par
blob que le client charge décennie par décennie.


## D21 — Écrire le rendu à la main plutôt que prendre une bibliothèque (2026-09-08)
Le besoin tient en une projection, une rampe et une interpolation entre deux images.
→ WebGL2 direct, 121 lignes de GLSL, aucune dépendance ni étape de build. → Le paquet
sert des octets bruts au navigateur et rien ne s'interpose ; la contrepartie assumée est
d'écrire soi-même l'inverse d'Equal Earth.

## D22 — Disperser « jours + 1 » dans la texture (2026-09-08)
Une valeur 0 ne distinguait pas la mer d'une terre sans jour extrême, si bien que les
continents disparaissaient dès qu'ils étaient calmes. → La dispersion écrit `jours + 1`
et réserve 0 au « hors masque ». → Les continents restent lisibles sans embarquer de
couche de terres, pour un octet et aucune donnée supplémentaire.

## D23 — Deux cartes entières, jamais un balayage (2026-09-08)
La première vue « côte à côte » coupait un planisphère au milieu : on comparait les
Amériques du monde observé à l'Asie du contrefactuel. → Deux planisphères complets
superposés, un par monde. → La comparaison porte sur ce qu'elle prétend comparer.

## D24 — Dire « pas encore chargé » plutôt que montrer du vide (2026-09-08)
Sauter vers une décennie absente affichait une carte vide à côté de compteurs justes,
ce qui se lit comme « rien ne brûle ». → L'horloge s'arrête et un bandeau l'annonce.
→ Même principe que la couverture en D11 : l'absence de donnée se dit, elle ne se
présente pas comme une valeur.

## D25 — Anglais par défaut, français au choix, jamais deviné (2026-09-08)
Le multilingue devait couvrir français et anglais, anglais par défaut, quelle que soit la
langue du navigateur. → Un dictionnaire unique dans `web/src/i18n.js`, deux boutons EN/FR
toujours visibles dans l'en-tête, et un choix persisté en `localStorage` uniquement après un
clic explicite. `getInitialLang()` ne lit jamais `navigator.language`. → Un visiteur
francophone voit l'anglais à la première visite, exactement comme demandé.

## D26 — Un dictionnaire, pas des chaînes éparpillées (2026-09-08)
Chaque texte visible (titres, légendes, aria-labels, les cinq faits de la modale générale,
les noms de mois) vit dans `i18n.js`, jamais codé en dur dans `index.html` ou `main.js`.
`renderStaticText(lang)` réapplique tout d'un coup, au démarrage et à chaque changement de
langue. → Ajouter une langue plus tard revient à ajouter un objet, pas à chercher du texte
dispersé dans quatre fichiers.

## D27 — « The difference » est le mode par défaut (2026-09-08)
Les trois autres vues construisent la compréhension nécessaire, mais la carte de différence
est le message. → `DEFAULT_MODE = 2`, et le libellé du bouton garde une teinte ambre
atténuée même hors sélection, pour rester repérable dans la liste avant toute interaction.
→ Un visiteur qui ne clique jamais voit quand même le résultat le plus parlant. **Revu en
D30** : la teinte seule ne suffisait pas, la structure de la navigation a été revue.

## D28 — Deux liens de crédit, pas une citation en prose (2026-09-08)
« Calculé par des chercheurs » sans lien ne crédite personne. → La modale générale porte
deux liens distincts vers les résolveurs DOI de l'étude et du jeu de données, ouverts dans
un nouvel onglet avec `rel="noopener noreferrer"`. → Le lecteur remonte directement à la
source plutôt qu'à une reformulation, et les auteurs sont crédités sans risque de mal
orthographier une liste de noms dans le texte de l'application.

## D29 — Un incident de heredoc redevient un script Python vérifié (2026-09-08)
Deux tentatives d'écriture de `i18n.js` par heredoc Bash ont échoué ou corrompu le bloc
anglais (le mot « emissions » existe dans les deux langues, un remplacement global sur tout
le fichier a traduit des mots anglais par erreur). → Reconstruction complète par blocs
heredoc plus courts, accents écrits directement dans le texte plutôt que restaurés après
coup, et une vérification programmatique (recherche de caractères accentués côté anglais,
recherche des chaînes françaises attendues) avant de continuer. → La leçon rejoint D15
de la passe pipeline : vérifier sur les données réelles, jamais sur ce qu'on croit avoir
écrit.

## D30 — La structure porte l'emphase, pas la seule couleur (2026-09-08)
Une teinte ambre discrète sur « The difference » ne suffisait pas : le texte d'introduction
décrivait encore « deux planètes » alors que la vue par défaut est la carte de différence,
et rien ne distinguait clairement les trois autres modes comme secondaires. → « The
difference » occupe sa propre ligne, en tête de la navigation, en plus grand ; les trois
autres sont regroupés sous une étiquette « The building blocks » / « Les briques de base »,
en plus petit. Le sous-titre décrit maintenant l'écart, pas les deux mondes séparés. →
`document.querySelectorAll(".mode-btn")` reste indépendant de l'ordre du DOM, donc ce
réarrangement n'a demandé aucun changement de logique, seulement de structure et de texte.

## D31 — La barre de défilement suit la palette (2026-09-08)
La modale générale peut déborder sur un écran bas, et le défilement natif de Windows,
gris et anguleux, tranchait avec l'instrument sombre construit autour. → `scrollbar-width`
et `scrollbar-color` pour Firefox, les pseudo-éléments `::-webkit-scrollbar-*` pour les
navigateurs Chromium, un fil fin coloré avec `--rule` au repos et `--muted` au survol,
sans boutons fléchés. → Détail mineur, mais visible à chaque ouverture d'une carte trop
longue pour l'écran.

## D32 — Une troisième modale pour les chiffres, pas une sixième ligne dans l'existante (2026-09-08)
La carte « Resolution » de la modale générale a plu précisément parce qu'elle mêlait un
chiffre concret à une phrase courte. → Un panneau dédié, déclenché par un lien discret sous
la légende des pourcentages, présente cinq statistiques en grille plutôt qu'en liste de
faits : deux colonnes, grand chiffre coloré au-dessus d'une légende d'une ligne. → Cinq
chiffres bien choisis se voient d'un coup d'œil ; noyés dans les cinq faits déjà denses de
la modale générale, ils se seraient perdus.

Chaque chiffre est sourcé, sans le dire dans l'interface pour ne pas alourdir la grille :
le doublement mondial et la part attribuable au réchauffement viennent de l'étude Science
Advances 2026 à l'origine du jeu de données ; le facteur 15 et les 8,5 jours en plus
viennent du calcul propre à ce pipeline sur la période 1979-2024 ([[fire-viz-pipeline-state]],
docs/06-first-results.md) ; la hausse de 60 % des émissions vient de Jones et al. 2024,
Science, une étude différente sur les mêmes régions. → Aucun de ces chiffres n'est inventé
ni arrondi au-delà de ce que permettent les données sources.

## D33 — Le crédit ne doit pas coûter deux clics (2026-09-08)
« Lire l'étude » et « Explorer les données » ne vivaient que dans les modales : un
visiteur qui n'ouvrait ni « ? » ni « Les chiffres » ne les voyait jamais, ce qui n'est pas
vraiment créditer les auteurs. → Les deux liens rejoignent « Les chiffres » sur l'interface
principale, sous la légende des pourcentages, en une seule ligne discrète. Ils restent
aussi dans les deux modales, redondance sans coût qui évite de fermer une carte pour
cliquer. → `renderLinks()` gagne un paramètre de classe et sert désormais trois
conteneurs au lieu de deux, sans dupliquer la logique de construction des liens.

## D34 — « The human fingerprint » remplace « The difference » (2026-09-08)
« La différence » décrit une opération, pas ce que le mode raconte. → Renommé en
« The human fingerprint » / « L'empreinte humaine », expression déjà établie en
communication scientifique sur le climat, qui garde la forme nominale courte des trois
autres noms de mode. Le corps du texte d'aide n'a pas changé : il explique déjà
correctement le mécanisme, seul le nom manquait de relief.

## D35 — Le texte d'aide du mode 2 doit nommer l'origine humaine, pas juste « warming » (2026-09-08)
Un visiteur a demandé si l'écart montré venait du réchauffement global ou de sa seule part
anthropique : question légitime, la modale d'aide de « The human fingerprint » disait « the
world without warming » alors que le contrefactuel retire spécifiquement le signal
d'origine humaine (méthode CMIP6, référence préindustrielle 1850-1900), en conservant la
variabilité naturelle. → Corps du texte modifié en anglais et en français pour dire
explicitement « the world without human-caused warming » / « le monde sans réchauffement
d'origine humaine », cohérent avec `twin.bottom` et `aboutHelp.facts` qui le disaient déjà
correctement. La modale était donc le seul endroit encore ambigu.

## D36 — Le crédit change de coin (2026-09-08)
« The numbers » / « Read the study » / « Get the data » vivaient en dernière ligne de
`.readout`, sous le mois, les deux pourcentages et la légende : la ligne la plus petite et
la moins contrastée de la page, sixième élément d'une colonne déjà dense. Un visiteur les a
trouvés peu visibles. → Sortis de `.readout` vers leur propre bloc fixe, ancré à droite en
miroir de la nav, aligné à droite (`justify-content: flex-end`), à la même hauteur que
l'ancienne ligne de crédit. `.readout` perd sa dernière ligne et remonte son offset bas de
4,2rem à 2,8rem pour garder l'écart original au-dessus du bandeau de lecture. Résultat :
quatre coins distincts (titre, nav, lecture, crédit) autour de la carte plutôt qu'une
colonne gauche à six niveaux. Vérifié en desktop et aux deux points de rupture mobiles
existants (portrait à `top:62%`, paysage à `bottom` fixe) : aucun chevauchement.
