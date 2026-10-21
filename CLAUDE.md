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
   `python tool/fx.py render recette.json --times 0,0.1,0.25,0.5,1` écrit une planche dans `rendus/`. Par défaut, la caméra cadre toute l’étendue de l’effet et un **mannequin Roblox de 5 studs** donne l’échelle. Ouvrez l’image et jugez chaque instant : lisibilité, timing, échelle, couleurs, disparitions.
4. **Comparer des variantes** : `python tool/fx.py render a.json b.json c.json --times 0.1,0.3` produit une ligne par variante, avec la même caméra et les mêmes instants. La simulation est déterministe : même recette, même graine et même instant donnent la même image.
5. **Valider, enregistrer, exporter.**
   `python tool/fx.py validate recette.json`, puis `python tool/fx.py save recette.json` (visible dans l’atelier), puis `python tool/fx.py export recette.json --format rbxmx`. Le `.rbxmx` se glisse dans Studio et `require(workspace.NomDuModèle.DatakyFX).play()` joue l’effet. Avec `--format lua`, on obtient un ModuleScript autonome qui construit lui-même l’effet.

Une recette peut être un fichier JSON ou l’ID d’un projet de `editor/projects/`. Les mêmes outils existent en MCP : `python tool/fx_mcp.py`, configuré dans `.mcp.json` pour Claude Code. `INSTALLER_CLAUDE_DESKTOP.bat` l’ajoute à Claude Desktop.

## Format de la recette

`python -c "import sys; sys.path.insert(0,'tool'); from fx_schema import SCHEMA; import json; print(json.dumps(SCHEMA, ensure_ascii=False))"` donne toutes les classes, propriétés, types et limites. L’outil MCP `get_schema` donne la même chose. Points clés :

- `nodes` : `{id, class, name, parent, properties, timing?}`. Un ParticleEmitter vit dans un Part ou un Attachment ; un Beam ou un Trail relie `Attachment0` et `Attachment1`.
- `timing` (émetteurs, beams, trails, lumières) vaut `{start, duration, mode: "burst" | "continuous", count}`. `burst` fait un `Emit(count)` unique à `start`. Toutes les fins de timing doivent tenir dans `duration`.
- `animations` : `[{node, property, keyframes: [{time, value}]}]`, avec les temps en secondes, interpolés linéairement. Les booléens et les enums restent sur la valeur du point clé.
- Séquences : `NumberSequence` = `[{time, value, envelope}]` et `ColorSequence` = `[{time, value: [r,g,b]}]`, de 0 à 1, avec 20 points au maximum.

## Pièges Roblox (vérifiés dans l’émulateur et la documentation)

- **Courbe d’un Beam** : les points de contrôle suivent **+X d’Attachment0** et **−X d’Attachment1**. Avec des attachments non tournés et alignés, `CurveSize` ne courbe rien. Inclinez leur `Orientation` ou utilisez `Axis`/`SecondaryAxis`.
- **Largeur d’un Beam sans FaceCamera** : elle suit l’axe Y (UpVector) des attachments.
- **Texture d’un Beam ou d’un Trail** : l’axe **vertical** de l’image suit la longueur du ruban, l’axe horizontal sa largeur.
- **Anneau à plat au sol** : utilisez `Orientation: VelocityPerpendicular`, `Speed` à 0,01 et `EmissionDirection: Top`.
- **Étincelles étirées** : utilisez `Orientation: VelocityParallel` avec un `Squash` positif (étire le long de la vitesse).
- **`Transparency` doit finir à 1**, et `Size` à 0 ou presque, sinon les particules disparaissent d’un coup en fin de vie.
- **`LightEmission: 1`** donne un mélange additif (lumière) ; 0 donne un mélange normal (fumée, poussière). `Brightness` n’agit que si `LightInfluence` est inférieur à 1.
- **`SpreadAngle [180, 180]`** émet dans toutes les directions. `Drag` réduit de moitié la vitesse d’émission toutes les `1/Drag` secondes, sans freiner l’accélération.
- **Attachment** : `Orientation` et `Axis`/`SecondaryAxis` s’excluent.
- **ParticleEmitter dans un Attachment** : il émet depuis un point. Dans un Part, il émet depuis la forme `Shape` (Box, Sphere, Cylinder, Disc), à la taille du Part.
- **`VelocityInheritance`** n’a pas d’effet ici : les Parts sont ancrées et déplacées par propriété.

## Limites de l’émulation

Les textures affichées sont les miniatures 420 × 420 de la bibliothèque. La géométrie des MeshPart et des FileMesh n’est disponible que dans Roblox (affichage en boîtes filaires). La forme exacte de Squash, la répartition de SpreadAngle, l’éclairage et le bloom sont approchés. Pour un effet à publier, demandez à l’utilisateur une vérification dans **◉ Roblox Studio**.

## Développement

- Atelier : `python tool/fx_server.py` (port 48754), interface dans `editor/`. L’émulateur est `editor/emulator.js` ; le rendu sans fenêtre passe par `tool/fx_render.cjs` (Node + Playwright).
- Tests : `node tool/test_fx_frontend.cjs`, `node --test tool/test_fx_emulator.cjs tool/test_fx_preview_ui.cjs tool/test_fx_curves.cjs`, `cd tool && python -m unittest test_fx_server test_fx_templates test_macro test_fx_rbxmx test_fx_tools`. Avec `DATAKY_LUAU=chemin/vers/luau`, `test_fx_rbxmx` exécute aussi le lecteur `.rbxmx` sous Luau.
- Après une modification de `tool/fx_runtime.lua`, régénérez le plugin avec `python tool/fx_package.py`.
- `rendus/` et `exports/` sont des sorties locales, ignorées par git.
