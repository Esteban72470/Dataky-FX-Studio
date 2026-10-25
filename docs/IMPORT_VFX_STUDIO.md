# Fusion des catalogues ZonitoVisuals et VFX Studio

La fusion conserve une ligne par ID Roblox valide dans chaque collection. Les noms alternatifs, tags, observations et anciennes clés restent enregistrés. Les placeholders aux IDs invalides sont conservés séparément. Un nom plus descriptif remplace un nom générique seulement lorsqu’il est effectivement présent dans les métadonnées ; l’ancien nom reste recherchable.

Pour les meshes, un même MeshId peut avoir plusieurs TextureId. La bibliothèque garde une ligne par MeshId, avec ses variantes dans `variants` et `references`. Les outils de catalogue exposent aussi chaque variante et continuent de résoudre les anciennes clés vers leur texture d’origine.

## Captures et résultats

Les fichiers `source/vfx-studio/textures/textures-metadata.json` et `source/vfx-studio/meshes/meshes-metadata.json` contiennent les métadonnées et la provenance du plugin, sans son code. La capture des textures correspond aux 9 178 IDs uniques vérifiés dans son interface ; les 571 observations de géométries correspondent à 476 MeshIds uniques. Les entrées d’interface sans MeshId exploitable ne sont pas présentées comme de nouvelles géométries natives. Les 18 catégories de textures ainsi que les filtres Static et Flipbook ont été parcourus entièrement dans l’interface. Les catégories incluent aussi les correspondances de noms appliquées par le plugin ; elles ne se réduisent pas aux seuls mots-clés du JSON.

Le parcours UI des meshes reste partiel : 289 entrées sur les 547 du navigateur, interrompu par une demande de permission de gestion des scripts du plugin. Cette permission n’a pas été accordée. La liste complète des références vient des métadonnées du package installé, lues séparément ; elle ne dépend pas de ce parcours partiel. `ui-section-verification.json` et `verified/Meshes_All_PARTIAL.json` conservent cette limite explicitement.

La comparaison conserve séparément la version installée et les métadonnées publiques effectivement utilisées par l’interface : deux IDs de textures sont ajoutés et deux retirés dans la version publique, sans autre changement de métadonnées constaté. Les fichiers de provenance décrivent cette différence au lieu de présenter les deux versions comme identiques.

Les exports JSON et les index par tag conservent les alias et la provenance. Les CSV ajoutent ces champs en JSON ; les bases SQLite comportent une table `plugin_provenance` pour les sources, noms, anciennes clés et variantes. Les aperçus restent des miniatures Roblox, distinctes des textures originales et des géométries de meshes.

## Refaire la fusion

Depuis la racine du dépôt, inspecter d’abord le rapport sans modifier les exports :

```powershell
python tool/import_vfx_studio.py --root . --captures source/vfx-studio --report rendus/fusion-vfx-studio.json
```

Appliquer avec une sauvegarde ZIP nouvelle :

```powershell
python tool/import_vfx_studio.py --root . --captures source/vfx-studio --report rendus/fusion-vfx-studio.json --apply --backup backups/avant-fusion-vfx-studio.zip
```

L’option `--download` télécharge les miniatures manquantes ; les images valides en cache sont réutilisées. Les captures actives avec recherche, les captures incomplètes et les totaux incohérents sont refusés. Réimporter les mêmes métadonnées conserve les mêmes assets et alias.

Les reconstructions par `METTRE_A_JOUR.bat`, `tool/catalog.py` et `tool/asset_catalog.py` réappliquent les captures VFX Studio enregistrées. Elles conservent ainsi la fusion lors d’une actualisation du catalogue original. L’outil ne télécharge pas automatiquement de nouvelles métadonnées de plugin.

Les sauvegardes, vidéos privées et fichiers binaires du plugin ne font pas partie du dépôt public.
