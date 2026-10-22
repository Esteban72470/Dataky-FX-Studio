# Dataky FX Studio · rapport du lot 3

Livraison du 22 octobre 2026, dans `C:\Users\esteb_9qwvhb8\Downloads\Dataky-FX-Studio-main`.

Les points 1 à 10 sont implémentés et testés. Le bonus 11 est livré pour les objets natifs et les recettes littérales des ModuleScripts ; les limites des recettes calculées sont explicites ci-dessous. Aucun test dans le moteur Roblox n'est prétendu : les comportements qui en dépendent restent **« à vérifier dans Studio par Claude »**.

Aucune commande git utilisée. Aucun fichier du catalogue, aucune fixture et aucun projet existant modifié. Audit SHA-256 : **10 176 fichiers protégés, zéro différence**. Validation conservée pour les **26 projets existants**, **19 recettes Bulbito** et **14 recettes Blueberrinni** (12 courantes + 2 reproductions). Les manifestes et observations, qui ne sont pas des recettes, sont également protégés par empreinte.

P2 a commencé après le passage de toutes les suites P0/P1 : Python **150 tests, OK**, JavaScript **94/94**, frontend PASS. Logs : `rendus/lot3-gate-P0-P1-{python,javascript,frontend}.txt`. Une revue ultérieure a également corrigé une URL valide du schéma avec `/asset?id=…` sans slash avant `?` ; elle est couverte par la suite finale.

## 1 · Caméra de render-batch

**Fait.** Le batch injectait `autoCamera: true`, qui écrasait la caméra du job. Les entrées Python, CLI et MCP partagent maintenant les priorités : caméra explicite exacte ; `fit`/`focus` demandent un cadrage depuis cette direction ; sinon caméra de la recette. `--auto-camera` demande explicitement le cadrage global. L'ancien `--no-auto-camera` reste accepté. Même si une ancienne configuration transmet `autoCamera: true` avec une caméra explicite, celle-ci reste prioritaire.

**Mesure avant → après, Chromium réel, fixture originale :**

| | Position | Cible |
| --- | --- | --- |
| Avant, reproduit | `[5.35,5.874,10.7]` | `[-1.519,1.982,1.542]` |
| Après / demande du job | `[3,2,4]` | `[0,0.3,0]` |

Le test compare le rapport JSON aux six valeurs demandées, puis compare batch/rendu unique et le défaut caméra de recette. Les tests `fit`/`focus` vérifient aussi la direction conservée.

**Fichiers :** `tool/fx_render.cjs`, `tool/fx_tools.py`, `tool/fx.py`, `tool/fx_mcp.py`, `tool/test_fx_render.cjs`, `tool/test_fx_tools.py`. Preuves : `rendus/lot3-camera-after.json`, `rendus/lot3-p0-notes.md`.

**Reste :** aucun point fonctionnel identifié pour cette correction hors moteur.

## 2 · Message du plugin en Play

**Fait.** Le message unique est conditionné par `RunService:IsEdit() and not RunService:IsRunning()`. Un nouveau test exécute le **source complet** du plugin dans des DataModels mockés serveur et client Play, y compris avec `IsEdit=true` et `IsRunning=true`. Deux chargements en Edit n'affichent qu'un message ; un DataModel non Edit et non running reste silencieux.

**Avant → après :** observation fournie : deux messages par lancement, constatés dans trois sessions. Après : **0 message serveur + 0 message client** dans le mock ; **1 message pour deux chargements Edit**. Le source et le package présents au début avaient déjà une garde `not IsRunning()` : la cause des deux messages observés n'a donc pas été reproduite à partir de ces fichiers. La garde a été renforcée et le package régénéré.

**Fichiers :** `tool/fx_plugin.lua`, `tool/test_fx_plugin.py`, `tool/test_fx_rbxmx.py`, `editor/DatakyFXStudio.rbxmx`.

**Reste :** vérifier le plugin effectivement installé, les éventuels doublons et ses vrais DataModels **à vérifier dans Studio par Claude**. Le package livré n'a pas été installé automatiquement dans les plugins de Studio.

## 3 · Cache et FX.prepare

**Fait.** Validation, décodage, ordre des propriétés, paramètres et pistes sont compilés par identité de table dans un cache à clés faibles (`__mode="k"`). Le snapshot décodé ne référence pas sa clé. Le premier `play` crée un gabarit non parenté ; les suivants clonent ce gabarit, appliquent les facteurs variables, placent les objets et démarrent la timeline. `FX.prepare(recipe)` anticipe ce coût sans yield et renvoie la recette. Pour une MeshPart : `FX.preload(recipe)` reste nécessaire avant prepare/play et peut yield.

Les tests couvrent indépendance des clones, références Beam/Trail remappées, scale/params, rotation, animations, follow/hold, freeze, nettoyage et les 14 recettes Blueberrinni. `play` ne yield jamais ; les callbacks utilisateur ne sont pas exécutés sur sa pile.

**Règle de mutation documentée :** dès le premier accès par le kit, considérer la recette immuable. Pour modifier une variante, faire une **copie profonde** avant de la changer ; `table.clone` seul ne copie pas les nœuds imbriqués. Les options de lecture peuvent varier librement. Le cache ne détecte pas une mutation de la même table.

**Mesures réelles dans Luau CLI + mock Roblox**, médianes de 300 paires ; seul `FX.play` est chronométré. Les copies profondes, Stop et prepare sont hors chronomètre. Ancien et nouveau source emploient le même mock final, avec tracing désactivé dans les deux cas. Le Clone mock copie descendants/attributs/propriétés et remappe les références internes ; il ne prétend pas mesurer le Clone natif.

| Recette | Ancien 1er / 2e play, ms | Nouveau 1er / 2e play, ms | Play après prepare, ms | Nouveau 1er / 2e |
| --- | --- | --- | --- | --- |
| A1_Splat, 10 nœuds | 0,2854 / 0,2836 | 0,3292 / **0,0545** | 0,0569 | **6,04×** |
| A2_Slam, 14 nœuds | 0,4434 / 0,4394 | 0,5097 / **0,0743** | 0,0793 | **6,86×** |

Objectif ≥3× atteint pour les deux fixtures. Le test de régression reprend 180 paires par fixture et impose ce seuil. Par rapport au deuxième appel de l'ancien kit, le nouveau est environ 5,20× / 5,91× plus rapide. Le premier appel froid coûte environ 15 % de plus car il construit le gabarit ; prepare déplace ce travail au chargement.

**Fichiers :** `tool/fx_kit.lua`, `tool/luau_roblox_mock.luau`, `tool/test_fx_kit.py`, `tool/benchmark_fx_kit.py`. Preuves : `rendus/lot3-kit-before.lua`, `rendus/lot3-kit-{before,after}-benchmark.json`, `rendus/lot3-p1-notes.md`.

**Reste :** les mesures Studio fournies (0,65 ms Splat, 0,99 ms Slam, pic Maelstrom ~8 ms) restent des mesures antérieures. Le temps natif, le pic des 11 pièces et la performance mobile sont **à vérifier dans Studio par Claude**. Aucun temps Studio après modification n'est inventé.

## 4 · Release avec hideParts

**Fait.** `h:Release({hideParts=true})` met immédiatement Transparency=1 sur toutes les Parts/MeshParts du handle, arrête les émissions et laisse les particules finir. Pas de Clear ni de destruction anticipée. Un second Release avec cette option peut encore masquer les Parts si le premier n'avait pas l'option.

**Avant → après :** une affectation manuelle par Part + Release → **un seul appel** pour tous les supports. Le mock vérifie deux Parts visibles masquées immédiatement et un émetteur conservé jusqu'au drainage ; les tests préexistants vérifient la durée de vie et l'annulation des futurs bursts.

**Fichiers :** `tool/fx_kit.lua`, `tool/test_fx_kit.py`.

**Reste :** projectile réel à trois Parts et gouttes résiduelles **à vérifier dans Studio par Claude**.

## 5 · SetFollow et onFinished

**Fait.** `h:SetFollow(fnOrInstance)` remplace le suivi, accepte nil pour le détacher et renvoie h. Attachment, Bone, BasePart et fonction sont supportés. La fonction n'est appelée ni par SetFollow ni par play. Release coupe définitivement le suivi ; un rattachement après Release/Stop est sans effet.

`options.onFinished(handle)` est différé par `task.defer` après le nettoyage, une seule fois : fin naturelle, Release/drainage, Stop, retrait externe ou erreur du handle. Ses erreurs sont isolées ; s'il yield, il ne fait yield ni play ni Stop et ne bloque pas un autre handle. Les pistes Position et Transparency des Parts/MeshParts restent ignorées par le kit, comme documenté ; Orientation et les autres pistes gardent leur comportement.

**Avant → après :** écriture directe de `handle.follow` → méthode officielle testée ; aucun callback de fin → **exactement 1 callback après nettoyage**, même après appels Stop répétés. Tests dédiés changement/détachement de cible, fin naturelle/Release/Stop/retrait externe, erreur et yield du callback.

**Fichiers :** `tool/fx_kit.lua`, `tool/test_fx_kit.py`, `tool/luau_roblox_mock.luau`, `CLAUDE.md`, `DATAKY_FX_STUDIO.md`.

**Reste :** suivi du rig animé et ordonnancement réel de task.defer **à vérifier dans Studio par Claude**.

## 6 · Préchargement et inventaire des textures

**Fait.** `FX.preloadTextures(recipeOrLibrary)` transmet à `ContentProvider:PreloadAsync` une liste triée/dédoublonnée d'URI explicites. Elle peut yield et s'appelle au démarrage. `FX.listTextures(recipeOrLibrary)` liste sans précharger. Sont inclus : ParticleEmitter/Beam/Trail.Texture, MeshPart.TextureID, SpecialMesh.TextureId ; MeshId est exclu. Les textures implicites par défaut Roblox ne sont pas inventées.

Une nouvelle bibliothèque exportée propose `Recipes:listTextures()` / `Recipes.listTextures()`, qui renvoie une copie défensive. La méthode est dans la métatable, ainsi `pairs(Recipes)` ne parcourt que les recettes. Une recette nommée `listTextures` conserve sa clé : utiliser alors `FX.listTextures(Recipes)` ou `getmetatable(Recipes).listTextures()`. Les bibliothèques anciennes sans cette méthode restent acceptées, y compris des recettes nommées `version` ou `nodes`.

**Avant → après :** API absente → appel ContentProvider unique avec les URI uniques. Le test d'export/kit compare **4 URI** uniques, vérifie toutes les variantes HTTP/HTTPS/www et slash facultatif de l'URL Roblox, puis preload/prepare/play. Les tests vérifient aussi le yield autorisé du préchargement et l'absence de yield dans play.

**Fichiers :** `tool/fx_kit.lua`, `tool/fx_export.py`, `tool/test_fx_kit.py`, `tool/test_fx_library_textures.py`, `tool/luau_roblox_mock.luau`.

**Reste :** autorisations des assets et première apparition réelle après chargement **à vérifier dans Studio par Claude**.

## 7 · Faux positif abrupt_transparency

**Fait.** Une particule qui finit avec une Size proche de zéro ne reçoit plus cet avertissement. Les seuils restent centralisés : Size finale doit dépasser `max(0,05 stud, 5 % du pic)` **et** Transparency finale doit être <0,95 pour signaler une fin abrupte.

**Avant → après :** exemple Size 0,34→0 et Transparency 0→0,4 : **1 → 0 avertissement**. Tests également à 0,001 et 0,049 stud, plus un cas résiduel à 0,1 qui avertit. Sur les 18 recettes courantes Bulbito : **5 → 2 abrupt_transparency** ; les trois retirés sont `A1_Blow/Ting`, `A1_Twirl/Stars`, `A3_Glint/Star`, qui rétrécissent déjà. `A1_Tracer/Glow` et `A3_Fuse/Spark` gardent leur diagnostic et leur taille résiduelle. L'ancien test de compte a été actualisé pour cette nouvelle règle ; aucune fixture changée.

**Fichiers :** `tool/fx_warnings.py`, `tool/test_fx_warnings.py`.

**Reste :** le seuil « proche de zéro » est une heuristique documentée.

## 8 · flat_layer_negative_zoffset

**Fait.** Diagnostic pour `VelocityPerpendicular` + `EmissionDirection: Top` + `ZOffset < 0`. Il reste consultatif et ne rend pas une recette invalide.

**Avant → après :** `Splat_NegativeZOffset` : **0 → 2** diagnostics, exactement `splat` et `ripple`. `A1_Splat` : **0 → 0**. Tests de non-déclenchement sur FacingCamera ou direction Front.

**Fichiers :** `tool/fx_warnings.py`, `tool/test_fx_warnings.py`.

**Reste :** le défaut fourni est une observation réelle conservée ; le comportement exact des couches après ajustement de ZOffset est **à vérifier dans Studio par Claude**.

## 9 · Contraste sur sol sombre

**Fait.** Nouveau `dark_ground_contrast`, sans ID ni nom spécial de fixture dans la production. Détection : LightEmission <0,2, luminance maximale <0,15 et présence potentielle sans soutien clair couvrant toute la même période. Un soutien clair exige LightEmission ≥0,2, luminance maximale ≥0,45, opacité maximale ≥0,05 et taille maximale >0,05 stud. La luminance utilise les coefficients RGB 0,2126 / 0,7152 / 0,0722 sur la couleur auteur ; ce n'est pas une mesure d'éclairage natif.

Les intervalles incluent timing, Count/Rate, Enabled et ses pistes booléennes, Lifetime maximale et TimeScale. Une simple intersection ne suffit pas ; l'union des fenêtres claires doit couvrir la période sombre. Les couches désactivées, sans émission, entièrement transparentes ou de taille nulle ne masquent pas le risque. Tous les seuils sont dans `THRESHOLDS`.

**Avant → après :** `Gather_DarkInkOnly/swirl` : **0 → 1** avertissement, luminance max **0,144364**. `A2_Gather` : **0 → 0**, grâce à `swirlLight`. Tests dédiés soutien absent/décalé/trop court, Count=0, Rate=0, Enabled=false/animé, TimeScale et visibilité nulle.

| Corpus courant | abrupt_transparency avant/après | Contraste sombre avant/après | Autres diagnostics |
| --- | --- | --- | --- |
| Bulbito, 18 recettes | 5 / 2 | 0 / 3 | 8 pale_small_texture, 2 flipbook_empty_start, 1 additive_white inchangés |
| Blueberrinni, 12 recettes | 0 / 0 | 0 / 2 | Aucun autre avertissement courant |

Les trois nouveaux avis Bulbito concernent `A2_Ring/Skid`, `A3_Ground/Scorch`, `A3_Ground/Crack`. Les deux avis sur Blueberrinni courant concernent **`A2_Slam/puddle` et `A2_Whirl/spiral`**, déjà observés visibles. Ce sont des avis de contraste conservateurs, pas une reclassification de leur observation Play. Une couche sombre peut rester lisible grâce au décor ou à un soutien partiel : les fenêtres plus longues que le soutien déclenchent encore cet avis. Aucun nouvel avertissement alpha de visibilité n'apparaît sur les émetteurs Bulbito marqués visibles ; le Pillar invisible conserve flipbook_empty_start. Les statuts unknown restent inconnus.

**Fichiers :** `tool/fx_warnings.py`, `tool/test_fx_warnings.py`, `rendus/lot3-warnings.py`. Preuves complètes par recette/émetteur : `rendus/lot3-warnings-{before,after}.json`.

**Reste :** approximation de présence, sans recouvrement spatial, analyse de la texture réelle, éclairage ni simulation des propriétés animées autres qu'Enabled. Luminance/contraste et avis conservateurs **à vérifier dans Studio par Claude**. Aucun statut visible/invisible fourni n'a été modifié ou présenté comme déduit par cette heuristique.

## 10 · Fond dark et lignes par fond

**Fait.** `--background dark` : ciel de nuit RGB `[0.035,0.045,0.08]`, sol gris sombre `[0.16,0.16,0.17]`. Disponible en CLI Python/Node, API Python, MCP et render-batch. `--backgrounds roblox,dark` / `backgrounds=["roblox","dark"]` donne une ligne par recette puis par fond, mêmes caméra/instants/graine. Les deux options sont exclusives. Le JSON inclut `rows` et `sheet`, les frames ont des noms distincts. Les légendes sont tronquées dans leur cellule sans déborder sur la suivante.

**Avant → après :** pas de preset dark ni de comparaison multi-fonds → deux presets et **4 lignes pour 2 recettes × 2 fonds**. Test pixel Chromium réel sur scène vide : ciel sombre attendu **[9,11,20]**, ciel jour **[163,207,240]** (tolérance 2/255), sol sombre 40–75/255 dans chaque canal contre ≥160/255 de jour. Ces assertions passent. Le test compare aussi caméra, instants, ordre des lignes, dimensions et huit noms de frames uniques. Les tests Python exercent réellement CLI, MCP et batch.

Planche produite et inspectée : **`rendus/lot3-backgrounds.png`**, 1440×1168, 4 lignes × 3 instants (0,10 / 0,25 / 0,40 s). Lignes A/B : Gather_DarkInkOnly jour/sombre ; C/D : A2_Gather jour/sombre. Le tourbillon sombre y perd du contraste, et la couche swirlLight apporte de la lisibilité. Métadonnées : `rendus/lot3-backgrounds.json`.

**Fichiers :** `editor/emulator.js`, `tool/fx_render.cjs`, `tool/fx_tools.py`, `tool/fx.py`, `tool/fx_mcp.py`, `tool/test_fx_render.cjs`, `tool/test_fx_emulator.cjs`, `tool/test_fx_tools.py`.

**Reste :** preset approché, sans lire le Lighting de vfx.rbxl ; correspondance avec le rendu natif **à vérifier dans Studio par Claude**.

## 11 · Bonus : exporter les textures utilisées

**Fait.** Bouton **Dataky FX → Exporter les textures utilisées**, après connexion en Edit. Également commande du pont `export_used_textures` via `POST /api/preview`, ou `_G.DatakyFXBridge.exportUsedTextures()`. Le plugin collecte ParticleEmitter/Beam/Trail.Texture de la place et les champs Texture/TextureID/TextureId littéraux des ModuleScripts de recettes (nodes/version). Il n'exécute jamais ces modules. Les sources illisibles et expressions dynamiques sont signalées comme scan partiel.

Le serveur n'accepte que le pont actif et écrit atomiquement `tool/used_textures/<game.Name nettoyé>.txt`, hors catalogue. IDs positifs, triés, dédoublonnés, une ligne par ID : directement compatible `--exclude-file`. Les noms Windows invalides/réservés sont neutralisés. L'ancienne connexion sans cette commande reçoit une erreur explicite invitant à mettre à jour le plugin.

**Avant → après :** scan manuel sans fichier officiel → fixture mock de **7 IDs uniques** issus des objets et modules ; les doublons et rbxasset:// intégrés ne deviennent pas de faux IDs catalogue. Deux expressions dynamiques et une source inaccessible sont signalées. Test fichier : `[100,2,100,0002]` → `2\n100\n`, relu directement par `excluded_ids`. Tests HTTP : pont inconnu refusé sans écriture ; pont actif accepté ; autre client ne peut écraser le fichier ; commande exposée et ancien pont refusé.

**Fichiers :** `tool/fx_plugin.lua`, `tool/fx_server.py`, nouveaux `tool/fx_used_textures.py`, `tool/test_fx_used_textures.py`, ajouts `tool/test_fx_server.py`, package régénéré.

**Reste / portée :** analyse lexicale des recettes littérales, pas un parseur Luau général ; commentaires/chaînes peuvent surinclure des IDs. Les textures calculées ou chargées au runtime ne sont pas évaluées ; le diagnostic les laisse à compléter. Le nom de fichier vient du nom du DataModel. Scan de la vraie place et sources protégées **à vérifier dans Studio par Claude**.

## Tests finaux et preuves

Toutes les suites ont été exécutées après les dernières modifications de production, avec Luau activé et Chromium réel disponible. Aucun test ignoré.

| Suite | Sortie réelle finale | Log |
| --- | --- | --- |
| Python complet, dont mock Luau | `Ran 160 tests in 43.585s` · `OK` | `rendus/lot3-tests-python.txt` |
| JavaScript complet | 96 tests · 96 pass · 0 fail · 0 skipped · 8128,3477 ms | `rendus/lot3-tests-javascript.txt` |
| Frontend | `PASS: five real editor templates, native schema defaults, references, motion, sequence codecs, frontend invalid-input checks.` | `rendus/lot3-tests-frontend.txt` |
| Compilation Luau kit/plugin/runtime | 3/3 réussies | `rendus/lot3-package-verification.json` |
| Sources du package vs fichiers | plugin=true, runtime=true | même JSON |
| Catalogue/fixtures/projets protégés | 10 176 contrôlés · 0 différence | `rendus/lot3-final-audit.json` |
| Validité des recettes | projets 26, Bulbito 19, Blueberrinni 14 | même JSON |

Les refus HTTP 400/403/409 imprimés par la suite Python sont les scénarios de refus attendus. La première passe de début Python a croisé une édition du test de garde et échoué sur son ancienne chaîne de découpage ; elle ne constitue pas le résultat final. Les passes P0/P1 et finale complètes sont vertes. Les vérifications natives utilisent le mock, sans installation ni lancement de Play dans Studio.

Commandes depuis la racine :

```powershell
$env:PATH = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin;' + $env:PATH
$env:PYTHONUTF8 = '1'
$env:DATAKY_LUAU = 'C:\Users\esteb_9qwvhb8\.codex\tmp\gift-ledger-luau-0.741\luau.exe'
python -m unittest discover -s tool -p 'test_*.py'
node tool/test_fx_frontend.cjs
node --test tool/test_fx_emulator.cjs tool/test_fx_preview_ui.cjs tool/test_fx_curves.cjs tool/test_fx_render.cjs tool/test_fx_texture_bounds.cjs
python tool/fx_package.py
python rendus/lot3-verify-package.py
python rendus/lot3-audit.py
python rendus/lot3-warnings.py --out rendus/lot3-warnings-after.json
python tool/benchmark_fx_kit.py --out rendus/lot3-kit-after-benchmark.json
```

Le fichier baseline `rendus/lot3-protected-before.json` ne doit pas être recréé ; le script d'audit refuse de l'écraser. Aucun nouvel outil global installé. Documentation des APIs, seuils, caméra et fonds mise à jour dans `CLAUDE.md` et `DATAKY_FX_STUDIO.md`.

## Vérifications manuelles dans Studio

Installer le package régénéré `editor/DatakyFXStudio.rbxmx`, puis redémarrer Studio pour charger ce source. Vérifier zéro message de connexion dans les logs serveur/client au lancement de Play ; réexporter une bibliothèque pour disposer du nouveau kit, ou remplacer seulement DatakyFXKit à côté d'une ancienne bibliothèque.

```lua
local FX = require(script.Parent.DatakyFXKit)
local Recipes = require(script.Parent.MesEffets)
FX.preloadTextures(Recipes) -- au démarrage, peut yield
FX.prepare(Recipes.A1_Berry)
local h = FX.play(Recipes.A1_Berry, muzzle.WorldCFrame, {
    follow=muzzle,
    onFinished=function(done) print("Effet nettoyé", done.stopped) end,
})
h:SetFollow(projectile)
-- À l'impact :
h:Release({hideParts=true})
```

Vérifier les trois Parts du projectile masquées et les gouttes encore présentes, fin du suivi au Release, callback unique après drainage, performance sur le rig et le pic Maelstrom à 11 pièces. En Edit connecté : exporter les textures utilisées puis lancer une recherche avec le fichier `--exclude-file`. Ces observations et les mesures mobile restent **à vérifier dans Studio par Claude**.
