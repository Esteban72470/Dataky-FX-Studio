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

- **Lire**, **Pause**, **Arrêter** et la timeline pilotent l’émulation. Cliquer dans la timeline affiche l’effet **exactement** à cet instant : la simulation est déterministe (pas de 1/60 s et graine fixe), elle rejoue l’historique des particules et des trails jusqu’au temps demandé.
- **Rejouer les changements** relance l’effet après chaque modification.
- Glissez dans la vue pour tourner autour de l’effet, **Maj + glisser** (ou clic droit) pour déplacer, molette pour zoomer. **Caméra du projet** revient au cadrage enregistré ; **Garder ce cadrage** l’enregistre dans le projet, pour les rendus et pour Studio.
- **Fond** (sombre, gris, ciel clair, noir) et **Sol** aident à juger un effet sur différents décors. Le sol reçoit la lumière des PointLight, SpotLight et SurfaceLight.
- **Mannequin** place un personnage Roblox de 5 studs à côté de l’effet pour juger son échelle. **Cadrer** recule la caméra jusqu’à voir toute l’étendue de l’effet, depuis l’angle actuel.
- **Capturer** enregistre l’image affichée avec son instant (`capture_source: browser-emulator`).

Ce qui est émulé : formes d’émission Box, Sphere, Cylinder et Disc avec ShapeStyle, ShapeInOut et ShapePartial ; EmissionDirection, SpreadAngle, Speed, Lifetime, Acceleration, Drag, Rotation, RotSpeed, TimeScale, LockedToPart ; Size, Transparency, Squash et Color au cours de la vie, enveloppes comprises ; orientations FacingCamera, FacingCameraWorldUp, VelocityParallel et VelocityPerpendicular ; flipbooks Grid2x2 à 8x8 et Custom en Loop, OneShot, PingPong et Random avec fondu ; LightEmission, LightInfluence, Brightness et ZOffset ; Beams (courbe de Bézier, CurveSize, largeurs, Segments, FaceCamera, TextureMode, TextureLength, TextureSpeed) ; Trails (Lifetime, MinLength, MaxLength, WidthScale, FaceCamera, TextureMode) ; Parts Block, Ball et Cylinder, SpecialMesh Sphere, Cylinder et Brick, matériau Neon ; lumières.

Limites à connaître :

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
