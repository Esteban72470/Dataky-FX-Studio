# Dataky FX Studio

Pour créer et modifier des effets, double-cliquez sur **DATAKY_FX_STUDIO.bat**. L’atelier local s’ouvre dans le navigateur : bibliothèque, hiérarchie, propriétés, courbes, timeline et émulation 3D de l’effet, sans Roblox Studio. Studio reste disponible pour la vérification finale. Pour créer des effets avec Claude, double-cliquez sur **INSTALLER_CLAUDE_DESKTOP.bat** (Claude Desktop) ou ouvrez ce dossier dans Claude Code (**CLAUDE.md**) ; les outils et l’export **.rbxmx** sont décrits dans **DATAKY_FX_STUDIO.md**. Le guide de création et de connexion native est **DATAKY_FX_STUDIO.md**.

Le catalogue conserve la provenance des assets du plugin ZonitoVisuals. Son ancien nom de dossier reste utilisé pour garder les chemins et les scripts compatibles.

Double-cliquez sur **catalogue.html**, puis choisissez l’onglet **Textures**, **Beams** ou **Meshes**. La recherche accepte un nom, un tag ou un ID. Chaque onglet conserve ses propres filtres ; Textures permet aussi de choisir les images fixes ou flipbooks. **Copier l’ID** et **rbxassetid** donnent les références à utiliser dans Roblox Studio.

**Beams** répertorie les textures utilisées par les rubans et faisceaux Roblox. **Meshes** répertorie les formes 3D : leurs détails proposent le **MeshId** et, lorsqu’il existe, le **TextureId**, avec un bouton de copie pour chaque référence.

Le catalogue et ses miniatures sont consultables hors ligne. Les images enregistrées sont des **miniatures fournies par Roblox**, pas les fichiers originaux des textures ou des maillages. Les IDs restent dans la base même si leur aperçu est indisponible. Un asset peut rester soumis aux permissions Roblox dans votre jeu.

## Fichiers

| Chemin | Contenu |
| --- | --- |
| `catalogue.html` | Catalogue visuel avec recherche, filtres et copie des IDs. |
| `textures.json` | Base complète réutilisable par des scripts. |
| `textures.csv` | Tableau ouvrable dans Excel. |
| `textures.sqlite` | Base SQLite pour les requêtes et les outils. |
| `beams/` | Catalogue des beams : `assets.json`, `assets.csv`, `assets.sqlite`, `tags/`, `images/`, `source/`, `summary.json` et `failures.json`. |
| `meshes/` | Même organisation pour les meshes, avec les références MeshId et TextureId conservées dans les exports. |
| `tags/` | Index des textures classées par tag du plugin. Une texture peut avoir plusieurs tags. |
| `images/` | Miniatures Roblox enregistrées localement, nommées par ID. |
| `previews/` | Aperçus représentatifs de flipbooks quand une disposition a pu être déduite. |
| `source/` | Captures brutes des listes du plugin, conservées pour refaire le catalogue. |
| `summary.json` | Bilan de l’extraction et du téléchargement. |
| `failures.json` | Aperçus indisponibles et erreurs enregistrées. |
| `apercu_catalogue.jpg` | Planche de 24 miniatures réelles, avec leurs noms et IDs. |
| `tool/` | Scripts de capture, téléchargement et génération du catalogue. |

Le type image fixe ou flipbook utilise l’appartenance aux vues **Statics** et **Flipbooks** du plugin lorsque cette information est disponible. Les détails du catalogue indiquent la provenance du type ; les cas ambigus ou déduits sont signalés.

Une disposition de flipbook marquée **estimée** est une déduction, pas une propriété vérifiée. L’animation proposée dans le catalogue utilise cette estimation. Vérifiez la grille dans le plugin avant de l’utiliser dans un effet.

## Actualiser

Double-cliquez sur **METTRE_A_JOUR.bat** pour régénérer le catalogue des trois collections et télécharger les miniatures manquantes à partir des captures déjà présentes dans `source/`, `beams/source/` et `meshes/source/`. Le téléchargement se fait en parallèle. Les images valides sont conservées en cache : après une interruption, relancez la mise à jour pour reprendre les aperçus manquants sans télécharger à nouveau ceux déjà enregistrés. Une connexion Internet est nécessaire pour les nouveaux aperçus.

Pour régénérer les exports et retenter les aperçus **Beams** et **Meshes** depuis leurs captures existantes, lancez à la racine du catalogue :

```powershell
python tool/asset_catalog.py --collections beams meshes --workers 12
```

Cette actualisation ne relit pas automatiquement les nouveautés du plugin. Pour une nouvelle capture, double-cliquez sur **`tool/macro.bat`** (ou lancez `python tool/macro.py`), ouvrez le plugin avec les tags et la recherche effacés, puis suivez les indications affichées. La macro fournit une ligne à coller dans la barre de commande Studio. Placez ensuite la souris au centre de l’en-tête **Tags** et appuyez sur **F8** pour calibrer. **Échap** interrompt la macro. Gardez la fenêtre `vfx.rbxl` visible et ne déplacez pas ses panneaux pendant les clics. Par défaut, la macro parcourt **Textures, Beams et Meshes**, leurs tags et leurs listes complètes ; elle capture aussi **Statics** et **Flipbooks** pour Textures, puis reconstruit les catalogues. Les instructions détaillées sont dans **`tool/MACRO_LIRE_MOI.md`**.

**La macro a été vérifiée hors interface ; nous n’avons pas exécuté son parcours par clics natifs Windows.** Son premier lancement interactif doit être surveillé par l’utilisateur, notamment le premier changement de tag. Les captures déjà terminées sont conservées si la macro s’arrête. Les tags sont découverts automatiquement ; les vues personnelles et récentes sont exclues par défaut (`--include-personal` les inclut).

Gardez le catalogue et ses dossiers d’images ensemble lorsque vous les déplacez.

Pour contrôler les exports sans ouvrir le navigateur : `python tool/verify_outputs.py`. Ce contrôle compare les captures aux bases JSON, CSV et SQLite, aux index par tag et aux données du catalogue HTML. L’option `--verify-png` vérifie aussi les fichiers PNG avec Pillow.

Le contrôle supplémentaire **`python tool/verify_extra_outputs.py --verify-png`** vérifie les captures et les exports **Beams/Meshes**, leurs références, leurs images et leur intégration dans le catalogue principal.
