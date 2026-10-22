# Rapport des demandes Claude — 22 octobre 2026

Les lots ont été livrés et vérifiés dans l’ordre **P0 → P1 → P2**. Aucune commande git n’a été utilisée. Le catalogue (`images/`, `previews/`, `source/`, `beams/`, `meshes/`, `tags/`, `textures.*`, `catalogue.html`) et les références dans Documents n’ont pas été modifiés. Le cache alpha est un nouveau fichier séparé. Les 21 projets existants passent toujours la validation version 1.

## Ce qui est fait, point par point

| Point | Résultat | Fichiers principaux |
| --- | --- | --- |
| P0.1 Squash | VelocityParallel corrigé : négatif longitudinal, positif transversal. Briques sparks et charge corrigées. Tests géométriques ±2 et non-régression FacingCamera. | `editor/emulator.js`, `tool/fx_modules.py`, `tool/test_fx_emulator.cjs` |
| P0.2 Fond | Fond de recette utilisé par défaut, option « Fond de la recette », presets forcés prioritaires et preset roblox avec ciel bleu clair/sol gris clair. CLI et MCP compatibles. | `editor/emulator.js`, `editor/app.js`, `editor/index.html`, `tool/fx.py`, `tool/fx_mcp.py`, `tool/fx_render.cjs` |
| P0.3 Message plugin | Message de connexion une seule fois en Edit, jamais en Play, y compris après rechargement du pont. Test Luau du garde. | `tool/fx_plugin.lua`, `tool/test_fx_rbxmx.py`, plugin régénéré |
| P1.4 Emit | Mode Timeline/Libre, horloge Libre continue, bursts manuels, continus au Rate, quantité par émetteur, sélection avec descendants, Emit tout avec counts d’origine et Vider. Commandes natives ajoutées au pont. | `editor/app.js`, `editor/emulator.js`, `editor/index.html`, `editor/styles.css`, `tool/fx_runtime.lua`, `tool/fx_plugin.lua`, `tool/fx_server.py`, `tool/test_fx_sandbox.py` |
| P1.5 Enabled | Interrupteurs arbre/propriétés ; aperçu seulement en Libre, propriété de recette en Timeline ; pistes grisées. Modifications simples des propriétés en direct. Les bursts automatiques respectent aussi Enabled=false. | Même ensemble UI/runtime ; tests émulateur/UI/serveur/sandbox |
| P1.6 Clavier | Tous les raccourcis obligatoires, aide `?`, infobulles des contrôles ajoutés, sélection multiple, copie/collage JSON avec enfants, références, pistes et paramètres entre projets. Gardes champs/dialogues, raccourcis historiques conservés. | `editor/app.js`, `editor/index.html`, `editor/styles.css`, `tool/test_fx_preview_ui.cjs` |
| P1.7 Kit | `FX.play`, handles indépendants, CFrame tournée, scale, speed, follow fonction/Attachment/Bone/BasePart, hold/Release/Stop/Move/Part, freeze/unfreeze, animations, qualité Auto/Low et nettoyage. `play` ne yield pas. | `tool/fx_kit.lua`, `tool/luau_roblox_mock.luau`, `tool/test_fx_kit.py` |
| P1.8 Bibliothèque | Plusieurs fichiers/IDs vers un module de données avec clés courtes, plus DatakyFXKit.lua voisin ; doublons refusés. Disponible CLI, Python et MCP. | `tool/fx.py`, `tool/fx_export.py`, `tool/fx_tools.py`, `tool/fx_mcp.py`, tests outils/kit |
| P1.9 Rayon | params au niveau recette, scaleWith sur propriétés numériques explicites de ParticleEmitter, validation, ratios ciblés dans le kit, curseurs d’aperçu appliqués aussi aux animations. | `tool/fx_schema.py`, `tool/fx_kit.lua`, `editor/app.js`, tests sandbox/kit/UI |
| P2.10 Builder | Recipe avec part/att/em/trail/light/anim/flip/merge/save ; NS/CS/NR ; module importable et documenté. | `tool/fx_builder.py`, `tool/test_fx_builder.py` |
| P2.11 Includes | Compose accepte include, at, position, orientation YXZ et scale. IDs/références/pistes/paramètres remappés ; fichiers relatifs au plan ; bonus positionKeys pour une trajectoire de translation. | `tool/fx_builder.py`, `tool/fx_modules.py`, `tool/fx.py`, tests builder/outils |
| P2.12 Avertissements | Début OneShot peu opaque + vie courte, opacité moyenne faible, texture fine/pâle petite, additif saturé, Squash positif parallèle, fins Transparency/Size abruptes et grille estimated. Diagnostics CLI/MCP séparés des erreurs de validité. | `tool/fx_warnings.py`, `tool/fx_texture_cache.py`, `tool/texture_frames.json`, `tool/fx_tools.py`, `tool/fx.py`, `tool/fx_mcp.py`, `tool/test_fx_warnings.py` |
| P2.13 Recherche | Compact CLI/MCP, exclusions avant total/pagination, fichier ou IDs, planche explicite annotée avec grille et badge USED. Outil MCP texture_sheet ajouté. | `tool/fx.py`, `tool/fx_tools.py`, `tool/fx_mcp.py`, `editor/emulator.js`, tests outils/rendu |
| P2.14 Rendu | render-batch : un Chromium pour tous les jobs, pages fermées entre jobs. Cadrage --fit avec descendants, ou --focus/--radius. API Python/MCP et erreurs de ciblage explicites. | `tool/fx_render.cjs`, `tool/fx_tools.py`, `tool/fx.py`, `tool/fx_mcp.py`, `tool/test_fx_render.cjs` |
| P2.15 Focus | Relais conditionnel des signaux de focus, booléen validé par le serveur et avertissement pendant une lecture native explicitement signalée inactive. Initialisation inconnue, aucun état inventé. | `tool/fx_plugin.lua`, `tool/fx_server.py`, `editor/app.js`, `editor/index.html`, tests serveur/UI |
| P2.16 Docs | Guide Claude et manuel mis à jour : Squash, flipbooks, Libre, raccourcis, kit, anciens exports, builder, includes, paramètres, recherche et rendu. | `CLAUDE.md`, `DATAKY_FX_STUDIO.md`, présent rapport |

Le plugin final est `editor/DatakyFXStudio.rbxmx`. Sa source embarquée a été comparée aux fichiers runtime et pont actuels après régénération.

La revue a également corrigé : réinitialisation native après Stop ou changement de mode ; première modification Libre native avant initialisation ; fuite d’état entre projets ayant les mêmes IDs ; Emit pendant une pause ; durée native mise à jour ; traitement RenderFidelity des MeshParts ; nettoyage du kit avec hold et bursts seuls ; Release pendant freeze ; cache JSON corrompu ; sortie des avertissements sur une console Windows cp1252.

## Ce qui reste non fait ou incertain

- **Bonus keybinds.json non réalisé** : tous les raccourcis demandés sont présents, mais pas configurables par fichier.
- **Aucun test dans Roblox Studio** : tout comportement natif nouveau a été contrôlé par compilation et mock Luau, pas observé dans le moteur. Le pont Libre et les captures réelles doivent encore être essayés dans Studio.
- **Playwright absent** : les deux tests de capture Chromium réelle ont été ignorés. Le lancement unique du batch, son nettoyage, le cadrage géométrique et le badge USED sont testés avec un pilote/canvas injecté ; ni le gain de temps réel ni les PNG finaux ne sont prétendus mesurés.
- **FacingCamera** reste inchangé et non mesuré. Le preset roblox est un décor approché, pas une reproduction exacte de Lighting.
- **Focus Studio** : les [signaux documentés UserInputService](https://create.roblox.com/docs/reference/engine/classes/UserInputService#WindowFocused) concernent le viewport principal. Leur livraison dans ce plugin en Edit et leur correspondance avec le focus de toute l’application restent à vérifier. L’avertissement est conditionnel à un signal explicite ; une absence de signal reste inconnue.
- **OneShot** : le cas mesuré fourni est conservé comme fait. Les avertissements alpha utilisent les miniatures et des seuils heuristiques ; ils ne prouvent pas le séquencement natif ni les permissions de l’asset. Les dimensions Custom utilisent les nombres de colonnes/lignes [documentés par Roblox](https://create.roblox.com/docs/reference/engine/classes/ParticleEmitter#FlipbookSizeX). Les PNG entrelacés donnent un diagnostic au lieu d’une couverture inventée. Le cache est paresseux, invalidé par SHA-256 ; le script peut préremplir tout le catalogue.
- **MeshParts du kit** : appeler `FX.preload(recipe)` avant play. Ce préchargement peut yield ; play clone ensuite les objets préparés sans yield. Un MeshPart non préparé est refusé clairement.
- **Trails natifs** : leur historique ne peut pas être figé fidèlement ; il peut disparaître pendant une capture figée. La pause native historique refuse les effets contenant un Trail ; freeze du kit ne prétend pas figer cet historique.
- **Navigation temporelle native** : flèches/Début/Fin/événements déplacent la tête dans l’interface et l’émulateur. Le natif doit repartir de 0 pour reconstruire son historique ; le message correspondant est affiché.
- **Édition Libre native** : les changements simples conservent l’historique ; une modification de structure, suppression de propriété ou changement de géométrie MeshPart peut reconstruire l’aperçu.
- **Includes et rotations animées** : exactitude aux points clés, mais l’interpolation Euler entre clés composées peut différer. Utiliser des clés intermédiaires pour les tours complets.
- **Compatibilité** : les méthodes historiques apply/play/pause/resume/stop/clear/status/adopt restent disponibles. Le singleton et la translation d’origine de l’export `.lua` historique restent inchangés. La correction volontaire des bursts automatiques Enabled=false aligne ce cas sur la demande.

## Tests exécutés et sorties réelles

Python n’était pas disponible dans le PATH de cette session. L’interpréteur local utilisé est `C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe` (Python 3.13.9). Luau : `C:\Users\esteb_9qwvhb8\.codex\tmp\gift-ledger-luau-0.741\luau.exe`. Aucun outil n’a été installé globalement.

Le premier essai Python a échoué faute d’interpréteur dans le PATH, puis un sous-processus de test a rencontré la même absence. Le PATH local a été corrigé pour les commandes suivantes ; le test stdio utilise désormais sys.executable. Le rendu réel reste ignoré faute de Playwright.

| Lot | Vérification | Sortie finale du lot |
| --- | --- | --- |
| P0 | Frontend + émulateur/UI/courbes | Frontend PASS ; 50 tests, 50 pass, 0 fail |
| P0 | Cinq suites Python demandées, avec Luau | Ran 67 tests in 16.038s — OK (skipped=1) |
| P1 | Frontend + émulateur/UI/courbes | Frontend PASS ; 64 tests, 64 pass, 0 fail |
| P1 | Suites demandées + sandbox + kit | Ran 85 tests in 17.751s — OK (skipped=1) |
| P2 final | Frontend | PASS: five real editor templates, native schema defaults, references, motion, sequence codecs, frontend invalid-input checks. |
| P2 final | Émulateur/UI/courbes/rendu | tests 82 ; pass 81 ; fail 0 ; skipped 1 ; duration_ms 827.5703 |
| P2 final | Toutes les suites Python ci-dessous | Ran 113 tests in 19.677s — OK (skipped=1) |
| P2 final | Compilation Luau runtime/kit/plugin | PASS: fx_runtime.lua, fx_kit.lua, fx_plugin.lua compiled |
| P2 final | Tous les projets existants | COMPATIBILITY: 21 existing projects valid |
| P2 final | Sources embarquées du plugin | PASS: packaged plugin contains current runtime and bridge sources |

Commandes finales :

```powershell
$env:PATH = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin;' + $env:PATH
$env:DATAKY_LUAU = 'C:\Users\esteb_9qwvhb8\.codex\tmp\gift-ledger-luau-0.741\luau.exe'
node tool/test_fx_frontend.cjs
node --test tool/test_fx_emulator.cjs tool/test_fx_preview_ui.cjs tool/test_fx_curves.cjs tool/test_fx_render.cjs
Push-Location tool
python -m unittest test_fx_server test_fx_templates test_macro test_fx_rbxmx test_fx_tools test_fx_sandbox test_fx_kit test_fx_builder test_fx_warnings
Pop-Location
python tool/fx_package.py
```

Logs complets : `rendus/tests-P1-python.txt`, `rendus/tests-P2-frontend.txt`, `rendus/tests-P2-javascript.txt`, `rendus/tests-P2-python.txt`. Les réponses HTTP 400/403/409 affichées dans le log correspondent aux scénarios de refus testés, pas à des échecs de la suite.

Des commandes réelles ont aussi validé le cache de `70418763522849` (analyzed: 1, errors: []), la recherche compacte star, la composition avec include relatif et positionKeys, et les exports bibliothèque d’exemples. La validation de Demo_Avertissements renvoie notamment positive_parallel_squash, abrupt_transparency, abrupt_size, additive_white, estimated_grid et flipbook_empty_start.

## Comment tester à la main

Depuis la racine du dépôt, définir l’interpréteur si nécessaire :

```powershell
$Python = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $Python tool/fx_server.py
```

Dans l’atelier, ouvrir **Recette JSON** et importer `rendus/verification-demandes/Demo_Libre.json` (ou l’enregistrer dans les projets via la commande save ci-dessous). Sélectionner `sparks`, basculer **Libre**, régler la quantité, puis **Emit**, **Emit sélection**, **Emit tout**, **Vider**. La fumée continue suit Rate ; les bursts n’émettent qu’à la demande. Tester Enabled dans l’arbre et les propriétés : pas de modification JSON en Libre ; en Timeline, modification enregistrée et piste grisée. Le curseur radius ne change que l’anneau.

Tester **?**, puis Espace/Maj+Espace, E/Maj+E, T, Tab, C, flèches, Début/Fin, [/], L, F/Maj+F, G, M, 1–5, ↑/↓, Alt+↑, Ctrl+C/V, Ctrl+E/Ctrl+Maj+E. Dans un champ ou dialogue, les nouveaux raccourcis doivent rester inactifs ; Ctrl+S conserve son comportement historique. Copier une branche et la coller dans un autre projet doit remapper enfants et références.

Régressions à vérifier : Libre → Pause → E conserve la pause ; Libre → Stop → T puis modification de Rate doit réinitialiser correctement le sandbox natif ; passer à un autre projet remet l’état d’aperçu à zéro. Choisir « Fond de la recette », puis « Roblox - jour » pour comparer le jaune additif sur clair.

Commandes prêtes à exécuter :

```powershell
& $Python tool/fx.py save rendus/verification-demandes/Demo_Libre.json
& $Python tool/fx.py validate rendus/verification-demandes/Demo_Avertissements.json
& $Python tool/fx.py compose rendus/verification-demandes/plan.json --out rendus/verification-demandes/Complet.json
& $Python tool/fx.py textures --query star --compact --no-sheet --exclude-file rendus/verification-demandes/used.txt
& $Python tool/fx.py sheet 15268066299 70418763522849 --exclude-file rendus/verification-demandes/used.txt --out rendus/verification-demandes/choix.png
& $Python tool/fx.py render rendus/verification-demandes/Demo_Libre.json --fit root --background roblox
& $Python tool/fx.py render rendus/verification-demandes/Demo_Libre.json --focus 0,1,0 --radius 4
& $Python tool/fx.py render-batch rendus/verification-demandes/jobs.json
& $Python tool/fx.py export rendus/verification-demandes/Demo_Libre.json rendus/verification-demandes/Complet.json --format library --out exports/verification-demandes/Demos.lua
```

Les commandes sheet/render/render-batch nécessitent Playwright et Chromium. Leurs PNG n’ont pas été produits dans cette session. Les JSON de démonstration, plan, manifeste batch, fichier used et exports de bibliothèque existent déjà dans `rendus/verification-demandes/` et `exports/verification-demandes/`.

Dans Studio, installer le plugin régénéré puis redémarrer, cliquer **Dataky FX → Connexion**, ouvrir l’aperçu natif et refaire les boutons Libre. La perte de focus doit être testée comme signal conditionnel, sans conclure qu’un état absent signifie « actif ».

Pour le kit, placer `exports/verification-demandes/Demos.lua` et `DatakyFXKit.lua` dans des ModuleScripts voisins et exécuter côté client :

```lua
local FX = require(script.Parent.DatakyFXKit)
local Recipes = require(script.Parent.Demos)
local a = FX.play(Recipes.Demo_Libre, CFrame.new(0, 3, 0), {params={radius=4}})
local b = FX.play(Recipes.Demo_Libre, CFrame.new(12, 3, 0) * CFrame.Angles(0, math.pi/2, 0),
    {hold=true, params={radius=8}, quality="Low"})
-- Vérifier deux effets indépendants, puis FX.freeze()/FX.unfreeze().
-- a:Move(CFrame.new(0,6,0)); b:Release(); a:Stop().
```

Vérifier visuellement la rotation, le rayon ciblé, l’indépendance, le suivi d’un Attachment/Bone et la disparition du dossier après les dernières particules. Pour une recette MeshPart, appeler FX.preload avant FX.play.

## Lot 2

Reprise et vérification du 22 octobre 2026. Les mentions d’absence de Playwright dans les sections du lot 1 sont historiques : **Chromium réel a été exécuté avec succès pour le lot 2**, après la reprise avec accès au navigateur installé. Aucune commande git n’a été utilisée. Les 20 fichiers de fixtures Bulbito sont inchangés octet pour octet ; les empreintes des quatre index du catalogue sont également inchangées. Aucun fichier du catalogue ni des références dans Documents n’a été édité. Les 21 projets existants restent valides.

### Avertissements avant / après

Périmètre : les **18 recettes actuelles**, sans `Pillar_InvisibleInPlay.json` ni `play_observations.json`. Avant : diagnostics du lot 1, avec les comptes fournis dans la demande ; après : recomptage des recettes immuables avec les règles livrées et un fichier de surcharges vide.

| Code | Avant : avertissements | Après : avertissements par défaut | Après : infos optionnelles |
| --- | ---: | ---: | ---: |
| abrupt_size | 58 | 0 | 0 |
| estimated_grid | 51 | 0 | 32 |
| flipbook_low_opacity | 8 | 0 | 0 |
| pale_small_texture | 7 | 8 | 0 |
| abrupt_transparency | 5 | 5 | 0 |
| flipbook_empty_start | 2 | 2 | 0 |
| additive_white | 1 | 1 | 0 |
| **Total** | **132** | **16** | **32** |

Les 32 infos correspondent à une occurrence par texture **dans chaque recette** ; elles concernent 14 textures distinctes sur l’ensemble du corpus. Elles sont masquées sans `--infos` ou `--verbose`. `grid-confirm ID 4` enregistre une confirmation manuelle hors catalogue ; aucun ID n’a été confirmé automatiquement et `tool/grid_overrides.json` est livré avec `grids: {}`.

Les seuils sont centralisés dans `tool/fx_warnings.py::THRESHOLDS`. La visibilité mesure la surface opaque équivalente moyenne `∫ alpha × Size² × (1 − Transparency) dt` sur une vie normalisée, avec seuil de 0,01 stud². L’intégration suit les clés des courbes et les cases OneShot ; les autres modes utilisent l’alpha moyen des cases. Un pixel opaque compte pleinement, sans seconde pénalité de couverture. Le risque de début OneShot vide reste indépendant : alpha moyen du premier quart < 0,08 et Lifetime maximale ≤ 0,5 s.

Les fins de courbe partagent le seuil de Transparency < 0,95. Une taille finale après un fondu ne déclenche rien. Appliquer uniquement ce filtre aurait laissé deux `abrupt_size` sur `A1_Tracer/Glow` et `A3_Fuse/Spark`. Pour conserver l’information et atteindre les zéro doublons demandés, leur taille résiduelle est regroupée dans `abrupt_transparency`, dans le message et les détails `abrupt_size: true` / `end_size`. Les cinq problèmes de transparence et le problème additif restent signalés.

Résultats des observations Play :

- **15 émetteurs marqués `visible` : aucun** `pale_small_texture`, `flipbook_low_opacity` ou `flipbook_empty_start`.
- **`Pillar_InvisibleInPlay/Burst` : `flipbook_empty_start` conservé**, vérifié séparément des 18 recettes du tableau.
- **`unknown`** : `A1_Muzzle/Flash` et `A3_Glint/Shine` gardent `flipbook_empty_start` ; `Idle_Puff/Wisp` ne reçoit aucun diagnostic de visibilité.
- Les huit `pale_small_texture` restants portent sur des émetteurs sans statut dans les observations : `A1_Hit/Sparks`, `A1_Muzzle/Sparks`, `A2_FireTrail/Embers`, `A2_Flare/Embers`, `A2_Vents/Embers1` à `Embers4`. Leurs surfaces estimées vont de 0,0047601 à 0,0095532 stud². Leur visibilité native n’est pas déduite de ces estimations.
- La CLI affiche un résumé par code puis les détails, et les infos séparément. `validate A1_Muzzle.json`, avec et sans `--infos`, retourne **0** malgré les avertissements. MCP expose aussi `warning_counts`, `infos`, `info_counts` et `include_infos`.

Les diagnostics complets avant/après, les seuils et les métriques par émetteur sont dans `rendus/lot2-warnings.json`. Le recomptage final et le contrôle SHA-256 sont reproductibles avec `rendus/lot2-final-audit.py` ; leur sortie est dans `rendus/lot2-final-audit.json`.

### Cadrage corrigé

`--fit` échantillonne uniquement les particules vivantes à l’union des instants effectivement rendus. Une Part inclut ses émetteurs descendants ; un émetteur sélectionné limite la contribution à sa branche. Le percentile des centres rejette les particules isolées, puis le calcul ajoute l’emprise visible du quad à sa taille réelle, avec demi-taille, rotation et Squash. Les cellules actives du flipbook et leur interpolation sont prises en compte.

Le cadrage conserve par défaut 90 % de l’énergie de contraste alpha² de chaque cellule, en proportion de son énergie totale : les pixels isolés et halos faibles ne gonflent plus les bornes, et une texture uniformément pâle garde sa géométrie. Le contour inclut une marge d’un texel. `--fit-percentile 100` conserve tous les centres et tout l’alpha ; une image inaccessible conserve prudemment le quad entier. Les pixels rendus et les avertissements de visibilité ne sont pas modifiés par cette analyse de cadrage. La caméra ajuste les points du contour dans son repère, sans ajouter la profondeur d’un cube autour des billboards.

La caméra est raffinée après recentrage, jusqu’à huit passes, afin que les billboards orientés vers sa position conservent une emprise correcte. Des régressions couvrent FacingCameraWorldUp et VelocityParallel sur une Part à 1 000 studs, avec Squash important. `--fit-all` conserve le comportement historique sur toute la durée. Sans particules aux instants demandés, la Part porteuse et ses Attachments servent de repli avec un message explicite. Les comparaisons partagent une caméra qui inclut aussi les recettes en repli ; un test vérifie explicitement une recette avec particules et une autre sans, éloignée de 100 studs. `--focus/--radius` ajuste une sphère visant 87,5 % de la plus petite dimension.

Mesures **des pixels réels Chromium**, sur fond noir, sans sol, à 480 × 270 ; pixel visible si max(R,G,B) > 12, comme dans le test de régression :

| Rendu | Instant demandé | Hauteur visible | Fraction de hauteur | Muzzle / Flash |
| --- | ---: | ---: | ---: | ---: |
| Sphère de 6 studs, focus/radius 3 | 0 | 236 px | 87,41 % | — |
| A1_Muzzle, fit Muzzle | 0,02 | 81 px | 30,00 % | 1,00 |
| A1_Muzzle, fit Flash | 0,02 | 81 px | 30,00 % | — |
| A1_Muzzle, fit Muzzle | 0,06 | 175 px | 64,81 % | 1,00 |
| A1_Muzzle, fit Flash | 0,06 | 175 px | 64,81 % | — |

La simulation quantifie les deux instants à 1/60 et 4/60 s ; le calcul des bornes utilise exactement les mêmes instants que les images. L’échec initial à **0,1296296** de hauteur est corrigé. Les assertions du test `real Chromium pixel regression` sont inchangées : sphère entre 75 et 90 %, Muzzle ≥ 30 % et ≥ 0,7 × Flash à chacun des deux instants. Un ancien contrôle CLI comparait la diagonale d’une boîte 3D ; il compare désormais les distances caméra avec le même rapport maximal de 1,2, car la profondeur de cette boîte ne détermine plus le cadrage des quads. Le test pixel reste la vérification de l’occupation visible.

Mesures et captures : `rendus/lot2-framing-final.json` et `rendus/lot2-framing-final/`. Le calcul reste un cadrage robuste : le percentile 90 peut volontairement laisser des extrémités hors champ ; utiliser 100 pour les conserver. Les miniatures, l’alpha et l’émulation ne remplacent pas une nouvelle observation dans Roblox Studio.

### Fichiers du lot 2

| Ensemble | Fichiers |
| --- | --- |
| Cadrage et miniatures | `editor/emulator.js`, `tool/fx_render.cjs` |
| Avertissements et surcharges | `tool/fx_warnings.py`, nouveau `tool/fx_grid_overrides.py`, nouveau `tool/grid_overrides.json` ; cache dérivé séparé `tool/texture_frames.json` |
| CLI, Python, MCP | `tool/fx.py`, `tool/fx_tools.py`, `tool/fx_mcp.py` |
| Régressions | `tool/test_fx_warnings.py`, `tool/test_fx_tools.py`, `tool/test_fx_emulator.cjs`, `tool/test_fx_render.cjs`, nouveau `tool/test_fx_texture_bounds.cjs` |
| Documentation | `CLAUDE.md`, `DATAKY_FX_STUDIO.md`, `RAPPORT_DEMANDES_CLAUDE.md` |
| Preuves locales | `rendus/lot2-warnings.json`, `rendus/lot2-final-audit.*`, `rendus/lot2-framing-final*`, `rendus/lot2-tests-*.txt`, `rendus/lot2-validate-*.txt` |

Aucune modification du runtime Luau dans ce lot ; aucune régénération du plugin n’est nécessaire pour ces changements. Les API historiques restent disponibles.

### Tests et vérification manuelle

Interpréteur Python 3.13.9 de Blender et exécutable Luau identiques au lot 1. Aucun nouvel outil global n’a été installé. Commandes complètes :

```powershell
$env:PATH = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin;' + $env:PATH
$env:PYTHONUTF8 = '1'
$env:DATAKY_LUAU = 'C:\Users\esteb_9qwvhb8\.codex\tmp\gift-ledger-luau-0.741\luau.exe'
python -m unittest discover -s tool -p 'test_*.py'
node tool/test_fx_frontend.cjs
node --test tool/test_fx_emulator.cjs tool/test_fx_preview_ui.cjs tool/test_fx_curves.cjs tool/test_fx_render.cjs tool/test_fx_texture_bounds.cjs
python rendus/lot2-final-audit.py
```

Sortie réelle Python (`rendus/lot2-tests-python.txt`) :

```text
Ran 130 tests in 18.388s
OK
```

Sortie frontend (`rendus/lot2-tests-frontend.txt`) :

```text
PASS: five real editor templates, native schema defaults, references, motion, sequence codecs, frontend invalid-input checks.
```

Sortie réelle de toutes les suites JavaScript (`rendus/lot2-tests-javascript.txt`) :

```text
tests 93
suites 0
pass 93
fail 0
cancelled 0
skipped 0
todo 0
duration_ms 3613.5236
```

Les deux tests de rendu Chromium (`real Chromium CLI...` et `real Chromium pixel regression...`) ainsi que le test des pixels alpha des textures ont été exécutés et passent. **Aucun blocage Chromium ne reste à relancer par Claude.** Les réponses HTTP de refus affichées pendant les tests Python appartiennent aux scénarios de test attendus. L’audit final confirme : 21 projets valides, 20 fixtures vérifiées / 0 modifiée, 4 index catalogue vérifiés / 0 modifié, surcharges de grille vides.

Pour reproduire à la main depuis la racine :

```powershell
python tool/fx.py validate tool/fixtures/bulbito/A1_Muzzle.json
python tool/fx.py validate tool/fixtures/bulbito/A1_Muzzle.json --infos
python tool/fx.py validate tool/fixtures/bulbito/Pillar_InvisibleInPlay.json
python tool/fx.py render tool/fixtures/bulbito/A1_Muzzle.json --fit Muzzle --times 0.02,0.06 --size 480x270 --background noir --no-ground --no-dummy --out rendus/lot2-manuel-muzzle.png
python tool/fx.py render tool/fixtures/bulbito/A1_Muzzle.json --fit Flash --times 0.02,0.06 --size 480x270 --background noir --no-ground --no-dummy --out rendus/lot2-manuel-flash.png
python tool/fx.py render tool/fixtures/bulbito/A1_Muzzle.json --fit Muzzle --fit-all --times 0.02,0.06 --out rendus/lot2-manuel-ancien.png
python tool/fx.py render tool/fixtures/bulbito/A1_Muzzle.json --focus 0,0,-1.5 --radius 3 --times 0.02,0.06 --out rendus/lot2-manuel-focus.png
```

Les rendus ciblés retirent automatiquement le mannequin ; les mesures pixel ci-dessus utilisent aussi `ground: false` dans le manifeste. Après contrôle visuel d’une planche, `python tool/fx.py grid-confirm ID 4` (ou 2/8) confirme uniquement la grille choisie dans le fichier de surcharges.
