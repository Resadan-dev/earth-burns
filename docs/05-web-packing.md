# 05 : Empaquetage pour le navigateur

## Budget

Le client doit animer 552 mois × 2 mondes × (au moins) un seuil. Trois décisions ramènent
le volume dans un budget raisonnable :

1. **Ne stocker que les cellules brûlables** : 185 301 sur 1 038 240, soit 18 % de la
   grille. Le reste est noir de toute façon.
2. **Un octet par cellule et par mois** (nombre de jours extrêmes, 0–31).
3. **Brotli** sur des données très creuses (la plupart des mois valent 0 presque partout).

Ordre de grandeur brut : 552 × 185 301 ≈ 102 Mo par monde et par seuil. Mesuré sur le banc
d'essai (12 mois × 3 seuils + index des cellules + série d'étendue) : **1,1 Mo**, soit
~22 Ko par mois et par seuil, donc 10 à 15 Mo par seuil pour 46 ans et **60 à 80 Mo** pour
les deux mondes et les trois seuils, chargés décennie par décennie. À confirmer sur Dryad.

## Disposition des fichiers (`data/web/`)

```
<source>/grid.json                        nlat, nlon, lat0, lon0, step, n_cells
<source>/cells.bin.br                     int32 × n_cells : index des cellules brûlables
<source>/<monde>/<seuil>/<y0>-<y1>.bin.br uint8 × (n_mois × n_cells), une décennie par blob
<source>/extent/<monde>.bin.br            uint16 × (n_jours × n_seuils × 30)
<source>/manifest.json                    tout ce que le client doit savoir pour décoder
```

Le paquet est rangé **par source** : mélanger un blob du banc d'essai et un blob Dryad sous
un même manifeste produisait un jeu incohérent étiqueté d'une seule source.

Chaque blob de frames est **frame-major** : les `n_cells` octets du mois 0, puis ceux du
mois 1, etc. Le client peut ainsi copier une tranche contiguë dans une texture sans
réarrangement. Le découpage par décennie permet de ne charger que ce qui est affiché et de
libérer la mémoire GPU derrière soi ; la taille du chunk est un paramètre
(`--chunk-years`).

## Reconstruction côté client

```js
const cells = new Int32Array(await brotliDecode("cells.bin.br"));   // n_cells
const blob  = new Uint8Array(await brotliDecode("observed/p90/1979-1988.bin.br"));
const month = 6;                                                     // 7e mois du blob
const frame = blob.subarray(month * cells.length, (month + 1) * cells.length);
// frame[i] = jours extrêmes de la cellule cells[i] ; ligne = cells[i] / 1440, colonne = cells[i] % 1440
```

Les navigateurs décompressent brotli nativement quand le serveur envoie
`Content-Encoding: br`. Servir les blobs déjà compressés avec cet en-tête évite toute
bibliothèque de décompression côté client.

## Séries d'étendue

`extent/<monde>.bin.br` contient, pour chaque jour depuis le premier jour couvert,
`n_seuils × 30` valeurs `uint16` multipliées par 10 000 (précision 0,01 point) : la fraction
globale, la couverture globale, puis pour chacune des 14 régions GFED sa fraction et sa
couverture. Les métadonnées du manifeste donnent l'ordre exact des colonnes, celui des
seuils, la première et la dernière date. Seule une région sans surface brûlable est codée 0.

## Ce que l'empaquetage refuse de faire

La disposition est **positionnelle** : le client déduit le mois d'un index et la date du
premier jour plus un décalage. Trois situations la rendraient silencieusement fausse, et
chacune lève désormais une erreur au lieu d'être absorbée :

- une **année manquante** entre la première et la dernière (`pack_monthly`) ;
- un **jour manquant** dans la série d'étendue, ou un seuil ayant moins de lignes que de
  jours (`pack_extent`) ;
- un **index de cellules différent** de celui contre lequel des blobs ont déjà été écrits
  (`write_grid`), à moins de passer `--force` en acceptant de tout réempaqueter.

Auparavant les deux premières produisaient une série décalée d'un jour ou des zéros
indiscernables d'un vrai calme, et la troisième laissait des cartes s'afficher sur les
mauvaises cellules.

## Ce que le manifeste garantit

- `worlds.<monde>.years` : première et dernière année disponibles ;
- `worlds.<monde>.thresholds.<seuil>` : liste ordonnée des blobs avec `first_year` et
  `n_months`, donc l'index absolu de chaque mois se calcule sans ouvrir le blob ;
- `worlds.<monde>.extent` : forme, échelle, colonnes, dates ;
- `region_names` : libellés GFED pour l'interface.

## Sources

- Format brotli : RFC 7932 (<https://www.rfc-editor.org/rfc/rfc7932>).
- Encodage de contenu `br` dans les navigateurs : MDN, *Content-Encoding*
  (<https://developer.mozilla.org/docs/Web/HTTP/Headers/Content-Encoding>).
