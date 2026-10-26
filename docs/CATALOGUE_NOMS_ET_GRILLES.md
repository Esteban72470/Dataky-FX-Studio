# Noms et grilles du catalogue

La revue visuelle ajoute 1 447 noms descriptifs français aux entrées vides ou génériques. Les noms précédents restent dans les alias et les IDs Roblox sont conservés. 1 428 noms proviennent de l’examen des images ; les 19 images indisponibles reçoivent un nom explicite fondé sur leurs catégories.

Les 98 flipbooks sans grille ont été examinés : 74 grilles 4×4, 13 grilles 8×8, 6 grilles 2×2 et une grille 6×4 (`79593708822934`) ont été confirmées. La grille rectangulaire est affichée et animée dans le catalogue ; l’atelier l’applique avec `FlipbookLayout=Custom`, `FlipbookSizeX=6`, `FlipbookSizeY=4`.

Les aperçus de `17387207972`, `110361796788602` et `77966646561127` sont indisponibles. L’image `15054104862` (Bats), classée de façon ambiguë dans les sources, ne montre aucune grille régulière. Ces quatre cas restent signalés sans grille inventée.

Les corrections sont conservées dans `tool/catalog_annotations_data.py`, un fichier de données lu sans exécution par `tool/catalog_annotations.py`. Il contient la provenance des noms, les dimensions vérifiées et les empreintes des images examinées. Les captures source restent intactes. Les corrections sont réappliquées lors de la reconstruction du catalogue et dans les API de consultation, afin de survivre aux prochaines mises à jour.
