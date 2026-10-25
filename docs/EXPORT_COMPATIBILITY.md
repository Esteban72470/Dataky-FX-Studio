# Export Roblox et géométrie locale — 25 octobre 2026

La géométrie importée dans l'aperçu local ne constitue pas un asset Roblox.
Un fichier OBJ visible dans l'éditeur nécessite un import autorisé dans Studio
et un **MeshId permanent** avant tout export natif. Aucun fichier ni asset n'est
publié ou envoyé automatiquement.

## Contrat des nouveaux meshes

`editor.meshes[nodeId]` conserve les triangles, normales, UV, indices et une
provenance locale : nom du fichier, format OBJ, SHA-256 et dimensions. Les
positions sont centrées et normalisées ; `MeshPart.Size` conserve les dimensions
de l'objet. L'export JSON préserve ces données pour reprendre l'édition.

Les exports `.lua`, `.rbxmx` et bibliothèque + kit vérifient chaque entrée :

* Sans `MeshPart.properties.MeshId` positif, l'export est bloqué avec un message
  explicite et un manifeste structuré des assets manquants.
* Un ID décimal positif, `rbxassetid://ID` ou URL officielle Roblox est accepté
  comme association explicite. Un chemin local `rbxasset://...` et l'ID 0 ne
  constituent pas un asset permanent pour un mesh importé.
* Avec une association, les exports conservent les propriétés natives et les
  pistes d'animation, puis retirent `editor.meshes` du payload Luau. Les buffers
  de preview ne sont ni une géométrie Roblox embarquée ni un upload implicite.
* L'existence d'un ID ne prouve pas les permissions, l'identité de la géométrie,
  les normales ou les UV. Leur comparaison dans l'expérience cible reste requise.

La composition par `merge_recipes` ou inclusion conserve ces métadonnées avec
les nouveaux IDs de nœuds. La copie est indépendante de sa source ; une inclusion
ne peut pas supprimer le besoin d'importer son mesh dans Roblox.

Pour consulter le manifeste en Python :

```python
from tool.fx_tools import export_manifest, export
manifest = export_manifest(recipe)
export(recipe, "manifest", "exports/MonEffet.assets.json")
```

`MeshExportError.manifest` fournit les mêmes données aux clients HTTP/MCP.
`missing_assets` et `mapped_assets` contiennent les IDs des nœuds et la provenance
sans recopier leurs buffers. Aucune écriture d'export natif n'a lieu si la
validation échoue ; les projets existants restent inchangés.

## Conversion manuelle vérifiable

1. Conserver le fichier OBJ original ; le JSON sauvegarde les données de preview.
2. Importer ce fichier avec l'importeur 3D de Studio dans votre compte autorisé.
3. Vérifier axes, unité en studs, pivot, taille, normales, double face et UV.
4. Vérifier les droits du mesh et de toute texture dans l'expérience cible.
5. Renseigner le MeshId obtenu dans le MeshPart de l'éditeur, puis exporter.
6. Comparer la scène native et l'aperçu aux mêmes instants et sous plusieurs vues.

OBJ est le premier format de ce jalon. FBX, glTF/GLB, matériaux PBR,
SurfaceAppearance, rigs, Bones, skinning et AnimationController nécessitent un
pipeline distinct. Le support d'un format générique ne garantit jamais la
compatibilité du pipeline d'importation Roblox.

## Runtime et limites conservées

Le runtime Roblox charge les meshes par
`AssetService:CreateMeshPartAsync(Content.fromUri(...))`. Le kit multi-instance
précharge explicitement avec `FX.preload(recipe)` ; `FX.play` clone ensuite le
gabarit et reste sans yield. Les propriétés `MeshId` ne sont pas réassignées à
un MeshPart construit vide.

Les pistes `Position` et `Transparency` de Part/MeshPart exigent `runtime:true`
dans le kit. Les mouvements compilés ajoutent déjà ce marqueur. `Orientation`,
`Size` et autres pistes numériques restent conservées. Les anciens projets
gardent leur comportement. Les Attachments restent locaux à leur parent ; les
Parts utilisent les positions du repère de la recette. Folder/Model n'ajoutent
pas un nouveau repère hiérarchique animé.

Le module historique et le lecteur `.rbxmx` suivent la translation du pivot,
sans composition complète de sa rotation pendant les pistes de position. Le kit
`FX.play(recipe, CFrame, ...)`, `Move` et `follow` compose la rotation et l'échelle.
Une courbe d'easing est compilée en clés linéaires : l'échantillonnage introduit
une approximation temporelle. Un Trail natif ne conserve pas son historique
pendant une pause complète du moteur.

## Vérifications et référence Studio

Avant les modifications : 50 tests d'export/kit/motion exécutés avec succès,
dont le véritable CLI Luau et un mock de l'API Roblox. Ils couvrent MeshPart,
préchargement, clés runtime, rotation, échelle, suivi, références Beam/Trail,
multi-instances et nettoyage. Les nouveaux tests `test_fx_mesh_export.py`
couvrent le blocage des meshes non associés, l'absence de fichiers partiels,
le manifeste, le JSON éditable et la conservation des pistes. Une bibliothèque
issue d'un mesh local associé est réellement jouée sous Luau/mock : position
interpolée, rotation d'origine, échelle, transparence et destruction sont
contrôlées. Résultat après modifications : **85 tests réussis**, dont 7 nouveaux,
avec `test_fx_mesh_export`, `test_fx_rbxmx`, `test_fx_kit`, `test_fx_motion` et
`test_fx_tools` (commande lancée depuis `tool`, aucun test ignoré).

Les contrôles d'intégration supplémentaires vérifient qu'un OBJ de 17 000
triangles (~1,8 Mo de texte, ~7 Mo de JSON après calcul) peut être importé,
sauvegardé, rechargé, inspecté par manifeste et recevoir un second import.
Une tentative d'aperçu natif avec mesh non associé est refusée avant de mettre
une commande Studio en attente. La suite ciblée composition, export et workflow
HTTP/Chromium contient 27 tests réussis, sans test ignoré.

La commande Studio MCP `list_roblox_studios` a retourné `{"studios":[]}`
pendant cette session. Aucun jeu n'a été modifié, aucun asset téléversé, aucune
capture Studio réalisée. Ces tests ne prouvent donc pas la parité graphique
native. Restent à capturer : Part/MeshPart, UV et transparence/occlusion,
ParticleEmitter/flipbooks, courbure Beam, historique Trail, lumières, projection
caméra et timing aux mêmes paramètres.

## Acquisition d'assets : APIs officielles inspectées

La référence actuelle recommande `POST /toolbox-service/v2/assets:search` ;
l'ancien GET de même chemin figure dans « Not Recommended ». Les détails d'un
asset utilisent `GET /toolbox-service/v2/assets/{id}`. Ces opérations Beta
doivent être relues au moment d'intégrer leurs contrats et scopes ; l'ancienne
spec GitHub du GET ne doit pas devenir un scraper figé.
[Référence Creator Store](https://create.roblox.com/docs/cloud/reference/features/creator-store).

Pour les actifs accessibles, les métadonnées passent par
`GET /assets/v1/assets/{assetId}` avec `readMask` ; Asset Delivery expose
`GET /asset-delivery-api/v1/assetId/{assetId}` avec autorisation Open Cloud.
Les aperçus sont séparés du contenu : `/v1/assets` pour les miniatures et
`/v1/assets-thumbnail-3d` pour les aperçus 3D. L'authentification nécessaire
dépend de l'opération et des permissions de l'asset.
[Référence Assets](https://create.roblox.com/docs/cloud/reference/features/assets),
[guide Assets](https://create.roblox.com/docs/cloud/guides/usage-assets).

L'acquisition prévue commence par candidats et métadonnées, puis revue des
permissions avant inspection de contenu. Stocker auteur, URL, dates, licence et
autorisations distinctes pour usage Roblox, inspection, redistribution et
entraînement ; garder « inconnu / à vérifier » quand la preuve manque. Une
ressource utilisable dans Roblox ne devient pas automatiquement redistribuable
ou admissible à un jeu d'entraînement. Aucun script tiers ne doit être exécuté
pour indexer un modèle. Utiliser pagination, cache et traitement des réponses
429, et respecter les règles et quotas des opérations utilisées.
[Creator Store et restrictions](https://create.roblox.com/docs/production/creator-store),
[assets et permissions](https://create.roblox.com/docs/projects/assets).
