# Catalogue dynamique de l’atelier

`tool/fx_ai_catalog.py` lit les collections existantes **Textures, Beams et
Meshes**, ainsi que les meshes OBJ réutilisables importés localement.
Chaque nouvelle recherche relit les sources actuelles. Une
modification de nom, tags, ID, grille ou observation, un ajout et une suppression
sont donc visibles sans redémarrer le serveur. Le nom historique du module
`fx_ai_catalog.py` ne signifie pas qu’un modèle est installé ou utilisé.

## Accès complet et recherche paginée

Tous les IDs valides sont recherchables, avec pagination. L'index parcourt noms,
tags, alias, IDs et observations explicitement fournies. Des synonymes français
et anglais couvrent les formes VFX courantes ; un ID explicitement demandé passe
en priorité. Le classement est textuel : il ne prétend pas analyser les images
ou attribuer une forme observée à partir d'un nom.

Les outils de recherche renvoient une sélection paginée du catalogue complet.
Un candidat conserve sa collection, son ID permanent et sa provenance ; les
buffers d’une géométrie locale ne sont chargés qu’après sa sélection.

Les doublons d'un même ID dans une même collection sont regroupés ; leurs noms
alternatifs et tags restent recherchables. Pour les meshes, le couple MeshId et
TextureId définit une variante distincte : un mesh non texturé n'est jamais
fusionné avec sa version texturée. La clé `meshes:ID` désigne la version sans
texture lorsqu'elle existe, sinon la variante au TextureId numériquement le plus
petit. Les autres variantes utilisent `meshes:ID@TEXTUREID`. Ce choix est calculé
avant la lecture des lignes pour rester indépendant de leur ordre. Un ID seul
devenu ambigu exige sa clé complète. Par exemple, le catalogue conserve séparément
`meshes:1051557` (Simple Thick Spring sans texture) et
`meshes:1051557@98468789881853` (Spiral texturé).
Les références MeshId et TextureId explicites sont conservées. Les entrées avec un ID invalide sont
exclues et comptées. Une miniature manquante ne supprime jamais un asset de la
recherche. Auteur, licence et droits inconnus restent inconnus.

## Sources relues

* `textures.json` ;
* `beams/assets.json` ;
* `meshes/assets.json` ;
* `tool/grid_overrides.json` pour les grilles confirmées ;
* `editor/artistry/assets.json` pour les observations humaines/vision ;
* `editor/local_ai/catalog.json` pour les meshes locaux réutilisables.

La révision SHA-256 porte sur le contenu des sources, même si leur taille et leur
date de modification sont inchangées. Une modification pendant la lecture
provoque une nouvelle lecture ; un fichier JSON invalide donne une erreur
visible. Aucune ancienne version en cache ne remplace silencieusement les données
actuelles. Les trois catalogues de départ ne sont jamais écrits par ce module.

Un ajout doit figurer dans le catalogue ou passer par un import pris en charge.
Déposer un fichier quelconque dans un dossier d'images ne crée pas à lui seul
une entrée d'asset avec ID, nom et provenance.

## Meshes OBJ importés

`register_mesh(imported, root=...)` enregistre le résultat validé de `import_obj`.
L'identité locale `local-<hash du fichier source>` reste stable quand le même OBJ
est importé à nouveau. La géométrie est enregistrée dans un fichier adressé par
son contenu sous `editor/local_ai/meshes/`. Un verrou entre processus protège
l'index, puis une écriture atomique le remplace ; les imports simultanés ne
perdent pas d'entrées.

Sauvegarder un effet contenant un mesh connu conserve son nom de bibliothèque,
sa licence, son créateur et sa provenance d'enregistrement. Un nom différent
de couche devient un alias recherchable. Une sauvegarde inchangée ne réécrit pas
l'index et ne change pas sa révision. Les tags explicitement fournis et les
associations MeshId/TextureID non vides sont mis à jour quand ils changent.
Les associations sont partagées par toutes les générations utilisant cet OBJ :
un ID renseigné doit bien représenter la même géométrie dans Studio. Une ancienne
recette non mappée n'efface pas une association explicite déjà enregistrée.
Vider le MeshId d'une instance de projet ne retire donc pas l'association
globale connue ; une correction ou suppression globale concerne l'entrée
correspondante dans `editor/local_ai/catalog.json`.
Cette association ne prouve pas les droits d'accès et ne publie aucun asset.

Un mesh local peut être recherché et réutilisé sans MeshId pour l'aperçu. Il doit
recevoir un MeshId Roblox explicite après import autorisé dans Studio avant
export natif. Le catalogue ne publie jamais un asset et ne télécharge ni n'exécute
de scripts tiers. Une miniature d'un mesh Roblox n'est pas sa géométrie 3D :
sans géométrie locale, seul Studio peut rendre sa forme native exacte.

Le registre accepte jusqu'à 256 meshes locaux. Les limites de géométrie et de
composition de l'éditeur s'appliquent toujours aux effets générés.

## API Python

```python
from tool import fx_ai_catalog as catalog

snapshot = catalog.snapshot(root=application_folder)
found = catalog.search("anneau magique", collection="meshes", snapshot=snapshot)
asset = catalog.get_asset(found["items"][0]["key"], snapshot=snapshot)
geometry = catalog.load_geometry(asset, root=application_folder)  # None pour un ID distant
```

`snapshot` fournit `revision`, `counts`, `raw_counts`, `assets` et `warnings`.
`search` fournit les résultats paginés, leur total et la même révision. Une
génération peut réutiliser un snapshot unique pour lier ses candidats et son
export à une source cohérente. La demande suivante crée un nouveau snapshot.

Tests : `python -m unittest discover -s tool -p test_fx_ai_catalog.py`. Ils
vérifient fraîcheur, lecture concurrente, JSON invalide, pagination, synonymes,
provenance, grilles, références de meshes, absence de miniature, sécurité des
chemins, empreintes et enregistrements atomiques entre processus indépendants.
