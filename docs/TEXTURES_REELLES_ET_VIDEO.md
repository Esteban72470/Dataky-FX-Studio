# Textures et références vidéo locales

Le catalogue conserve des miniatures Roblox, principalement de 420 × 420 pixels, et les IDs natifs. Une miniature ne contient pas la géométrie d’un mesh et ne garantit pas les droits d’utilisation d’un asset. L’aperçu natif dans Roblox Studio reste la vérification finale.

Les textures originales de `source/vfx/<effet>/textures/` sont accessibles à l’émulation par des URI `rbxasset://textures/dataky-local/<effet>/<fichier>.png`. Le serveur n’expose que ces PNG, sans ouvrir arbitrairement les scripts ou les autres fichiers de `source/`. Une texture originale absente est signalée et reste transparente.

## Extraction vidéo

Le bouton **Références vidéo** ouvre l’import d’un fichier local, les fenêtres temporelles, les planches horodatées et les annotations humaines. Le module `tool/fx_video.py` demande OpenCV, NumPy et Pillow pour décoder et préparer les images :

```powershell
python -m pip install opencv-python numpy pillow
```

Les fenêtres proposées reposent sur les variations de mouvement, de luminosité et de couleur. Les niveaux A/B/C règlent le nombre d’images et la résolution. Les segments peuvent être corrigés manuellement puis réextraits ; les résultats sont mis en cache par empreinte du média et configuration.

Ces mesures ne constituent pas une interprétation artistique automatique. Aucun modèle local ni appel vision ne produit de critique. Les observations enregistrées via **Conserver les observations** portent une provenance humaine.

Les médias, images extraites et caches restent dans `editor/local_ai/video/`, un chemin historique de stockage local exclu de Git. L’import conserve une copie du fichier fourni ; aucun téléchargement de vidéo distante n’est effectué. Les routes d’images servent uniquement les JPEG déclarés dans le manifeste de l’analyse.

Les tests vidéo utilisent une vidéo synthétique pour vérifier l’extraction, les timestamps, les caches, la correction des segments, les annotations et le confinement des fichiers.
