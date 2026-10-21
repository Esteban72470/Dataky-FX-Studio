# Refaire les catalogues Textures, Beams et Meshes

Double-cliquer **`tool/macro.bat`** pour relancer la capture sous Windows. Le parcours par défaut couvre les trois collections **Textures, Beams et Meshes**, avec les tags propres à chaque onglet et la vue **All**. Pour Textures, il capture aussi les vues **Statics** et **Flipbooks**.

La macro conserve les noms et les IDs Roblox ; pour les meshes, le helper lit les références MeshId et TextureId du panneau. Les captures brutes vont dans `source/`, `beams/source/` et `meshes/source/`. Elle lance ensuite `catalog.py` pour les textures et `asset_catalog.py` pour les autres collections afin de reconstruire les catalogues.

Le téléchargement des aperçus se fait en parallèle et réutilise les images valides du cache local. Relancer une génération après une interruption reprend les aperçus manquants. Une nouvelle exécution de la macro recommence le parcours des listes et réutilise le même cache d’images.

1. Ouvrir `vfx.rbxl` dans Roblox Studio, en mode édition, et afficher ZonitoVisuals sur Textures, Beams ou Meshes. Effacer la recherche et désélectionner les tags : l’en-tête doit afficher **Tags**.
2. Double-cliquer **`tool/macro.bat`**. Copier la ligne `loadstring(...)` imprimée dans sa fenêtre, puis la coller dans la barre de commande de Studio et l’exécuter. Autoriser l’accès HTTP local si Studio le demande.
3. Placer le pointeur exactement au centre de l’en-tête **Tags**, puis appuyer sur **F8** pour calibrer les coordonnées du panneau.
4. Garder cette fenêtre Studio au premier plan, sans déplacer ni redimensionner ses panneaux. Laisser la macro parcourir les listes. **Échap** ou Ctrl+C arrête la capture.

La sélection des tags est vérifiée avant chaque capture. Les types Statics/Flipbooks exigent une sélection exclusive et aucun tag. Beams et Meshes n’utilisent pas ces types. Une capture d’assets ou de type incomplète est rejetée avant de remplacer un fichier complet. Après un parcours réussi, la macro revient à l’onglet initial.

Pour sélectionner les collections à refaire, ouvrir un terminal dans `tool/` et utiliser, par exemple :

```powershell
py -3 macro.py --collections beams meshes
py -3 macro.py --collections textures
```

Les vues **Personal** et **Recently Used** sont exclues par défaut ; `--include-personal` les inclut pour chaque collection choisie. Pour un fichier Studio portant un autre nom, ajouter `--window-title "MonJeu.rbxl"`.

Pour régénérer seulement les aperçus et les exports à partir des captures présentes, sans refaire les clics :

```powershell
py -3 catalog.py --workers 12
py -3 asset_catalog.py --collections beams meshes --workers 12
```

Le serveur est limité à `127.0.0.1:48754` et protégé par un jeton aléatoire à chaque lancement. La macro s’arrête si la fenêtre Studio attendue perd le premier plan, si le panneau bouge ou change de taille, ou si la collection, le tag ou le type actif ne correspond plus à la capture attendue. Elle ne crée aucun objet dans le jeu.

En cas d’arrêt, les captures complètes restent sur disque. Les fragments incomplets restent dans le dossier `.capture_parts/` de leur collection et ne remplacent jamais une capture complète. Effacer les tags actifs avant de recommencer. Les noms de tags incompatibles avec un nom de fichier Windows sont enregistrés sous un nom sécurisé ; leur nom exact reste dans le JSON. Le défilement et la visibilité du menu sont restaurés tant que la connexion locale est encore disponible.

**Limite de validation : nous n’avons pas exécuté le parcours par clics natifs Windows de cette macro.** Son premier lancement interactif doit être surveillé, notamment le premier changement d’onglet et de tag. Les tests hors interface couvrent les coordonnées, la file de commandes, les captures découpées, les trois collections et leurs tags, les types de textures, la sélection d’une seule collection et les contrôles contre les captures contaminées.
