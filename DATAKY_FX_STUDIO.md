# Dataky FX Studio

Un atelier local pour composer des effets Roblox à la main ou depuis une recette JSON. Le rendu animé est calculé par Roblox Studio avec de vrais objets. Le navigateur fournit la bibliothèque, les réglages, la hiérarchie et la timeline.

## Ouvrir l’atelier

1. Double-cliquez sur **DATAKY_FX_STUDIO.bat**. Python 3 suffit ; aucun service d’IA ni clé API ne sont nécessaires.
2. L’application s’ouvre sur **http://127.0.0.1:48754/**. Gardez sa fenêtre de serveur ouverte pendant votre travail.
3. Ouvrez votre projet dans Roblox Studio, en mode édition.
4. Dans l’atelier, cliquez sur **Studio déconnecté**, copiez la commande proposée et exécutez-la dans la barre de commande Studio. La connexion est valable pour cette session.

Pour installer le pont comme plugin local et utiliser l’aperçu intégré, utilisez **INSTALLER_LE_PONT.bat**, puis redémarrez Studio. Dans l’onglet Plugins, la barre **Dataky FX** propose **Connexion** et **Aperçu**. Cliquez sur Connexion dans la fenêtre Studio voulue. Le plugin démarre déconnecté pour vous laisser choisir la bonne fenêtre. La connexion par barre de commande permet toujours d’éditer et de lire les effets ; la permission de capture du nouvel aperçu exige le plugin installé.

## Créer à la main

Commencez par un modèle **Impact**, **Fumée**, **Beam** ou **Trail**, ou par un projet vide.

- Ajoutez les objets depuis **Hiérarchie → Ajouter**. Un ParticleEmitter peut être placé directement dans un Part ou dans un Attachment. Roblox applique alors nativement sa logique de volume ou de point d’émission.
- Sélectionnez un objet pour modifier ses propriétés. Les valeurs et les noms suivent les classes Roblox ; les courbes permettent de modifier taille, couleur ou transparence au cours de la vie des particules.
- Cliquez sur une courbe pour ouvrir l’éditeur graphique : glissez ses points et ses poignées Bézier, ajoutez un point par double-clic et choisissez un profil linéaire, accéléré, ralenti, impact ou fondu. Les points de début et de fin gardent leur temps. Les dégradés de couleur ont des repères glissables et un sélecteur de couleur. Les animations numériques et XYZ proposent aussi **Éditeur graphique**.
- La ligne lisse sert à dessiner la courbe. La ligne en pointillés montre son approximation réellement exportée en points Roblox, avec une limite de 20 points. Les poignées sont enregistrées dans `editor.curves` pour retrouver la courbe à la réouverture ; le moteur utilise les valeurs échantillonnées. Modifier le JSON des valeurs invalide automatiquement les anciennes poignées.
- Choisissez une texture, un beam ou un mesh dans la bibliothèque pour appliquer son ID. Les miniatures servent à choisir ; Studio charge la ressource native par son ID et applique ses permissions habituelles.
- Pour un Beam ou un Trail, reliez **Attachment0** et **Attachment1** à deux points de votre effet. Une ressource de la collection Beams est une texture pour ce ruban ; elle ne définit pas à elle seule ses réglages.
- Réglez le début, la durée et le nombre de particules dans la timeline. Les animations de propriétés utilisent des points clés en secondes.
- **Appliquer à Studio** construit la composition. **Lire** déclenche la lecture native. **Arrêter** coupe l’émission et efface les particules en cours. **Fermer l’aperçu** retire le conteneur temporaire et rend la caméra à la scène initiale.

Les effets de prévisualisation sont placés dans `Workspace.__DatakyFXPreview`, sur une station à distance du contenu de votre place. Le pont travaille uniquement dans son conteneur. Ne publiez pas une place contenant un aperçu dont vous n’avez plus besoin ; fermez l’aperçu après utilisation.

## Voir le rendu dans l’application

Dans **Aperçu natif**, cliquez sur **Activer l’aperçu intégré**. Le pont construit l’effet et demande à Studio l’autorisation de capturer son viewport au premier usage. Acceptez cette demande vous-même dans Studio. Les images du rendu 3D arrivent ensuite directement dans l’atelier ; il n’est plus nécessaire d’observer une deuxième fenêtre pour juger l’effet. Studio doit rester ouvert et son document de prévisualisation actif. Une fenêtre minimisée ou un document non capturable peut suspendre le flux ; le pont réessaie sans redemander la permission.

Le pont de capture doit être chargé après un redémarrage de Studio lors de cette mise à jour. Les tests automatisés du transport, des courbes et de leur intégration passent ; le premier flux réel demande encore votre autorisation dans Studio.

Le flux natif utilise `StudioCaptureService`, avec environ **4 images par seconde**, une résolution maximale de 1280 × 720 et un débit adapté aux limites HTTP. Il convient au réglage visuel ; ce n’est pas une vidéo à 30 ou 60 images par seconde. **Utiliser le partage de fenêtre en secours** affiche une vidéo plus fluide dans le même panneau après avoir sélectionné la fenêtre Studio dans le navigateur.

**Rejouer les changements** relance automatiquement la composition après une modification. Décochez cette option pour ne rejouer qu’avec le bouton de lecture. **Capturer l’aperçu** archive une image PNG locale avec le véritable projet et l’instant rendu, pour comparer des variantes ou la fournir à une IA. Les images courantes du flux restent uniquement en mémoire ; les anciennes images sont écartées quand le projet change ou que l’aperçu s’arrête.

Le **plan de scène** est une aide de placement. La timeline sert à écrire les réglages et les animations ; déplacer sa tête de lecture ne recrée pas un historique de particules ou de trails à un instant arbitraire. Relancez la lecture native pour juger l’effet. La pause est prise en charge pour les particules et beams ; un effet contenant un Trail signale qu’une pause fidèle de son historique n’est pas disponible.

La caméra, l’éclairage, la qualité graphique, l’aléatoire et les permissions d’assets influencent l’apparence. L’éditeur utilise les comportements natifs ; il ne promet pas deux lectures identiques pixel par pixel.

## Sauvegarder et réutiliser

**Enregistrer** sauvegarde le projet dans `editor/projects/`. Le brouillon du navigateur et l’historique annuler/rétablir facilitent le travail manuel ; utilisez Enregistrer pour conserver un fichier de projet.

**Recette JSON** permet de lire, copier, importer et modifier toute la composition. **Exporter** fournit le projet JSON ou un ModuleScript Luau autonome. Le module exporté fonctionne sans l’atelier, sans connexion locale et sans IA :

```lua
local fx = require(game.ReplicatedStorage.MonEffet)
fx.build(workspace, Vector3.new(0, 4, 0))
fx.play()
-- fx.stop(), fx.clear(), fx.pause(), fx.resume(), fx.status()
```

Le déplacement d’origine est appliqué aux Parts du projet ; les Attachments gardent leurs positions locales. Pour un effet attaché à un personnage mobile, le code du jeu doit gérer le support ou la liaison au personnage. L’export ne crée pas automatiquement une logique de combat ou une réplication réseau.

## Pour une IA ou un autre outil

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
| `GET /api/snapshots` | Retrouver les captures enregistrées manuellement depuis la vue Studio. |

L’IA doit pouvoir appeler cette API ou lire les fichiers et voir les captures. Le site ne lui donne pas automatiquement accès à votre écran. Aucun texte de projet n’est exécuté comme code. Les propriétés inconnues, références invalides et cycles de parents sont signalés ; corrigez-les avant la sauvegarde ou la lecture.

## Bibliothèque et maintenance

La bibliothèque existante reste utilisable hors ligne dans **catalogue.html**. **METTRE_A_JOUR.bat** régénère les exports et miniatures depuis les captures enregistrées. **tool/macro.bat** relit les listes du plugin. Ces deux opérations sont indépendantes de la création d’un effet dans l’atelier.

Les projets, les aperçus et les scripts restent locaux. Aucun appel à ChatGPT n’est nécessaire pour utiliser l’éditeur à la main ou pour rejouer un effet exporté.
