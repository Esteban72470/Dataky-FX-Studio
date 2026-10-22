# Dataky FX Studio · guide pour Claude

Ce dépôt crée des effets visuels Roblox (VFX) décrits par une **recette JSON**, les montre dans un **émulateur** sans Roblox Studio, puis les **exporte** vers Roblox. Ce guide couvre les outils et les pièges propres à Roblox. La direction artistique (rythme, couleurs, lisibilité d’un effet) relève du skill VFX de l’utilisateur : appliquez-le, puis utilisez ces outils pour le réaliser et le vérifier.

## Boucle de travail

1. **Choisir les textures en les regardant.**
   `python tool/fx.py textures --tag Slash --kind flipbook` liste les assets et écrit une planche PNG avec leurs IDs (chemin dans `"sheet"`). Ouvrez cette image avant de choisir. Tags utiles : Impact, Slash, Crescent, Smoke, Fire, Flare, Circle, Lightning, Swirl, Star, Wind, Water, Ground. `--collection beams` pour les textures de Beam, `--collection meshes` pour les meshes, `--query anneau` ou `--query 15268066299` pour un nom ou un ID. Les flipbooks donnent `FlipbookLayout` (grille marquée `estimated` si elle est déduite).
2. **Partir de briques** quand elles conviennent : `python tool/fx.py blocks` liste flash, sparks, shockwave, smoke, slash, arc, swipe, fire, charge et orb, avec leurs réglages (`at`, `position`, `scale`, `intensity`, `color`, `color2`, et des réglages propres). Écrivez un plan puis :
   `python tool/fx.py compose plan.json --out recette.json`
   ```json
   {"name": "Coup de glace", "blocks": [
     {"block": "charge", "at": 0, "duration": 0.6, "color": [0.6, 0.85, 1]},
     {"block": "flash", "at": 0.6, "color": [0.7, 0.9, 1]},
     {"block": "sparks", "at": 0.6, "color": [0.6, 0.9, 1]},
     {"block": "shockwave", "at": 0.63, "scale": 1.3},
     {"block": "smoke", "at": 0.65, "color": [0.8, 0.9, 1]}]}
   ```
   La recette produite est ordinaire : modifiez ensuite ses propriétés, textures et timings à la main. `--base ID` ajoute les briques à un projet existant.
3. **Regarder le résultat.**
   `python tool/fx.py render recette.json --times 0,0.1,0.25,0.5,1` écrit une planche dans `rendus/`. Par défaut, la caméra de la recette est conservée et un **mannequin Roblox de 5 studs** donne l’échelle. `--auto-camera` cadre toute l’étendue de l’effet. Ouvrez l’image et jugez chaque instant : lisibilité, timing, échelle, couleurs, disparitions.
4. **Comparer des variantes** : `python tool/fx.py render a.json b.json c.json --times 0.1,0.3` produit une ligne par variante, avec la même caméra et les mêmes instants. La simulation est déterministe : même recette, même graine et même instant donnent la même image.
5. **Valider, enregistrer, exporter.**
   `python tool/fx.py validate recette.json`, puis `python tool/fx.py save recette.json` (visible dans l’atelier), puis `python tool/fx.py export recette.json --format rbxmx`. Le `.rbxmx` se glisse dans Studio et `require(workspace.NomDuModèle.DatakyFX).play()` joue l’effet. Avec `--format lua`, on obtient un ModuleScript autonome qui construit lui-même l’effet.

Une recette peut être un fichier JSON ou l’ID d’un projet de `editor/projects/`. Les mêmes outils existent en MCP : `python tool/fx_mcp.py`, configuré dans `.mcp.json` pour Claude Code. `INSTALLER_CLAUDE_DESKTOP.bat` l’ajoute à Claude Desktop.

## Tester à la main dans le mode Libre

Dans l’atelier, basculez **Timeline / Libre** (Tab). En Libre, l’horloge continue sans limite, les continus suivent leur Rate et les bursts attendent **Emit**. Le panneau ParticleEmitter propose une quantité (count du timing, sinon 30). **Emit sélection** inclut les descendants ; **Emit tout** déclenche tous les bursts avec leurs counts ; **Vider** efface les particules. Les interrupteurs Enabled dans l’arbre et les propriétés sont des états d’aperçu en Libre ; en Timeline ils éditent la recette et grisent sa piste. Les propriétés modifiées en Libre restent des modifications de recette, visibles immédiatement. Le pont natif doit être mis à jour pour ces nouvelles commandes.

**Raccourcis** (hors champs et dialogues) : Espace lecture/pause, Maj+Espace stop, E Emit sélection, Maj+E Emit tout, T Enabled sélection, Tab mode, C vider ; ←/→ une image, Maj+←/→ 0,1 s, Début/Fin, [/ ] événement précédent/suivant ; L boucle, F cadrer sélection, Maj+F tout, G sol, M mannequin, 1–5 fonds ; ↑/↓ arbre, Alt+↑ parent ; Ctrl+C/V copier/coller JSON avec enfants entre projets ; Ctrl+E .rbxmx, Ctrl+Maj+E .lua ; **?** ouvre l’aide complète, avec les raccourcis historiques. Le déplacement arbitraire de la tête reconstruit l’émulation seulement ; le rendu natif doit repartir de 0 pour retrouver son historique.

## Jouer dans un jeu : kit multi-instances

`python tool/fx.py export A1_Muzzle.json A2_Impact.json --format library --out exports/MesEffets.lua` écrit un module de données (clés = noms de fichiers sans extension) et **DatakyFXKit.lua** à côté. Installez les deux comme ModuleScripts voisins :

```lua
local FX = require(script.Parent.DatakyFXKit)
local Recipes = require(script.Parent.MesEffets)
FX.preloadTextures(Recipes) -- au démarrage ; cette fonction peut yield
FX.prepare(Recipes.A1_Muzzle) -- facultatif : déplace le travail du premier play
local h = FX.play(Recipes.A1_Muzzle, muzzle.WorldCFrame, {
    scale=1, speed=1, follow=muzzle, hold=false,
    params={radius=24}, quality="Auto", parent=workspace,
})
-- h:Release({hideParts=true}) cache les Parts et laisse finir les particules.
-- h:Stop() détruit immédiatement ; h:Move(cf) ; h:Part("node_id").
-- h:SetFollow(autreAttachment) ; h:SetFollow(nil) arrête le suivi.
-- FX.freeze() / FX.unfreeze() : particules et timeline pour les captures.
```

Chaque handle est indépendant et suit la rotation de la CFrame. `follow` accepte une fonction renvoyant une CFrame, un Attachment, un Bone (TransformedWorldCFrame) ou un BasePart. `quality="Low"` réduit les bursts à 60 % ; Auto lit le SavedQualityLevel disponible côté client. Le kit nettoie son dossier et laisse les dernières particules mourir après Release. Les animations Position et Transparency des Parts sont réservées à l’aperçu et ignorées par le kit ; les autres pistes sont jouées. Les MeshParts exigent **FX.preload(recipe)** avant `play` : seul ce préchargement peut yield, `play` reste immédiat. Les Trails natifs ne permettent pas de figer leur historique.

La validation et le décodage sont mis en cache par identité de table avec des clés faibles. Traitez la recette comme immuable dès `prepare`, `preload`, `preloadTextures`, `listTextures` ou le premier `play` : pour une variante, faites une **copie profonde** avant de la modifier. `table.clone` seul ne copie pas les nœuds imbriqués. Le premier play construit aussi un gabarit ; les suivants le clonent. `FX.prepare(recipe)` fait ce travail à l’avance, sans yield ; avec des MeshParts, appelez d’abord `FX.preload(recipe)`.

`h:Release()` arrête définitivement le suivi et coupe les continus ; `hideParts=true` cache immédiatement toutes les Parts/MeshParts du handle sans vider les particules. `h:SetFollow(fnOrInstance)` remplace le suivi ; `nil` le coupe. Il est sans effet après Release/Stop. L’option `onFinished=function(handle) ... end` est appelée une fois après la fin naturelle, Release suivi du drainage, ou Stop. Elle est différée avec `task.defer`, après nettoyage, et ses erreurs sont isolées ; elle peut donc yield sans faire yield `play`.

`FX.preloadTextures(recipeOrLibrary)` transmet à `ContentProvider:PreloadAsync` les URI explicites, uniques, des particules, Beams, Trails et textures de meshes ; elle peut yield et s’appelle au démarrage. `FX.listTextures(recipeOrLibrary)` renvoie cette liste sans charger. Les nouvelles bibliothèques proposent aussi `Recipes:listTextures()` (liste copiée ; `pairs(Recipes)` continue de ne donner que les recettes). En cas de recette nommée `listTextures`, utilisez `FX.listTextures(Recipes)`. Les bibliothèques exportées avant cette API restent acceptées par le nouveau kit.

L’export historique **`--format lua` conserve un seul effet à la fois, aligné sur les axes du monde** (translation d’origine). Son API et celle de `fx_runtime.lua` restent disponibles ; utilisez library + kit pour plusieurs unités animées.

## Outils d’écriture et de recherche

`tool/fx_builder.py` fournit les helpers importables **Recipe, NS, CS, NR** : `part`, `att`, `em`, `trail`, `light`, `anim`, `flip`, `merge`, `save`. Depuis un script dans le dépôt :

```python
from tool.fx_builder import Recipe, NS, CS, NR
fx = Recipe("Muzzle", 1)
fx.part("root")
fx.att("tip", "root", (0, 0, -1))
fx.em("sparks", "tip", "rbxassetid://123", count=12,
      Lifetime=NR(.2, .4), Size=NS((0, .3), (1, 0)),
      Transparency=NS((0, 0), (1, 1)))
fx.save("Muzzle.json")
```

Un plan compose peut inclure une recette par fichier, ID ou nom court unique des projets :

```json
{"blocks": [{"include":"A1_Muzzle.json","at":0.44,"position":[0,1,-4],"orientation":[0,90,0],"scale":1,
  "positionKeys":[{"time":0,"value":[0,0,0]},{"time":1,"value":[0,0,-10]}]}]}
```

Les fichiers inclus se résolvent relativement au plan CLI. `positionKeys` ajoute une translation animée avec des temps locaux à la pièce. IDs, références, animations et paramètres sont préfixés pour éviter les collisions. La rotation utilise YXZ ; les orientations restent exactes aux points clés, mais l’interpolation Euler entre des clés composées peut différer. Ajoutez des clés intermédiaires pour les tours complets.

Recherche courte : `python tool/fx.py textures --query star --compact --no-sheet --exclude-file used.txt`. `--exclude-ids 123 456` accepte aussi une liste d’IDs. Les exclusions précèdent pagination et total. `python tool/fx.py sheet 123 456 --exclude-file used.txt --out rendus/choix.png` dessine les grilles et marque **USED** sans retirer les IDs explicitement choisis. En MCP : `search_assets` accepte `compact`, `exclude_ids`, `exclude_file` ; `texture_sheet` produit la planche choisie.

Après installation du plugin régénéré et connexion du pont en Edit, **Dataky FX → Exporter les textures utilisées** écrit `tool/used_textures/<nom de la place>.txt`. Le fichier passe directement à `--exclude-file`. Le scan inclut les ParticleEmitter/Beam/Trail de la place et les champs de textures littéraux des ModuleScripts de recettes, sans exécuter ces modules. Il signale les sources illisibles et les expressions dynamiques, à compléter manuellement. Commande du pont : `POST /api/preview` avec `{"action":"export_used_textures"}` ; fonction de session : `_G.DatakyFXBridge.exportUsedTextures()`.

## Rendus ciblés et par lots

`python tool/fx.py render recette.json --fit NODE_ID --times 0.02,0.06` cadre les particules vivantes aux seuls instants rendus (union des instants), demi-taille incluse. Sur un **ParticleEmitter**, seuls cet émetteur et ses descendants contribuent ; sur une **Part**, tous ses émetteurs descendants contribuent. Le 90e centile de distance au centroïde écarte les centres isolés avant d’ajouter la demi-taille : `--fit-percentile 100` garde toutes les particules de ces instants. `--fit-all` retrouve l’ancien cadrage sur toute la durée simulée, y compris hors des instants choisis. S’il n’y a aucune particule vivante, le cadrage se replie sur la Part porteuse et ses Attachments avec un avertissement explicite.

Le cadrage transforme le contour alpha des cases effectivement affichées avec la taille, le Squash et la rotation du quad. Il conserve par défaut 90 % de l’énergie de contraste (`alpha²`) de chaque case, normalisée par case pour préserver les textures entièrement pâles ; le même `--fit-percentile` règle ce contour et le rejet des centres isolés. À 100, toute l’emprise alpha et toutes les particules sont conservées. Une miniature inaccessible utilise le quad entier. La caméra ajuste ces points visibles directement, sans ajouter la profondeur d’un cube autour des billboards. Les billboards sont réévalués après recentrage pour tenir compte de leur orientation vers la caméra. Cette analyse sert uniquement au cadrage ; les pixels rendus et le calcul des avertissements restent inchangés.

`--focus 0,1,-4 --radius 3` cadre une **sphère** de rayon 3, depuis la direction de caméra actuelle. Sa silhouette remplit 87,5 % de la plus petite dimension de l’image ; les coins d’un cube englobant ne servent plus au calcul. `--background roblox` force le décor clair ; `--background dark` utilise un ciel de nuit `[0.035,0.045,0.08]` et un sol gris sombre `[0.16,0.16,0.17]` (RGB 0–1), approximation de la scène observée dans vfx.rbxl. Sans preset le fond de la recette est utilisé.

`--backgrounds roblox,dark` produit une ligne par recette puis par fond, avec la même caméra, les mêmes instants et la même graine. Ce paramètre est exclusif avec `--background`. Python/MCP : `backgrounds=["roblox","dark"]` ou la chaîne `"roblox,dark"` ; les jobs batch utilisent la même clé `backgrounds`. Jusqu’à huit fonds/presets/couleurs `#RRGGBB` sont acceptés par le renderer/Python (MCP annonce les presets). Le JSON expose `rows` (recette/fond) et `sheet` (dimensions) ; les images individuelles gardent un préfixe distinct par ligne.

`python tool/fx.py render-batch jobs.json` réutilise **un seul lancement de Chromium** pour plusieurs vues. Exemple de manifeste :

```json
{"jobs":[
  {"projects":["A1_Muzzle.json"],"out":"rendus/face.png","times":[0,0.1,0.3],"camera":[10,6,12,0,1,0],"fit":"root"},
  {"projects":["A1_Muzzle.json","A2_Impact.json"],"out":"rendus/profil.png","times":[0.1,0.3],"camera":[12,2,0,0,1,0],"focus":[0,1,0],"radius":3}
]}
```

Les recettes se résolvent relativement au manifeste, les sorties relativement au dépôt. Les options de jobs utilisent camelCase (`autoCamera`, `framesDir`, `fitPercentile`, `fitAll`…). API Python : `fx_tools.render_batch(jobs)` ; `fx_tools.render` accepte `fit_percentile` et `fit_all`, comme les options MCP de `render_effect`. Playwright/Chromium restent nécessaires. Des tests géométriques et des tests de rendu Chromium sont disponibles ; si le bac à sable interdit l’accès au Playwright installé, les tests de rendu l’indiquent explicitement et restent à relancer hors de ce bac à sable.

La règle de caméra est la même pour un rendu unique, le batch et MCP : `camera` fournit les six valeurs exactes ; `fit`/`focus` cadrent depuis la direction choisie ; sans cadrage demandé, la caméra de la recette est gardée. `autoCamera: true` (CLI `--auto-camera`) demande explicitement le cadrage global ; une caméra explicite reste prioritaire. `--no-auto-camera` reste accepté.

## Format de la recette

`python -c "import sys; sys.path.insert(0,'tool'); from fx_schema import SCHEMA; import json; print(json.dumps(SCHEMA, ensure_ascii=False))"` donne toutes les classes, propriétés, types et limites. L’outil MCP `get_schema` donne la même chose. Points clés :

- `nodes` : `{id, class, name, parent, properties, timing?}`. Un ParticleEmitter vit dans un Part ou un Attachment ; un Beam ou un Trail relie `Attachment0` et `Attachment1`.
- `timing` (émetteurs, beams, trails, lumières) vaut `{start, duration, mode: "burst" | "continuous", count}`. `burst` fait un `Emit(count)` unique à `start`. Toutes les fins de timing doivent tenir dans `duration`.
- `animations` : `[{node, property, keyframes: [{time, value}]}]`, avec les temps en secondes, interpolés linéairement. Les booléens et les enums restent sur la valeur du point clé.
- Séquences : `NumberSequence` = `[{time, value, envelope}]` et `ColorSequence` = `[{time, value: [r,g,b]}]`, de 0 à 1, avec 20 points au maximum.
- Paramètres : `params: {"radius": {"default": 16, "min": 0, "max": 64, "step": 1}}` au niveau recette ; `scaleWith: {"Size": "radius", "Speed": "radius"}` au niveau ParticleEmitter. La propriété numérique doit être explicite. Le kit applique `options.params.radius / default` aux seules propriétés marquées (et à leurs animations), en plus de scale. Les curseurs de l’atelier règlent seulement l’aperçu.

## Pièges Roblox (vérifiés dans l’émulateur et la documentation)

- **Courbe d’un Beam** : les points de contrôle suivent **+X d’Attachment0** et **−X d’Attachment1**. Avec des attachments non tournés et alignés, `CurveSize` ne courbe rien. Inclinez leur `Orientation` ou utilisez `Axis`/`SecondaryAxis`.
- **Largeur d’un Beam sans FaceCamera** : elle suit l’axe Y (UpVector) des attachments.
- **Texture d’un Beam ou d’un Trail** : l’axe **vertical** de l’image suit la longueur du ruban, l’axe horizontal sa largeur.
- **Anneau à plat au sol** : utilisez `Orientation: VelocityPerpendicular`, `Speed` à 0,01 et `EmissionDirection: Top`.
- **Étincelles étirées** : en `Orientation: VelocityParallel` et `Rotation: 0`, un `Squash` **négatif** étire le long de la vitesse ; positif étire en travers (mesuré dans Roblox). Une texture de trait vertical demande `Rotation: 90` avec un Squash positif. Les textures non carrées sont comprimées dans le quad carré. FacingCamera n’a pas été mesuré et conserve son approximation actuelle.
- **Fin de particule** : `abrupt_transparency` exige une Transparency finale < **0,95** et une Size finale > `max(0,05 stud, 5 % de la taille maximale)`. Rétrécir jusqu’à environ zéro est donc une autre façon de finir proprement, même avec une Transparency finale de 0,4. La taille résiduelle et la transparence sont regroupées dans ce seul diagnostic.
- **Couche au sol** : `flat_layer_negative_zoffset` signale `VelocityPerpendicular` + `EmissionDirection: Top` + `ZOffset < 0`, qui peut enfouir la couche sous le sol.
- **Contraste sombre** : `dark_ground_contrast` signale les émetteurs de LightEmission < 0,2 et de luminance RGB maximale < 0,15 sans couche claire couvrant leur présence potentielle. Une couche de soutien exige LightEmission ≥ 0,2, luminance maximale ≥ 0,45, opacité maximale ≥ 0,05 et taille maximale > 0,05 stud. Les fenêtres tiennent compte du timing, de Count/Rate, d’Enabled et de ses pistes, de la Lifetime et de TimeScale ; une brève intersection ne suffit pas, l’union doit couvrir toute la période. Les seuils sont dans `THRESHOLDS`. Ce calcul ne mesure ni recouvrement spatial ni texture/éclairage natif, et les autres propriétés animées, enveloppes et probabilités d’émission restent des approximations. Il peut signaler une couche sombre intentionnelle ; comparer `--backgrounds roblox,dark` et vérifier dans Studio.
- **Flipbooks qui commencent presque vides** : le OneShot « Upwards flame pillar » `70418763522849` avec Lifetime 0,2–0,45 s a été invisible en Play malgré une bonne planche catalogue. Regardez les premières cases, augmentez la Lifetime ou changez de texture. `validate` conserve ce risque court et avertit aussi sur une faible surface visible, une couleur additive saturée, un Squash positif parallèle et les fins de courbes abruptes. Ces avertissements n’invalident pas la recette et ne changent pas son code de sortie.
- **Visibilité** : tous les seuils sont regroupés dans `tool/fx_warnings.py::THRESHOLDS`. La surface opaque équivalente moyenne est `∫ alpha × Size² × (1 - Transparency) dt`, sur une vie normalisée de 0 à 1, avec seuil **0,01 stud²**. L’intégration suit les points des courbes et les cases OneShot ; les autres modes utilisent l’alpha moyen des cases. Un pixel opaque contribue pleinement, sans lui appliquer une deuxième pénalité de couverture. Cela tient compte des poussières pixel de 1 à 5 studs, visibles en Play malgré une faible couverture de la case. Le risque de début vide reste indépendant : premier quart d’alpha moyen < 0,08 et Lifetime maximale ≤ 0,5 s. Couleurs, fond, enveloppes et cumul de particules restent hors de cette estimation heuristique.
- **Grilles estimated** : infos masquées par défaut, une seule par texture dans une recette. `python tool/fx.py validate recette.json --infos` (ou `--verbose`) affiche séparément leurs résumés et détails. Confirmer une grille contrôlée visuellement avec `python tool/fx.py grid-confirm 11844402871 4` écrit `tool/grid_overrides.json`, hors catalogue ; cette confirmation retire l’info pour la grille correspondante et s’applique aussi aux recherches. Grilles carrées acceptées : 2, 4 ou 8. MCP : `validate_effect` avec `include_infos: true`, et `grid_confirm` avec `id` et `grid`. Aucune grille n’est confirmée automatiquement à partir des observations Play.
- Les statistiques alpha sont calculées depuis les miniatures locales et mises en cache dans **tool/texture_frames.json** avec empreinte SHA-256 ; aucun fichier du catalogue n’est changé. Calcul paresseux au premier `validate`, ou `python tool/fx_texture_cache.py [IDs…]` (sans IDs : tout le catalogue). La surface moyenne reste une heuristique, pas une mesure du séquencement OneShot natif. PNG entrelacés non pris en charge : diagnostic plutôt qu’estimation inventée. La CLI affiche d’abord une ligne de résumé par code, puis le détail, et enfin les infos si demandées ; MCP fournit aussi `warning_counts`, `infos` et `info_counts`.
- **`LightEmission: 1`** donne un mélange additif (lumière) ; 0 donne un mélange normal (fumée, poussière). `Brightness` n’agit que si `LightInfluence` est inférieur à 1.
- **`SpreadAngle [180, 180]`** émet dans toutes les directions. `Drag` réduit de moitié la vitesse d’émission toutes les `1/Drag` secondes, sans freiner l’accélération.
- **Attachment** : `Orientation` et `Axis`/`SecondaryAxis` s’excluent.
- **ParticleEmitter dans un Attachment** : il émet depuis un point. Dans un Part, il émet depuis la forme `Shape` (Box, Sphere, Cylinder, Disc), à la taille du Part.
- **`VelocityInheritance`** n’a pas d’effet ici : les Parts sont ancrées et déplacées par propriété.

## Limites de l’émulation

Les textures affichées sont les miniatures 420 × 420 de la bibliothèque. La géométrie des MeshPart et des FileMesh n’est disponible que dans Roblox (affichage en boîtes filaires). La forme exacte de Squash, la répartition de SpreadAngle, l’éclairage et le bloom sont approchés. Pour un effet à publier, demandez à l’utilisateur une vérification dans **◉ Roblox Studio**.

Un Trail natif ne conserve pas son historique pendant une capture figée : sa pause fidèle n’est pas disponible. Le pont relaie, lorsqu’ils arrivent, les événements documentés de focus du viewport principal ; l’atelier avertit pendant la lecture native s’il reçoit explicitement `window_focused=false`. L’état initial reste inconnu, et le fonctionnement de ces signaux dans ce plugin en Edit n’a pas été mesuré. Ils ne constituent pas une détection garantie du focus de toute la fenêtre Studio ([référence Roblox](https://create.roblox.com/docs/reference/engine/classes/UserInputService#WindowFocused)).

## Développement

- Atelier : `python tool/fx_server.py` (port 48754), interface dans `editor/`. L’émulateur est `editor/emulator.js` ; le rendu sans fenêtre passe par `tool/fx_render.cjs` (Node + Playwright).
- Tests : `node tool/test_fx_frontend.cjs`, `node --test tool/test_fx_emulator.cjs tool/test_fx_preview_ui.cjs tool/test_fx_curves.cjs`, `cd tool && python -m unittest test_fx_server test_fx_templates test_macro test_fx_rbxmx test_fx_tools`. Avec `DATAKY_LUAU=chemin/vers/luau`, `test_fx_rbxmx` exécute aussi le lecteur `.rbxmx` sous Luau.
- Après une modification de `tool/fx_runtime.lua`, régénérez le plugin avec `python tool/fx_package.py`.
- Tests des nouvelles fonctions : ajouter `tool/test_fx_render.cjs tool/test_fx_texture_bounds.cjs` à la commande `node --test`, et `test_fx_sandbox test_fx_kit test_fx_builder test_fx_warnings` à unittest. `python -m unittest discover -s tool -p 'test_*.py'` lance toutes les suites Python. Les tests Luau utilisent le mock étendu sans prétendre remplacer Studio.
- `rendus/` et `exports/` sont des sorties locales, ignorées par git.
