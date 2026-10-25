# MeshPart : aperçu OBJ local

L'import OBJ local ajoute un vrai maillage à l'éditeur existant via
`tool.fx_mesh.import_obj` ou la route locale `/api/mesh/import`. Les positions, normales et UV sont rendues en WebGL avec
profondeur, couleur, transparence, TextureID, orientation, Size et DoubleSided.
Les pistes et mouvements déjà présents animent ce MeshPart sur la même timeline
que les particules, Beams, Trails et lumières. Les attaches du MeshPart suivent
sa position et sa rotation. Comme dans Roblox, les Parts utilisent des
transformations monde ; leur parentage seul ne constitue pas une transformation
locale de groupe.

## Fichiers et format

Le fichier est un OBJ texte UTF-8 contenant des surfaces : `v`, `vt`, `vn`, `f`.
Les indices positifs et négatifs sont acceptés. Les triangles et polygones
convexes plans sont triangulés ; trianguler les faces concaves ou non planes dans
le logiciel source avant import. Les groupes OBJ sont réunis en un MeshPart.
Les normales explicites sont conservées ; sinon des normales par face sont
calculées. Les groupes de lissage ne remplacent pas des normales explicites.

Les fichiers MTL et autres ressources externes ne sont jamais ouverts. Leurs
références produisent un avertissement. Pour les textures, renseigner un
TextureID Roblox dont la miniature existe dans le catalogue local. Ces
miniatures ont une résolution inférieure aux assets originaux.

L'import est borné : 4 Mio de texte, 100 000 lignes, 16 384 caractères par ligne,
64 sommets par face, 60 000 sommets par canal et 20 000 triangles par mesh.
Un projet accepte 32 meshes, 100 000 triangles et 16 Mio de géométrie JSON au
total. Les dimensions source doivent rester dans 2 048 unités ; réduire
l'échelle dans le logiciel source pour des géométries plus grandes.

La géométrie est centrée sur sa boîte et normalisée par axe à `[-0.5, 0.5]`.
La dimension originale devient `MeshPart.Size` ; un axe plat utilise la taille
minimale 0,001. Les coordonnées OBJ sont interprétées comme des studs, Y vers
le haut. L'axe V des UV est inversé pour les images du navigateur.

```python
from tool.fx_mesh import import_obj
result = import_obj(obj_text, "slash", name="slash.obj", mesh_id="")
project["nodes"].append(result["node"])
editor = project.setdefault("editor", {"version": 1, "curves": {}})
editor.setdefault("meshes", {})["slash"] = result["mesh"]
```

`result` contient `node`, `mesh` et `warnings`. Le schéma valide la géométrie
avant sauvegarde. `editor.meshes[node_id]` contient exactement :

```text
version: 1
positions: [x, y, z, ...]       # tableau plat normalisé
normals: [nx, ny, nz, ...]      # normales unitaires, une par sommet
uvs: [u, v, ...]               # une paire par sommet
indices: [i0, i1, i2, ...]     # triangles, indices entiers commençant à zéro
source: {name, format: "obj", sha256, dimensions: [x, y, z]}
```

Ces données sont des métadonnées d'édition, distinctes de `properties.MeshId`.
Dupliquer et copier/coller remappent leurs IDs. Supprimer retire les données
associées ; Annuler les restaure. L'import/export JSON et la sauvegarde
conservent les meshes. Conserver aussi le fichier OBJ source pour son import
manuel dans Studio.

## Export vers Roblox

Un aperçu OBJ local ne crée pas un asset Roblox. Sans `MeshId` Roblox explicite,
les exports `.rbxmx`, Luau et bibliothèque, ainsi que l'aperçu Studio natif,
sont refusés. L'export JSON reste disponible. **Exporter → Manifeste des
assets Roblox** indique les références manquantes.

Importer le fichier source dans Roblox Studio avec le workflow officiel,
vérifier la géométrie, l'échelle et les permissions, puis renseigner le MeshId
obtenu sur le même nœud dans l'éditeur. Aucune publication n'est automatique.
La présence d'un ID ne prouve ni les permissions ni l'identité géométrique :
la comparaison finale doit être faite dans Studio.

## Vérification et limites

`test_fx_mesh.py` vérifie l'import et les données invalides ; `test_fx_mesh.cjs`
rend réellement sous Chromium et contrôle les pixels de silhouette, profondeur,
transparence, culling et texture UV. `test_fx_preview_ui.cjs` couvre le cycle de
vie des métadonnées. `test_fx_mesh_export.py` vérifie les refus d'export
sans MeshId et `test_fx_mesh_merge.py` couvre la fusion des meshes locaux.

Cette étape n'ajoute pas d'import FBX/glTF/GLB, de skinning, Bones,
AnimationController, EditableMesh, SurfaceAppearance/PBR ni de générateurs
procéduraux de meshes métier. Les matériaux restent une approximation
SmoothPlastic/Neon et éclairage simplifié ; aucun bloom/ombre natif n'est
reproduit. Les surfaces translucides sont triées par objet et les particules
par lot : les intersections complexes ne garantissent pas la parité Roblox.
Les parties opaques des textures écrivent la profondeur, les pixels alpha sont
dessinés dans une seconde passe. Les vérifications décrites sont celles du
simulateur ; elles ne constituent pas une comparaison native Studio.
