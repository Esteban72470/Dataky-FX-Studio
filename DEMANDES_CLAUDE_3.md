Tu travailles sur **Dataky FX Studio** (`C:\Users\esteb_9qwvhb8\Downloads\Dataky-FX-Studio-main`). Lis d'abord ces fichiers :
- `CLAUDE.md` et `DATAKY_FX_STUDIO.md` ;
- les lots précédents : `DEMANDES_CLAUDE.md`, `DEMANDES_CLAUDE_2.md` et `RAPPORT_DEMANDES_CLAUDE.md`.

## Contexte

Les lots 1 et 2 marchent : builder, export `library`, `DatakyFXKit` (`FX.play`), `render-batch`, avertissements.

Ils ont maintenant servi à construire une unité complète de tower defense, **Blueberrinni Octopusini** :
- 12 recettes ;
- jouées par `FX.play` en Play dans Roblox Studio, sur un rig animé ;
- dans un jeu qui aura beaucoup d'unités à l'écran, y compris sur mobile.

Ce lot corrige ce que ce vrai usage a révélé et rend le kit plus solide pour un jeu.

Fixtures fournies dans `tool/fixtures/blueberrinni/` : ce sont des observations réelles. Ne les modifie pas pour faire passer un test.
- Les 12 recettes de l'unité (A1_*, A2_*, Idle_Bubble, Walk_Splish).
- `Gather_DarkInkOnly.json` : la première version de A2_Gather. Son tourbillon d'encre presque noire, avec LightEmission 0, était **invisible en Play sur un sol gris foncé**.
- `Splat_NegativeZOffset.json` : A1_Splat avec les couches au sol en ZOffset -0.5. Ces couches passent **sous le sol**.
- `jobs_camera_ignored.json` : reproduction du bug de caméra de `render-batch`.
- `play_observations.json` :
  - ce qui a été vu (`visible`) ;
  - ce qui a disparu sur sol sombre (`invisible_on_dark_ground`) ;
  - ce qui est passé sous le sol (`under_ground`) ;
  - ce qui n'est pas vérifié (`unknown`) ;
  - les temps de `FX.play` mesurés dans Studio.

## Règles (inchangées)

- Pas de git. Ne touche pas au catalogue : `images/`, `previews/`, `source/`, `beams/`, `meshes/`, `tags/`, `textures.*`, `catalogue.html`.
- **Compatibilité :**
  - tous les projets existants, `tool/fixtures/bulbito` et `tool/fixtures/blueberrinni` restent valides ;
  - un module `library` déjà exporté doit marcher avec le nouveau kit ;
  - `FX.play` ne yield jamais.
- Chaque point a son test. Lance **toutes** les suites (JS, Python, Luau mock) à la fin.
- Si tu modifies le runtime ou le plugin, régénère `editor/DatakyFXStudio.rbxmx` avec `python tool/fx_package.py`.
- Termine par **`RAPPORT_DEMANDES_CLAUDE_3.md`**. Pour chaque point, donne :
  - ce qui est fait ;
  - les fichiers modifiés ;
  - les mesures avant et après ;
  - ce qui reste non fait ou incertain.

Ce que seul un vrai Studio peut prouver, marque-le « à vérifier dans Studio par Claude ».

## P0 · Bugs

**1. `render-batch` ignore la caméra d'un job.**
- Avec `jobs_camera_ignored.json`, qui demande `"camera":[3,2,4,0,0.3,0]`, la caméra rendue est automatique : position (5.35, 5.874, 10.7), cible (-1.519, 1.982, 1.542). Ce n'est ni celle du job ni celle de la recette.
- **Attendu :** un job avec les mêmes options que `fx.py render` donne la même caméra.
  - `camera` explicite : caméra exacte.
  - `fit` ou `focus` : cadrage.
  - Sinon : caméra de la recette, comme le dit la doc de `--camera`.
- Ajoute un test qui compare la caméra du rapport JSON à la caméra demandée.

**2. Le message du plugin s'affiche en Play.**
- « Dataky FX Studio : cliquez sur Connexion dans la barre Dataky FX. » sort **deux fois à chaque lancement de Play**. Vu dans 3 sessions. P0.3 promettait « jamais en Play ».
- Hypothèse : le plugin se charge dans les DataModels de Play, serveur et client.
- Garde-le avec `RunService:IsRunning()` en plus du test Edit.
- Teste-le avec un mock qui simule un DataModel serveur et un DataModel client en Play.

## P1 · Kit pour un vrai jeu

**3. Performance de `FX.play`.**
- Aujourd'hui, chaque appel revalide et redécode toute la recette. Mesuré dans Studio : 0,99 ms pour A2_Slam (14 nœuds) et 0,65 ms pour A1_Splat (10 nœuds). Le Maelstrom lance 11 pièces sur la même frame, soit environ 8 ms de pic.
- **Demande :**
  - mets en cache la validation et le décodage par table de recette, avec des clés faibles ;
  - ajoute `FX.prepare(recipe)`, optionnel, qui construit un gabarit d'instances ; `play` ne fait alors que `Clone()`, placer et lancer.
- Garde un comportement identique : rendu, timing, scale, params, follow, hold.
- Documente la règle si une recette est modifiée après un `play` : soit la détecter, soit dire de la copier.
- Fais un benchmark dans le mock Luau. Objectif : un 2e `play` de la même recette au moins 3 fois plus rapide. Donne les chiffres.

**4. Cacher un projectile au Release.**
- Cas réel : la baie est faite de 3 Parts visibles portées par `follow`, plus des gouttes. À l'impact, les Parts doivent disparaître tout de suite pendant que les gouttes finissent.
- Aujourd'hui, il faut écrire `h:Part("berry").Transparency = 1` pour chaque Part, puis `h:Release()`.
- **Demande :** `h:Release({hideParts = true})`.

**5. Rendre officielles des choses utilisées en douce.**
- `h:SetFollow(fnOrInstance)` : aujourd'hui on réassigne `handle.follow` directement.
- Une option `onFinished(handle)` appelée quand le handle se termine.
- Documente que :
  - `follow` s'arrête au Release ;
  - les pistes Position et Transparency des Parts sont ignorées par le kit.

**6. `FX.preloadTextures(recipeOrLibrary)`.**
- Il précharge toutes les textures (`ContentProvider:PreloadAsync`). Il peut yield : il s'appelle au démarrage.
- Raison : au premier `play` d'une texture jamais chargée, on voit parfois rien.
- Le module `library` exporté doit pouvoir lister ses textures.

## P2 · Validation et rendus

**7. Faux positif de `abrupt_transparency`.**
- Une particule dont la Size finit à environ 0 a déjà fondu, même si sa Transparency finit à 0,4. Exemple : Size (0, 0.34) puis (1, 0), et Transparency (0, 0) puis (1, 0.4).
- Pas d'avertissement dans ce cas. Construis le test.

**8. Nouvel avertissement `flat_layer_negative_zoffset`.**
- Il vise une couche plate au sol (`VelocityPerpendicular` + `EmissionDirection Top`) avec `ZOffset < 0`.
- Test : `Splat_NegativeZOffset.json` signale `splat` et `ripple`, et `A1_Splat.json` ne signale rien.

**9. Nouvel avertissement de contraste sur sol sombre.**
- Il vise des couches opaques (LightEmission < 0,2) presque noires, par exemple une luminance maximale < 0,15, sans couche claire active en même temps dans la recette.
- Test : `Gather_DarkInkOnly.json` est signalé, et `A2_Gather.json` ne l'est pas, parce que sa couche `swirlLight` couvre le même moment.
- Les seuils vont dans `THRESHOLDS`.

**10. Fond sombre pour les rendus.**
- Un preset `--background dark` : ciel de nuit et sol gris foncé, comme `vfx.rbxl`. Il doit marcher en CLI, en MCP et dans `render-batch`.
- Une option pour rendre une ligne par fond, par exemple `--backgrounds roblox,dark`, afin de voir le contraste avant Studio.

## P3 · Bonus si le temps le permet

**11. Scan des textures utilisées.**
- Une commande du pont plugin, « Exporter les textures utilisées », écrit les IDs de tous les ParticleEmitter, Beam et Trail de la place ouverte, plus ceux des ModuleScripts de recettes, dans `tool/used_textures/<nom de la place>.txt`.
- Ce fichier doit s'utiliser directement avec `--exclude-file`.
- Aujourd'hui, Claude doit scanner la place à la main à chaque unité.

**Livrable :** le code, les tests et `RAPPORT_DEMANDES_CLAUDE_3.md`. Ne commence pas P2 tant que P0 et P1 ne passent pas tous leurs tests.
