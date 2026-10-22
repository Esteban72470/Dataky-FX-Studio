# Dataky FX Studio

Un atelier local pour composer des effets Roblox à la main ou depuis une recette JSON. Le navigateur émule lui-même les ParticleEmitter, Beam, Trail, lumières et Parts : l’effet se lit, se met en pause et se rembobine à n’importe quel instant sans ouvrir Roblox Studio. Studio reste disponible pour la vérification finale avec les vrais objets, puis l’export Luau met l’effet dans votre jeu.

## Ouvrir l’atelier

1. Double-cliquez sur **DATAKY_FX_STUDIO.bat**. Python 3 suffit ; aucun service d’IA ni clé API ne sont nécessaires.
2. L’application s’ouvre sur **http://127.0.0.1:48754/**. Gardez sa fenêtre de serveur ouverte pendant votre travail.
3. Créez votre effet : la vue **✦ Émulation** le joue directement dans l’atelier. Roblox Studio n’est pas nécessaire à cette étape.
4. Facultatif, pour la vérification finale : ouvrez votre projet dans Roblox Studio en mode édition, cliquez sur **Studio déconnecté** dans l’atelier, copiez la commande proposée et exécutez-la dans la barre de commande Studio. La connexion est valable pour cette session.

Pour installer le pont comme plugin local et utiliser l’aperçu intégré, utilisez **INSTALLER_LE_PONT.bat**, puis redémarrez Studio. Dans l’onglet Plugins, la barre **Dataky FX** propose **Connexion** et **Aperçu**. Cliquez sur Connexion dans la fenêtre Studio voulue. Le plugin démarre déconnecté pour vous laisser choisir la bonne fenêtre. La connexion par barre de commande permet toujours d’éditer et de lire les effets ; la permission de capture du nouvel aperçu exige le plugin installé.

## Créer à la main

Commencez par un modèle **Impact**, **Fumée**, **Beam** ou **Trail**, ou par un projet vide.

- **Hiérarchie → Ajouter → Briques** ajoute un bloc prêt à l’emploi à l’instant de la tête de lecture : Flash, Étincelles, Onde de choc, Fumée, Slash, Arc, Traînée, Feu, Concentration ou Orbe. Ses objets sont ordinaires et restent modifiables comme les autres.
- Ajoutez les objets depuis **Hiérarchie → Ajouter**. Un ParticleEmitter peut être placé directement dans un Part ou dans un Attachment. Roblox applique alors nativement sa logique de volume ou de point d’émission.
- Sélectionnez un objet pour modifier ses propriétés. Les valeurs et les noms suivent les classes Roblox ; les courbes permettent de modifier taille, couleur ou transparence au cours de la vie des particules.
- Cliquez sur une courbe pour ouvrir l’éditeur graphique : glissez ses points et ses poignées Bézier, ajoutez un point par double-clic et choisissez un profil linéaire, accéléré, ralenti, impact ou fondu. Les points de début et de fin gardent leur temps. Les dégradés de couleur ont des repères glissables et un sélecteur de couleur. Les animations numériques et XYZ proposent aussi **Éditeur graphique**.
- La ligne lisse sert à dessiner la courbe. La ligne en pointillés montre son approximation réellement exportée en points Roblox, avec une limite de 20 points. Les poignées sont enregistrées dans `editor.curves` pour retrouver la courbe à la réouverture ; le moteur utilise les valeurs échantillonnées. Modifier le JSON des valeurs invalide automatiquement les anciennes poignées.
- Choisissez une texture, un beam ou un mesh dans la bibliothèque pour appliquer son ID. Les miniatures servent à choisir ; Studio charge la ressource native par son ID et applique ses permissions habituelles.
- Pour un Beam ou un Trail, reliez **Attachment0** et **Attachment1** à deux points de votre effet. Une ressource de la collection Beams est une texture pour ce ruban ; elle ne définit pas à elle seule ses réglages.
- Réglez le début, la durée et le nombre de particules dans la timeline. Les animations de propriétés utilisent des points clés en secondes.
- **Appliquer à Studio** construit la composition. **Lire** déclenche la lecture native. **Arrêter** coupe l’émission et efface les particules en cours. **Fermer l’aperçu** retire le conteneur temporaire et rend la caméra à la scène initiale.

Les effets de prévisualisation sont placés dans `Workspace.__DatakyFXPreview`, sur une station à distance du contenu de votre place. Le pont travaille uniquement dans son conteneur. Ne publiez pas une place contenant un aperçu dont vous n’avez plus besoin ; fermez l’aperçu après utilisation.

## Émulation dans le navigateur

La vue **✦ Émulation** est la vue par défaut. Elle rejoue la recette avec les mêmes règles que le pont Studio : timing des pistes, bursts (`Emit`), émission continue au `Rate`, animations par points clés, boucle qui efface les particules, fin d’effet qui laisse les particules existantes s’éteindre.

Le sélecteur **Timeline / Libre** (Tab) ouvre un bac à sable. En Libre, l’horloge tourne sans limite ; les continus émettent au Rate et les bursts attendent Emit. Le ParticleEmitter sélectionné possède un champ quantité et un bouton Emit. **Emit sélection** inclut ses descendants, **Emit tout** joue les bursts, **Vider** efface les particules sans changer les interrupteurs. Les Enabled de l’arbre et des propriétés sont temporaires en Libre ; en Timeline ils sont enregistrés dans la recette et grisent les barres désactivées. Modifier les propriétés en Libre met à jour l’aperçu directement. Ce mode fonctionne aussi dans l’aperçu natif après réinstallation du pont généré.

Le bouton **?** affiche tous les raccourcis : Espace/Maj+Espace lecture-pause/stop, E/Maj+E Emit sélection/tout, T Enabled, Tab mode, C vider, flèches et Début/Fin pour la tête, [/ ] pour les débuts de timing, L boucle, F/Maj+F cadrage, G sol, M mannequin, 1–5 fonds, ↑/↓ arbre, Alt+↑ parent, Ctrl+C/V copie JSON avec descendants entre projets, Ctrl+E/Ctrl+Maj+E exports. Ils restent inactifs dans un champ ou un dialogue. Les raccourcis de sauvegarde, historique, duplication, suppression, recherche et Échap restent disponibles. La tête arbitraire s’applique à l’émulateur ; l’aperçu natif doit être relancé depuis 0.

Les recettes comportant `params` affichent un curseur par paramètre. Par exemple, `params.radius.default=16` et `scaleWith: {"Size":"radius"}` sur un anneau font varier son rayon sans grossir les autres émetteurs. Ces curseurs changent l’aperçu seulement.

Emit conserve une pause explicite ; après Stop, Emit remet le bac à sable en marche. Changer de projet remet à zéro les particules, l’horloge et les Enabled d’aperçu. Les modifications simples de propriétés conservent l’historique en Libre. Une modification de structure ou suppression de propriété peut reconstruire l’aperçu natif.

- **Lire**, **Pause**, **Arrêter** et la timeline pilotent l’émulation. Cliquer dans la timeline affiche l’effet **exactement** à cet instant : la simulation est déterministe (pas de 1/60 s et graine fixe), elle rejoue l’historique des particules et des trails jusqu’au temps demandé.
- **Rejouer les changements** relance l’effet après chaque modification.
- Glissez dans la vue pour tourner autour de l’effet, **Maj + glisser** (ou clic droit) pour déplacer, molette pour zoomer. **Caméra du projet** revient au cadrage enregistré ; **Garder ce cadrage** l’enregistre dans le projet, pour les rendus et pour Studio.
- **Fond** utilise la couleur `environment.background` de la recette tant qu’aucun preset n’est forcé. Les presets sombre, gris, ciel clair, noir et **roblox** (ciel bleu clair, sol gris clair) et **Sol** aident à juger un effet sur différents décors. Le sol reçoit la lumière des PointLight, SpotLight et SurfaceLight. Testez aussi sur fond clair : les couleurs additives peuvent saturer en blanc.
- **Mannequin** place un personnage Roblox de 5 studs à côté de l’effet pour juger son échelle. **Cadrer** recule la caméra jusqu’à voir toute l’étendue de l’effet, depuis l’angle actuel.
- **Capturer** enregistre l’image affichée avec son instant (`capture_source: browser-emulator`).

Ce qui est émulé : formes d’émission Box, Sphere, Cylinder et Disc avec ShapeStyle, ShapeInOut et ShapePartial ; EmissionDirection, SpreadAngle, Speed, Lifetime, Acceleration, Drag, Rotation, RotSpeed, TimeScale, LockedToPart ; Size, Transparency, Squash et Color au cours de la vie, enveloppes comprises ; orientations FacingCamera, FacingCameraWorldUp, VelocityParallel et VelocityPerpendicular ; flipbooks Grid2x2 à 8x8 et Custom en Loop, OneShot, PingPong et Random avec fondu ; LightEmission, LightInfluence, Brightness et ZOffset ; Beams (courbe de Bézier, CurveSize, largeurs, Segments, FaceCamera, TextureMode, TextureLength, TextureSpeed) ; Trails (Lifetime, MinLength, MaxLength, WidthScale, FaceCamera, TextureMode) ; Parts Block, Ball et Cylinder, SpecialMesh Sphere, Cylinder et Brick, matériau Neon ; lumières.

Limites à connaître :

- En `VelocityParallel` avec `Rotation: 0`, un Squash négatif étire le long de la vitesse et un Squash positif en travers (mesuré en Play). Pour une texture de trait vertical, utilisez `Rotation: 90` et un Squash positif. FacingCamera reste une approximation non mesurée.
- Le message de connexion du plugin apparaît une seule fois en édition, sans polluer les sorties client et serveur de Play.

- Les textures affichées sont les **miniatures 420 × 420** de la bibliothèque locale. Une texture absente de la bibliothèque est remplacée par un halo doux et signalée dans la barre d’état. Les textures intégrées `rbxasset://` sont approchées par des formes générées.
- La géométrie des **MeshPart** et des SpecialMesh FileMesh n’est disponible que dans Roblox : l’émulation les montre comme des boîtes filaires.
- Sur un Beam ou un Trail, l’émulation fait courir l’**axe vertical de l’image le long du ruban**. La documentation ne le précise pas ; c’est l’orientation de la grande majorité des 447 textures de la collection Beams.
- Le moteur Roblox n’est pas public. La forme exacte de Squash, la répartition de SpreadAngle, l’éclairage, le bloom, la qualité graphique et le tri fin des particules sont des approximations fondées sur la documentation officielle. VelocityInheritance n’a pas d’effet, comme dans le pont Studio où les Parts sont ancrées et déplacées par propriété.
- L’émulation sert à créer et itérer vite. Avant de publier, vérifiez une fois l’effet dans **◉ Roblox Studio**.

## Vérifier dans Roblox Studio

Dans **◉ Roblox Studio**, cliquez sur **Activer l’aperçu intégré**. Le pont construit l’effet et demande à Studio l’autorisation de capturer son viewport au premier usage. Acceptez cette demande vous-même dans Studio. Les images du rendu 3D arrivent ensuite directement dans l’atelier ; il n’est plus nécessaire d’observer une deuxième fenêtre pour juger l’effet. Studio doit rester ouvert et son document de prévisualisation actif. Une fenêtre minimisée ou un document non capturable peut suspendre le flux ; le pont réessaie sans redemander la permission.

Le pont de capture doit être chargé après un redémarrage de Studio lors de cette mise à jour. Les tests automatisés du transport, des courbes et de leur intégration passent ; le premier flux réel demande encore votre autorisation dans Studio.

Le flux natif utilise `StudioCaptureService`, avec environ **4 images par seconde**, une résolution maximale de 1280 × 720 et un débit adapté aux limites HTTP. Il convient au réglage visuel ; ce n’est pas une vidéo à 30 ou 60 images par seconde. **Utiliser le partage de fenêtre en secours** affiche une vidéo plus fluide dans le même panneau après avoir sélectionné la fenêtre Studio dans le navigateur.

**Rejouer les changements** relance automatiquement la composition après une modification. Décochez cette option pour ne rejouer qu’avec le bouton de lecture. **Capturer l’aperçu** archive une image PNG locale avec le véritable projet et l’instant rendu, pour comparer des variantes ou la fournir à une IA. Les images courantes du flux restent uniquement en mémoire ; les anciennes images sont écartées quand le projet change ou que l’aperçu s’arrête.

Le **plan de scène** est une aide de placement. La timeline sert à écrire les réglages et les animations ; déplacer sa tête de lecture ne recrée pas un historique de particules ou de trails à un instant arbitraire. Relancez la lecture native pour juger l’effet. La pause est prise en charge pour les particules et beams ; un effet contenant un Trail signale qu’une pause fidèle de son historique n’est pas disponible.

Studio en arrière-plan peut ralentir la simulation des particules (mesuré en Play). Le pont relaie conditionnellement les événements de focus du viewport principal et l’atelier affiche un avertissement lorsqu’il reçoit explicitement une perte de focus pendant la lecture. Un état inconnu ne déclenche rien. La livraison de ces signaux dans ce plugin Edit reste à vérifier dans Studio ; ce n’est pas une détection garantie du focus de toute l’application ([API documentée](https://create.roblox.com/docs/reference/engine/classes/UserInputService#WindowFocusReleased)). Un Trail natif continue de perdre son historique dans une capture figée.

La caméra, l’éclairage, la qualité graphique, l’aléatoire et les permissions d’assets influencent l’apparence. L’éditeur utilise les comportements natifs ; il ne promet pas deux lectures identiques pixel par pixel.

## Sauvegarder et réutiliser

**Enregistrer** sauvegarde le projet dans `editor/projects/`. Le brouillon du navigateur et l’historique annuler/rétablir facilitent le travail manuel ; utilisez Enregistrer pour conserver un fichier de projet.

**Recette JSON** permet de lire, copier, importer et modifier toute la composition.

**Exporter → Modèle Roblox .rbxmx** est le chemin le plus simple vers Roblox : glissez le fichier dans Studio. Le modèle contient les vrais objets de l’effet (Parts, Attachments, émetteurs, beams, lumières), visibles et modifiables à la main, et un ModuleScript `DatakyFX` qui joue la timeline sur ces objets :

```lua
local fx = require(workspace.MonEffet.DatakyFX)
fx.play()
-- fx.stop(), fx.pause(), fx.resume(), fx.status()
```

Chaque objet porte un attribut `DatakyFXNodeId` : vous pouvez le renommer ou retoucher ses propriétés, la timeline le retrouve. Déplacez le modèle par son pivot : les animations de position suivent ce déplacement (pas la rotation). Les émetteurs qui ont un timing sont éteints dans le fichier ; le lecteur les allume au bon instant. Une MeshPart importée ainsi garde son MeshId ; vérifiez sa taille dans Studio.

**Exporter** fournit aussi le projet JSON et un ModuleScript Luau autonome, qui construit lui-même l’effet. Le module exporté fonctionne sans l’atelier, sans connexion locale et sans IA :

```lua
local fx = require(game.ReplicatedStorage.MonEffet)
fx.build(workspace, Vector3.new(0, 4, 0))
fx.play()
-- fx.stop(), fx.clear(), fx.pause(), fx.resume(), fx.status()
```

Le déplacement d’origine est appliqué aux Parts du projet ; les Attachments gardent leurs positions locales. Pour un effet attaché à un personnage mobile, le code du jeu doit gérer le support ou la liaison au personnage. L’export ne crée pas automatiquement une logique de combat ou une réplication réseau.

L’export `.lua` historique joue **un seul effet à la fois, aligné sur le monde**. Pour un vrai jeu avec plusieurs unités, exportez une bibliothèque :

```powershell
python tool/fx.py export A1_Muzzle.json A2_Impact.json --format library --out exports/MesEffets.lua
```

La commande produit `MesEffets.lua` (recettes indexées par nom de fichier) et `DatakyFXKit.lua`. Placez les deux dans des ModuleScripts voisins :

```lua
local FX = require(script.Parent.DatakyFXKit)
local Recipes = require(script.Parent.MesEffets)
local h = FX.play(Recipes.A1_Muzzle, muzzle.WorldCFrame, {
    follow=muzzle, scale=1, speed=1, hold=false, quality="Auto",
})
-- h:Release(), h:Stop(), h:Move(cframe), h:Part("id")
-- FX.freeze(), FX.unfreeze()
```

Le kit respecte la rotation, suit Attachment/Bone/BasePart ou une fonction renvoyant une CFrame et nettoie chaque instance indépendamment. Release coupe les continus et attend leur durée de vie ; Stop détruit tout de suite. `params={radius=24}` règle les propriétés marquées par scaleWith. Les animations de propriétés sont jouées, sauf Position et Transparency des Parts qui servent à la prévisualisation. `Low` réduit les bursts à 60 % ; Auto lit la qualité disponible. Pour des MeshParts, appelez `FX.preload(recipe)` avant `play` ; ce préchargement peut attendre, mais `play` ne yield jamais. L’historique natif des Trails ne peut pas être figé.

Le kit mémorise validation et décodage par table de recette (clés faibles) et clone un gabarit d’instances. `FX.prepare(recipe)` construit ce gabarit à l’avance sans attendre ; pour les MeshParts, `FX.preload(recipe)` doit le précéder. Dès le premier accès par le kit, gardez la recette immuable : créez une copie profonde pour modifier une variante. Une copie superficielle `table.clone` ne suffit pas.

`h:Release({hideParts=true})` masque immédiatement toutes les Parts/MeshParts et laisse les particules finir. Release arrête définitivement le suivi. `h:SetFollow(fnOrInstance)` change la cible ; `nil` arrête le suivi ; après Release/Stop cette méthode ne fait rien. L’option `onFinished=function(h) ... end` est appelée une seule fois après le nettoyage, y compris après Stop. Elle est différée avec `task.defer` et protégée : une erreur ou une attente du callback ne bloque pas `play`.

Au démarrage, `FX.preloadTextures(Recipes)` ou `FX.preloadTextures(Recipes.A1_Muzzle)` peut attendre `ContentProvider:PreloadAsync`. `FX.listTextures(Recipes)` liste les URI uniques sans précharger. Une nouvelle bibliothèque exportée permet aussi `Recipes:listTextures()` ; ses recettes restent les seules clés parcourues par `pairs`. Si une recette porte ce nom, utilisez `FX.listTextures`. Les anciens modules de bibliothèque fonctionnent avec le nouveau kit.

Dans le plugin connecté en Edit, **Dataky FX → Exporter les textures utilisées** scanne les ParticleEmitter, Beam et Trail de la place ainsi que les champs de textures littéraux des ModuleScripts de recettes. Le résultat est `tool/used_textures/<nom de la place>.txt`, directement utilisable avec `--exclude-file`. Les modules ne sont pas exécutés ; les sources inaccessibles et les expressions de textures calculées sont signalées comme scan partiel.

## Écrire, chercher et vérifier depuis Python

Le module `tool/fx_builder.py` fournit `Recipe`, `NS`, `CS`, `NR` et les méthodes part/att/em/trail/light/anim/flip/merge/save. Exemple complet et signatures dans le module et dans `CLAUDE.md`.

Dans un plan compose, `{"include":"A1_Muzzle.json","at":0.44,"position":[0,1,-4],"orientation":[0,90,0],"scale":1}` inclut une recette tournée et décalée. Les chemins se résolvent depuis le plan. `positionKeys` ajoute une translation animée locale ; les références, animations et paramètres sont remappés. Les orientations sont exactes aux points clés, avec une limite d’interpolation Euler entre les clés après composition.

- `python tool/fx.py textures --query star --compact --no-sheet --exclude-file used.txt` affiche un tableau court et ignore les textures déjà utilisées. `--exclude-ids 123 456` est une alternative.
- `python tool/fx.py sheet 123 456 --exclude-file used.txt --out rendus/choix.png` affiche les IDs choisis, leur grille et le badge USED.
- `python tool/fx.py validate recette.json` affiche un résumé par code, puis les avertissements détaillés. Les infos de grille estimated sont séparées et masquées par défaut : utiliser `--infos` ou `--verbose`. Une même texture n’apparaît qu’une fois dans les infos d’une recette. La recette reste valide et les avertissements ne changent pas le code de sortie.
- `python tool/fx.py grid-confirm 11844402871 4` confirme une grille contrôlée visuellement. La confirmation est stockée dans `tool/grid_overrides.json` et retire l’info correspondante ; le catalogue reste intact. Le fichier accepte les grilles carrées 2, 4 ou 8 et la recherche utilise aussi ces surcharges.
- Une fin Size proche de zéro ou une Transparency finale ≥ **0,95** ne déclenche pas `abrupt_transparency`. Ce diagnostic exige les deux résidus : Transparency < 0,95 et Size > `max(0,05 stud, 5 % du pic de Size)`.
- `flat_layer_negative_zoffset` avertit sur les couches plates `VelocityPerpendicular` + `Top` avec `ZOffset < 0`, qui peuvent passer sous le sol. `dark_ground_contrast` avertit sur les couches presque noires (luminance maximale < 0,15, LightEmission < 0,2) sans couche claire couvrant leur présence. Le soutien clair exige luminance ≥ 0,45, LightEmission ≥ 0,2 et une taille/opacité visibles. Les fenêtres incluent timing, Enabled, Count/Rate, Lifetime et TimeScale ; tous les seuils sont dans `THRESHOLDS`. Ce sont des heuristiques : positions, textures, éclairage natif et propriétés animées autres qu’Enabled ne sont pas simulés par cet avertissement.
- Les diagnostics de visibilité mesurent une **surface opaque équivalente en studs²**, au lieu du seul pourcentage d’alpha : moyenne sur la vie de `alpha × Size² × (1 - Transparency)`. Le seuil est **0,01 stud²** ; les pixels durs opaques contribuent pleinement. La règle garde ainsi les poussières et étoiles pixel observées visibles en Play. Les seuils sont centralisés dans `tool/fx_warnings.py::THRESHOLDS` ; couleur, fond, enveloppes et cumul d’émetteurs restent des limites de cette estimation.
- Les flipbooks OneShot dont les premières cases sont presque vides peuvent être invisibles avec une Lifetime courte : c’est le cas mesuré de `70418763522849` à 0,2–0,45 s. Le cache alpha séparé `tool/texture_frames.json` est calculé au besoin ; `python tool/fx_texture_cache.py` le préremplit. Ses diagnostics utilisent les miniatures et des seuils heuristiques, à confirmer en Play.
- `python tool/fx.py render recette.json --fit NODE_ID --times 0.02,0.06` cadre seulement les particules vivantes aux instants choisis, demi-taille incluse. Un émetteur cadre ses propres particules ; une Part inclut celles de tous ses émetteurs descendants. Le 90e centile des distances au centroïde écarte les particules isolées : réglable avec `--fit-percentile` (> 0 à 100). Sans particules, repli annoncé sur la Part et ses Attachments. `--fit-all` conserve l’ancien cadrage de toute l’étendue simulée sur toute la durée.
- Le contour des cases de texture affichées est transformé avec la taille, la rotation et le Squash des particules. Le cadrage conserve 90 % de l’énergie alpha² par case ; cette mesure relative préserve les textures pâles et écarte les halos isolés. `--fit-percentile 100` conserve tout l’alpha et toutes les particules. Sans miniature accessible, le quad entier contribue. La caméra cadre ces points directement ; aucun cube artificiel n’ajoute de profondeur aux billboards. Le rendu et les diagnostics de visibilité ne sont pas modifiés par ce choix de caméra.
- `--focus 0,1,-4 --radius 3` cadre une **sphère** de rayon 3, visant 87,5 % de la plus petite dimension de l’image. La direction de la caméra est conservée.
- `python tool/fx.py render-batch jobs.json` traite plusieurs recettes/instants/caméras avec un seul Chromium. Le manifeste `{"jobs":[{"projects":["recette.json"],"out":"rendus/vue.png","times":[0,0.1],"camera":[10,6,12,0,1,0]}]}` peut contenir plusieurs vues. Options de jobs en camelCase, dont `fitPercentile` et `fitAll` ; chemins de recettes depuis le manifeste, sorties depuis le dépôt. Playwright est requis. Si le bac à sable interdit l’accès au Playwright installé, le diagnostic l’indique et les captures réelles doivent être relancées hors du bac à sable.

Les outils MCP proposent les mêmes filtres/exclusions, `texture_sheet`, le cadrage `fit`/`fit_percentile`/`fit_all` ou `focus/radius`, `render_batch`, les avertissements et résumés de `validate_effect` (`include_infos` pour les infos), `grid_confirm` et l’export library.

## Pour une IA ou un autre outil

Claude (ou une autre IA) dispose de trois portes d’entrée vers les mêmes outils : choisir des textures en les voyant, assembler des briques, rendre l’effet en images, comparer des variantes, valider, enregistrer et exporter.

- **Claude Desktop** : double-cliquez sur **INSTALLER_CLAUDE_DESKTOP.bat**, puis relancez Claude Desktop. Le serveur MCP `tool/fx_mcp.py` ajoute les outils Dataky FX à la conversation ; il suffit de demander « fais-moi une explosion de glace ». Une sauvegarde `.bak` de la configuration est faite avant modification.
- **Claude Code** dans ce dossier : `CLAUDE.md` décrit la méthode et les pièges Roblox, et `.mcp.json` déclare le même serveur MCP (commande `python` ; remplacez-la par `py` si nécessaire). La ligne de commande suffit aussi :

```powershell
python tool/fx.py textures --tag Slash --kind flipbook   # planche des textures avec leurs IDs
python tool/fx.py blocks                                 # briques disponibles
python tool/fx.py compose plan.json --out recette.json   # briques → recette
python tool/fx.py render recette.json variante.json      # planche ; une ligne par variante
python tool/fx.py export recette.json --format rbxmx     # modèle à glisser dans Studio
```

Les rendus se font avec cadrage automatique et mannequin d’échelle (`--no-auto-camera`, `--no-dummy` pour les retirer). Les planches vont dans `rendus/` et les exports dans `exports/`. Ces outils n’ajoutent pas de savoir-faire artistique : votre skill VFX garde ce rôle, et ces outils lui donnent des yeux et des mains.

Les rendus utilisent Node.js et Playwright. La commande de bas niveau produit une planche PNG de l’effet à des instants précis :

```powershell
node tool/fx_render.cjs editor/projects/dataky-impact.json --out rendu.png --times 0,0.1,0.25,0.5
node tool/fx_render.cjs dataky-impact --frames 8 --size 640x360 --camera 8,4,10,0,1,0
node tool/fx_render.cjs variante-a.json variante-b.json --times 0.1,0.3 --auto-camera --dummy
```

Elle utilise Chromium par Playwright (`npm install -g playwright` puis `npx playwright install chromium`) et n’a besoin ni du serveur, ni de Studio. La même recette, la même graine (`--seed`) et le même instant donnent toujours la même image : l’IA peut modifier un réglage, refaire la planche et comparer. `--frames-dir` enregistre aussi chaque image séparément ; `--background`, `--no-ground` et `--fov` reprennent les options de la vue. Le résultat JSON liste les fichiers, les instants réellement rendus (arrondis au pas de 1/60 s) et les avertissements (textures absentes, maillages non émulés).

Rendu unique, `render-batch` et MCP partagent les priorités de caméra : `--camera px,py,pz,tx,ty,tz` est exact ; `--fit` ou `--focus` demandent un cadrage ; sinon la caméra de la recette est conservée. `--auto-camera` / `autoCamera: true` demande le cadrage global, avec priorité conservée à une caméra explicite. L’ancien `--no-auto-camera` reste disponible.

`--background dark` force un ciel de nuit et un sol gris sombre ; ce décor est une approximation de vfx.rbxl, pas une capture de son éclairage. `--backgrounds roblox,dark` génère une ligne par recette et par fond pour comparer le contraste avec les mêmes caméra, instants et graine. Python/MCP et les jobs batch acceptent `background="dark"` ou `backgrounds=["roblox","dark"]` (chaîne à virgules également acceptée). Les deux options sont exclusives. Le rapport JSON liste les lignes et la taille de la planche ; les images individuelles ont un nom distinct par ligne.

Sans Node, la page **http://127.0.0.1:48754/render.html?project=ID&frames=8** affiche la même planche pour un projet enregistré (paramètres `times`, `size`, `columns`, `background`, `ground=0`, `seed`). Dans l’atelier ouvert, `window.DatakyFX.emulator` propose `play()`, `stop()`, `seek(t)`, `frame(t)` (image PNG en data URL) et `sheet(options)`.

Boucle conseillée pour une IA : choisir les textures sur leurs planches, composer ou écrire la recette, la valider, rendre la planche, regarder les images, corriger, recommencer ; puis enregistrer et exporter le modèle `.rbxmx`.

L’API locale sert la même recette que l’interface :

| Route | Usage |
| --- | --- |
| `GET /api/schema` | Classes, propriétés, types, valeurs et limites acceptées. |
| `GET /api/catalog` | Assets et tags des trois collections. |
| `GET /api/projects` | Projets sauvegardés. |
| `GET /api/project/ID` | Lire une recette. |
| `POST /api/project` | Valider et sauvegarder une recette JSON. |
| `POST /api/preview` | `{ "action": "play", "project": { ... } }` ; actions apply, play, stop, clear, pause, resume. |
| `GET /api/status` | Connexion Studio, erreurs et résultats natifs. |
| `GET /api/preview/frame` | État du flux intégré et métadonnées de la dernière image récente. |
| `GET /api/preview/frame.png` | Dernière image native, sans cache ; erreur si aucune image récente. |
| `POST /api/snapshot` | `{ "native": true }` archive l’image native récente avec son véritable instant et projet. |
| `GET /api/export/ID.json` | Télécharger le projet. |
| `GET /api/export/ID.lua` | Télécharger le ModuleScript autonome. |
| `GET /api/export/ID.rbxmx` | Télécharger le modèle Roblox à glisser dans Studio, lecteur inclus. |
| `GET /api/blocks` | Briques disponibles et leurs réglages. |
| `POST /api/compose` | `{ "project": {…}, "blocks": [{ "block": "flash", "at": 0 }] }` ajoute des briques et renvoie la recette, sans l’enregistrer. |
| `GET /api/snapshots` | Retrouver les captures enregistrées manuellement depuis la vue Studio. |

L’IA doit pouvoir appeler cette API ou lire les fichiers et les planches de rendu. Le site ne lui donne pas automatiquement accès à votre écran. Aucun texte de projet n’est exécuté comme code. Les propriétés inconnues, références invalides et cycles de parents sont signalés ; corrigez-les avant la sauvegarde ou la lecture.

## Bibliothèque et maintenance

La bibliothèque existante reste utilisable hors ligne dans **catalogue.html**. **METTRE_A_JOUR.bat** régénère les exports et miniatures depuis les captures enregistrées. **tool/macro.bat** relit les listes du plugin. Ces deux opérations sont indépendantes de la création d’un effet dans l’atelier.

Les projets, les aperçus et les scripts restent locaux. Aucun appel à ChatGPT n’est nécessaire pour utiliser l’éditeur à la main ou pour rejouer un effet exporté.
