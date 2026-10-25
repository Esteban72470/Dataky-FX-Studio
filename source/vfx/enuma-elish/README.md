# Enuma Elish — exemple original

Effet de 29,4 secondes composé manuellement : 291 objets, 242 pistes et huit textures PNG originales. Aucun modèle local ne génère cet exemple. La recette est aussi proposée dans `editor/projects/enuma-elish-rupture.json`.

Depuis la racine du dépôt :

```powershell
python source/vfx/enuma-elish/build_effect.py
python source/vfx/enuma-elish/package_scene.py
```

Les exports JSON, Luau et `.rbxmx` sont fournis dans `exports/`. Le second script crée `exports/package/Scene-Enuma-Elish.rbxlx` et un script `Installer-textures-Studio.ps1`. Exécutez ce dernier avant l'aperçu natif pour copier les PNG dans les dossiers de contenu de vos installations locales de Roblox Studio. Le package peut aussi être écrit ailleurs avec `--output CHEMIN`.

Les URI `rbxasset://textures/dataky-local/enuma-elish/` fonctionnent dans cet aperçu local. Pour distribuer l'effet dans un jeu, importez les PNG comme assets Roblox et remplacez ces URI par les IDs obtenus. Un dossier Studio mis à jour peut nécessiter de relancer l'installation locale des textures.

Les PNG sont fournis ; leur régénération facultative demande NumPy et Pillow :

```powershell
python -m pip install numpy pillow
python source/vfx/enuma-elish/draw_textures.py
```

Le générateur produit aussi `exports/textures-originales.jpg`. Le package n'inclut aucune vidéo ni frame de la référence externe.
