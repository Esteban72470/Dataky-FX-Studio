# Dataky FX Studio · demandes de Claude, lot 2 (2026-10-22)

Suite de `DEMANDES_CLAUDE.md` et de `RAPPORT_DEMANDES_CLAUDE.md`. Claude a vérifié le lot 1 :
- 82/82 tests JavaScript passent, y compris le vrai rendu Chromium : Playwright est disponible sur cette machine, hors du bac à sable ;
- 113 tests Python passent ;
- l'éditeur fonctionne : mode Libre, Maj+E, T, aide `?`.

Deux points restent à corriger. Les règles de travail du lot 1 s'appliquent toujours :
- pas de git, et la sauvegarde d'avant le lot 1 existe déjà ;
- ne pas toucher au catalogue ;
- garder la compatibilité ;
- lancer tous les tests.

## Fixtures fournies

`tool/fixtures/bulbito/` contient les 18 pièces d'effets réelles de l'unité Bulbito Bandito Traktorito, qui ont toutes été jouées en Play dans Roblox Studio, ainsi que :
- `Pillar_InvisibleInPlay.json` : l'ancienne version de A2_Flare, dont l'émetteur `Burst` (« Upwards flame pillar », `70418763522849`, OneShot 4x4, Lifetime 0,45) était **invisible en Play** ;
- `play_observations.json` : ce qui a été **vu** en Play (`visible`), ce qui a **échoué** (`invisible`) et ce qui n'a pas été vérifié (`unknown`).

Ces fichiers sont des observations réelles. Utilise-les comme tests de régression : ne les modifie pas pour faire passer un test.

## 1. Avertissements trop bruyants

Sur ces 18 pièces, `fx.py validate` sort aujourd'hui 132 avertissements :

| Code | Nombre |
| --- | --- |
| abrupt_size | 58 |
| estimated_grid | 51 |
| flipbook_low_opacity | 8 |
| pale_small_texture | 7 |
| abrupt_transparency | 5 |
| flipbook_empty_start | 2 |
| additive_white | 1 |

Les vrais problèmes se perdent dans ce bruit.

### 1a. `abrupt_size`
Il se déclenche sur presque toutes les fumées et poussières, alors que leur `Transparency` finit à 1. Une taille finale non nulle ne se voit pas si la particule a déjà fondu. Règle demandée : signaler `abrupt_size` **seulement si la Transparency de fin est < 0,95**, soit le même seuil que `abrupt_transparency`, documenté au même endroit.

Attendu : 0 `abrupt_size` sur les fixtures Bulbito.

### 1b. `estimated_grid`
Presque toutes les grilles du catalogue sont marquées `estimated`, donc l'avertissement sort sur presque tout le monde, une fois par émetteur. Demande :
- le passer en niveau **info**, masqué par défaut et visible avec `--verbose` ou `--infos` (CLI, et option MCP équivalente) ;
- le dédoublonner : **une ligne par texture**, pas une par émetteur ;
- permettre de **confirmer une grille** à la main, par exemple `fx.py grid-confirm <id> 4`, enregistré dans un fichier de surcharges hors catalogue (`tool/grid_overrides.json`). Une grille confirmée ne produit plus d'info. Claude a contrôlé visuellement les grilles 4x4 et 8x8 utilisées par Bulbito sur des planches.

### 1c. `pale_small_texture` et `flipbook_low_opacity` : trop de faux positifs
D'après `play_observations.json`, ces deux règles se déclenchent sur des émetteurs **bien visibles en Play** :
- les poussières pixel de A2_Ring, A2_Stop, A3_Ground, A1_Hit et Walk_Dust (Pixel Puff FX `11844402871`, 1 à 5 studs) ;
- les fumées pixel de A1_Muzzle et A1_Blow (Pixel Smoke 23 `13468353904`) ;
- les étoiles pixel de A1_Twirl et l'étincelle de A3_Fuse (`80635905349701`).

Explication probable : la règle mesure la couverture alpha de la case de la miniature, sans tenir compte de la **taille réelle à l'écran**. Une texture pixel aux bords nets, peu couvrante dans sa case mais affichée sur 2 à 5 studs, se voit très bien. Revois le calcul, par exemple :
- surface visible ≈ couverture × Size² (en studs) × opacité, intégrée sur la durée de vie ;
- seuil absolu en studs² ;
- bords durs (pixel art) comptés comme pleinement opaques.

C'est à toi de choisir la méthode, mais elle doit être documentée et ses seuils regroupés dans une seule table.

Critères :
- **Aucun** avertissement de visibilité (`pale_small_texture`, `flipbook_low_opacity`, `flipbook_empty_start`) sur les émetteurs `visible` de `play_observations.json`.
- `flipbook_empty_start` **toujours présent** sur `Pillar_InvisibleInPlay` / `Burst`.
- Les émetteurs `unknown` sont libres. Dis dans le rapport ce que la nouvelle règle donne pour eux.
- `abrupt_transparency` et `additive_white` restent comme aujourd'hui : ce sont des avertissements vrais par définition.

### 1d. Présentation
- Une ligne de résumé par code, avec le compte, puis le détail.
- Les infos à part.
- Le code de sortie de `validate` reste inchangé : les avertissements ne font jamais échouer.

## 2. Cadrage `--fit` / `--focus` trop large

Mesures de Claude sur `tool/fixtures/bulbito/A1_Muzzle.json` :
- `--fit Flash` (un émetteur) cadre bien : le flash, la flamme, la douille et les étincelles remplissent l'image ;
- `--fit Muzzle` (la Part qui porte tous les émetteurs) cadre toute l'étendue simulée, dont les étincelles qui partent à 8 studs et la douille qui tombe, et le flash devient minuscule ;
- `--focus 0,0,-1.5 --radius 3` montre environ 15 studs à la verticale au lieu d'environ 6 à 7. `autoCamera` cadre les **8 coins du cube** (rayon × √3, plus l'effet de profondeur) au lieu d'une sphère.

Demandes :
- **`--focus/--radius` cadre une sphère de rayon r.** Elle doit remplir environ 85 à 90 % de la plus petite dimension de l'image. Test : un objet de 6 studs centré sur `focus`, avec `--radius 3`, couvre au moins 75 % de la hauteur d'une image 480×270.
- **`--fit` par défaut :**
  - ne cadre que les particules **vivantes aux instants rendus** (union sur `--times`) ;
  - inclut la demi-taille (Size) de chaque particule ;
  - écarte les particules isolées (par exemple au-delà du 90ᵉ centile de distance au centroïde, réglable avec `--fit-percentile`) ;
  - garde l'ancien comportement avec `--fit-all`.

  Test : `--fit Muzzle --times 0.02,0.06` sur A1_Muzzle donne un cadrage comparable à `--fit Flash` (le flash couvre au moins 30 % de la hauteur).
- Si aucune particule n'est vivante aux instants demandés, repli sur la Part et ses Attachments, avec un message clair (pas d'erreur).
- Documente la différence entre `--fit` sur un émetteur et `--fit` sur une Part, dans `CLAUDE.md` et `DATAKY_FX_STUDIO.md`.
- Vérifie avec de vrais rendus Chromium, qui fonctionnent sur cette machine. Si le bac à sable bloque Chromium, dis-le : Claude relancera les tests.

## Rapport attendu

Mets à jour `RAPPORT_DEMANDES_CLAUDE.md` avec une section « Lot 2 » :
- les comptes d'avertissements avant et après sur les fixtures Bulbito, par code ;
- les résultats des critères ci-dessus ;
- les fichiers modifiés ;
- les sorties réelles des tests.
