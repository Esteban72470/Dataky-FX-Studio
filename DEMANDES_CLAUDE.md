# Dataky FX Studio · demandes de Claude (2026-10-22)

Fiche pour Codex. Elle vient de l'usage réel de Dataky FX par Claude sur quatre unités Roblox du jeu Brainrot TD (Pop Pop Sahur, Corn Corn Corn Sahur, Tractoro Dinosauro2, Bulbito Bandito Traktorito). Chaque fois, la méthode était la même :

1. un script Python génère les recettes Dataky ;
2. la CLI `fx.py` les valide et les rend dans l'émulateur ;
3. un exporteur maison produit un module de données Luau ;
4. un kit Luau écrit à la main joue les recettes sur les os animés de l'unité ;
5. tout est vérifié en Play dans Roblox Studio.

Les faits marqués **mesuré** ont été mesurés dans Roblox Studio, en Play. Prends-les comme la vérité.

Les fichiers de référence cités sont dans `C:\Users\esteb_9qwvhb8\Documents\brainrot td\`. Tu peux les lire, mais ne les modifie pas.

## Règles de travail

- Ce dossier **n'est pas un dépôt git**. Une copie du code (tool/, editor/, *.md, *.bat, .mcp.json) se trouve dans `C:\Users\esteb_9qwvhb8\Downloads\Dataky-FX-Studio-main_sauvegarde_2026-10-22\`.
- Ne touche pas au catalogue : `images/`, `previews/`, `source/`, `beams/`, `meshes/`, `tags/`, `textures.*`, `catalogue.html`. Si une donnée dérivée des images est nécessaire, écris-la dans un nouveau fichier de cache généré par un script, par exemple `tool/texture_frames.json`.
- Garde la compatibilité :
  - les recettes `version: 1` existantes et les projets de `editor/projects/` doivent toujours se charger ;
  - l'API actuelle de `tool/fx_runtime.lua` (`apply`, `play`, `pause`, `resume`, `stop`, `clear`, `status`, `adopt`) ne doit pas changer de comportement.
- Après chaque lot, lance les tests décrits dans `CLAUDE.md` (section Développement) et ajoute des tests pour ce que tu changes. Après une modification de `tool/fx_runtime.lua`, régénère le plugin avec `python tool/fx_package.py`.
- Tu n'as pas accès à Roblox Studio. N'invente aucun comportement Roblox non mesuré. Quand une hypothèse n'est pas sûre, écris-la dans le rapport final.
- Mets à jour `CLAUDE.md` et `DATAKY_FX_STUDIO.md` pour tout ce qui change.
- Ordre de livraison : P0, puis P1, puis P2. Si tu manques de temps, livre des lots complets et testés plutôt que tout à moitié.

## P0 · Résultats faux

### 1. Squash inversé par rapport à Roblox

**Mesuré** (Play, 2026-10-21) : un ParticleEmitter avec `Orientation = VelocityParallel` et `Rotation = 0` donne ceci dans Roblox :
- un **Squash positif** étire le quad **en travers** de la vitesse ;
- un **Squash négatif** l'étire **le long** de la vitesse.

Il faut donc un Squash **négatif** pour des étincelles en traînée. Une texture de trait vertical a besoin de `Rotation 90` et d'un Squash positif. Les textures non carrées sont écrasées dans le quad carré.

Ce qui est faux aujourd'hui :
- `editor/emulator.js` (vers la ligne 465, calcul de `width`/`height`) fait l'inverse en VelocityParallel ;
- `CLAUDE.md`, section « Étincelles étirées », dit « Squash positif » ;
- la brique `sparks` de `tool/fx_modules.py` (ligne 125, `Squash=seq((0, 2.6), (1, 1.2))`) s'étire donc de travers dans Roblox. Vérifie aussi la ligne 241 et toute autre brique en VelocityParallel.

À faire :
- inverser l'axe d'étirement de l'émulateur **pour VelocityParallel seulement**. FacingCamera n'a pas été mesuré : n'y touche pas et signale-le dans le rapport ;
- corriger la doc et passer les briques concernées en Squash négatif ;
- ajouter un test d'émulateur qui vérifie qu'avec VelocityParallel et Squash -2, le quad est plus long le long de la vitesse.

### 2. `environment.background` ignoré

Le schéma accepte `environment.background` en `#RRGGBB` et l'atelier crée les projets avec `#191522`. Pourtant :
- l'émulateur de l'atelier prend le fond dans le menu `#emu-background` (presets `sombre`, `gris`, `ciel`, `noir`) ;
- `fx_render.cjs` prend `--background`, et `sombre` par défaut.

La valeur de la recette ne sert donc à rien. Il faut :
- utiliser la couleur de la recette quand aucun preset n'est forcé ;
- ajouter un preset **`roblox`** proche d'une baseplate Roblox de jour (ciel bleu clair, sol gris clair).

Pourquoi c'est important : un effet réglé sur fond sombre trompe. Par exemple, `LightEmission 1` sur du jaune ou du rose sature en **blanc** sur un ciel clair (**mesuré**, et l'émulateur le montre aussi).

### 3. Message du plugin répété à chaque Play

`tool/fx_plugin.lua` (vers la ligne 394) affiche « Dataky FX Studio : cliquez sur Connexion dans la barre Dataky FX. » à chaque chargement. Il sort donc **deux fois dans chaque log de Play** (client et serveur), ce qui pollue la sortie pendant les tests de jeu.

À faire : ne l'afficher qu'en Edit (`not RunService:IsRunning()`), une seule fois.

## P1 · Demandé par l'utilisateur : un mode « bac à sable » comme les plugins VFX de Roblox

Aujourd'hui, tout passe par la timeline (`timing.start / duration / mode / count`). On ne peut pas tester un émetteur à la main comme avec les plugins VFX de Roblox Studio. Ajoute un **mode Libre**, distinct du mode **Timeline** et sans modifier la recette :
- l'horloge de simulation tourne en continu ;
- les émetteurs `continuous` émettent à leur `Rate` tant qu'ils sont actifs ;
- les émetteurs `burst` n'émettent que sur Emit.

Ce mode doit marcher dans l'émulateur **et** dans l'aperçu natif Studio (pont du plugin), quand celui-ci est connecté.

### 4. Bouton Emit

- Un bouton **Emit** et un champ **quantité** dans le panneau d'un ParticleEmitter, avec par défaut le `count` du timing ou 30. Il fait un `Emit(n)` immédiat dans l'aperçu.
- **Emit sélection** (les émetteurs sélectionnés et leurs descendants) et **Emit tout** (tous les bursts de l'effet, chacun avec son count, immédiatement).
- Un bouton **Vider** qui efface les particules vivantes (`Clear`).

### 5. Interrupteur Enabled en direct

- Un interrupteur visible par objet (ParticleEmitter, Beam, Trail, lumières) dans l'arbre **et** dans le panneau de propriétés, qui allume ou éteint l'objet en direct, comme la case Enabled de Roblox.
- **En mode Libre**, c'est un état d'aperçu : il ne modifie pas la recette.
- **En mode Timeline**, il édite la propriété `Enabled` de la recette. Celle-ci est déjà respectée par l'émulateur (lignes 198-199) et par le runtime ; il faut qu'elle reste respectée et visible sur la piste de la timeline (barre grisée quand c'est éteint).
- Bonus : changer `Rate`, `Speed`, `Size`… en mode Libre se voit immédiatement, sans relancer.

### 6. Raccourcis clavier

Existants, à garder : Ctrl+S, Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y, Ctrl+D, Suppr/Retour arrière, `/`, Échap.

À ajouter. Aucun ne doit se déclencher quand on tape dans un champ ou qu'un dialogue est ouvert (même garde que l'existant) :

| Touche | Action |
| --- | --- |
| Espace | Lecture / pause |
| Shift+Espace | Stop (retour à 0, particules vidées) |
| E | Emit sur l'émetteur sélectionné (quantité du champ) |
| Shift+E | Emit tout |
| T | Interrupteur Enabled de la sélection |
| Tab | Basculer mode Timeline / mode Libre |
| C | Vider les particules |
| ← / → | Une image (1/30 s) en arrière / en avant |
| Shift+← / Shift+→ | 0,1 s en arrière / en avant |
| Début / Fin | Tête de lecture à 0 / à la fin |
| [ / ] | Événement de timing précédent / suivant (débuts de burst et de continu) |
| L | Boucle on/off |
| F | Cadrer la caméra sur la sélection |
| Shift+F | Cadrer tout l'effet |
| G | Sol on/off |
| M | Mannequin 5 studs on/off |
| 1 à 5 | Fonds sombre / gris / ciel / noir / roblox |
| ↑ / ↓ | Objet précédent / suivant dans l'arbre |
| Alt+↑ | Sélectionner le parent |
| Ctrl+C / Ctrl+V | Copier / coller la sélection avec ses enfants, aussi d'un projet à l'autre (presse-papiers JSON) |
| Ctrl+E | Export .rbxmx |
| Ctrl+Shift+E | Export .lua |
| ? | Fenêtre d'aide qui liste tous les raccourcis |

Bonus : rendre les raccourcis configurables (`editor/keybinds.json`), et les afficher en infobulle sur les boutons.

## P1 · Ce qui a coûté le plus de temps : jouer les recettes dans un vrai jeu

### 7. Runtime de jeu multi-instances

L'export actuel ne convient pas pour une unité animée :
- `--format lua`, comme le runtime, ne gère **qu'un effet à la fois** ;
- l'effet est aligné sur les axes du monde (décalage d'origine seulement, sans rotation) ;
- `apply` détruit la racine précédente.

Pour chaque unité, Claude a donc réécrit environ 300 lignes de Luau qui lisent les recettes et les jouent. Voir `brainrot td/BulbitoVFX/BulbitoCombat.lua`, fonctions `decode`, `build` et `playPiece`, ainsi que `TractoroVFX/TractoroCombat.lua`, qui est la même chose.

Demande : un module officiel, par exemple `tool/fx_kit.lua`, exporté avec le reste. API proposée :

```lua
local FX = require(DatakyFXKit)
local h = FX.play(recipe, cframe, {
    scale = 1,          -- multiplie Size, Speed, Acceleration des particules, positions d'Attachment, taille des Parts, Range des lumières
    speed = 1,          -- vitesse de la timeline
    follow = nil,       -- function() -> CFrame, ou Instance (Attachment, Bone : TransformedWorldCFrame, BasePart) suivie chaque frame
    hold = false,       -- les émetteurs continus restent allumés après leur durée jusqu'à Release
    params = {},        -- voir point 9 (radius…)
    quality = "Auto",   -- "Low" multiplie les counts de burst par 0,6 ("Auto" lit SavedQualityLevel <= 3)
    parent = nil,       -- dossier cible (défaut workspace.DatakyFX)
})
h:Release()   -- coupe les émetteurs continus, laisse vivre les particules, nettoie après la plus longue durée de vie
h:Stop()      -- détruit tout de suite
h:Move(cf)    -- replace l'effet
h:Part(id)    -- instance d'un nœud
FX.freeze() / FX.unfreeze()  -- TimeScale 0 + timelines en pause, pour les captures
```

Exigences :
- **la rotation de la CFrame est respectée** ;
- plusieurs instances peuvent jouer en même temps ;
- aucun `yield` dans `play` ;
- utilisable côté client ;
- nettoyage garanti (le dossier disparaît après la dernière particule) ;
- les animations de propriétés de la recette sont jouées ;
- les animations Position et Transparency des Parts servent seulement à l'aperçu et peuvent être ignorées, comme dans `BulbitoVFX/tools/export_lua.py`.

Teste-le avec le mock Luau existant (`tool/luau_roblox_mock.luau`, et `DATAKY_LUAU` si disponible).

### 8. Export « bibliothèque »

`fx.py export a.json b.json … --format library --out MesEffets.lua` doit produire **un seul** ModuleScript de données qui contient plusieurs recettes, avec le nom court de chaque recette comme clé, plus le module du point 7 à côté. Modèle : `brainrot td/BulbitoVFX/tools/export_lua.py` et la sortie `BulbitoVFX/BulbitoRecipes.lua`.

### 9. Rayon paramétrable

Une attaque de zone a un rayon de jeu variable. Aujourd'hui, Claude multiplie seulement la `Size` des émetteurs `VelocityPerpendicular` (anneaux à plat) par `rayon / rayon_d'auteur`. Le but : ne pas grossir aussi la poussière et les flammes.

Demande :
- `params` au niveau de la recette, par exemple `{"radius": {"default": 16}}` ;
- un marqueur par propriété d'émetteur, par exemple `"scaleWith": {"Size": "radius", "Speed": "radius"}` ;
- le runtime applique `params.radius / default` ;
- dans l'atelier, un curseur par paramètre ;
- dans le schéma, la validation.

## P2 · Confort et qualité

### 10. Bibliothèque Python officielle `tool/fx_builder.py`

Claude copie le même code dans chaque unité : la classe `Recipe` avec `part`, `att`, `em`, `trail`, `light`, `anim`, `flip`, `merge`, `save`, plus `NS`, `CS` et `NR`. Voir `brainrot td/BulbitoVFX/tools/build_recipes.py`, du début jusqu'à `def pix`. Fournis-la comme module importable, documentée et testée.

### 11. Inclure des pièces dans une recette

Pour prévisualiser une attaque complète, Claude fusionne des pièces avec un décalage de position et de temps (`merge`), mais **sans rotation**. Une pièce directionnelle comme un flash de canon ne peut donc pas être tournée.

Demande : dans les plans `compose`, ou comme nœud spécial, `{"include": "A1_Muzzle", "at": 0.44, "position": [...], "orientation": [...], "scale": 1}`. Bonus : une position animée, pour un projectile qui vole de A à B dans l'aperçu.

### 12. Avertissements de validation (pièges Roblox vus en Play)

1. **Flipbook OneShot dont les premières images sont presque vides, avec une Lifetime courte.**
   - Cas **mesuré** : « Upwards flame pillar » `70418763522849` avec Lifetime 0,2 à 0,45 s est invisible en Play. On ne voit que les toutes petites premières images, et c'est une volute blanche très pâle. La planche du catalogue, elle, a l'air bonne.
   - Calcule une fois la couverture alpha de chaque case à partir de `images/<id>.png` et mets-la en cache.
   - Avertis quand l'opacité moyenne sur la durée de vie est faible.
2. **Texture très pâle ou fine** (volute blanche) utilisée petite.
3. **`LightEmission` ≥ 0,6 avec une couleur saturée** : risque de blanc sur un fond clair.
4. **VelocityParallel avec un Squash positif** (après la correction 1) : probablement une erreur.
5. **`Transparency` qui ne finit pas à 1**, ou **`Size` qui ne finit pas près de 0** (déjà dans la doc, pas encore dans `validate`).
6. **Grille de flipbook `estimated`** utilisée. Mémoire de l'utilisateur : les grilles déduites peuvent être fausses.

### 13. Recherche de textures

- **`--compact`** (CLI) et option équivalente pour `search_assets` (MCP) : un tableau `id | nom | kind/grille | taille`. Le JSON actuel est très long : une recherche sur « star » remplit l'écran.
- **`--exclude-file used.txt`** (ou `--exclude-ids`) pour ignorer les textures déjà prises par d'autres effets du jeu. Chaque unité doit avoir ses propres textures. Modèle : `brainrot td/BulbitoVFX/tools/texfind.py`.
- **`fx.py sheet id1 id2 … --out planche.png`** : une planche annotée des IDs choisis, avec la grille de flipbook dessinée et la mention « USED » pour les textures exclues. Modèle : `brainrot td/CornVFX/tools/sheet.py`.

### 14. Rendu de l'émulateur

- **Lenteur** : environ 60 à 90 s par rendu de 5 à 8 instants, car Playwright est relancé à chaque fois. Garde un navigateur chaud entre deux rendus, ou ajoute `render-batch` (plusieurs recettes × instants × caméras en un seul lancement).
- **Cadrage** : avec la caméra automatique, un petit effet comme un flash de canon de 3 studs est illisible quand il est placé loin dans une recette « complète ». Ajoute `--fit NODE_ID` ou `--focus x,y,z --radius r`.
- **Captures figées** : un Trail ne s'affiche pas sur une image figée (son historique continue de s'effacer). C'est une limite connue de Roblox, à documenter seulement.

### 15. Aperçu natif dans Studio

**Mesuré** : quand la fenêtre de Studio est en arrière-plan, Roblox ralentit la simulation des particules et les captures montrent des jets figés. Si le plugin peut le détecter (par exemple `UserInputService.WindowFocusReleased` / `WindowFocused`, à vérifier, ne l'invente pas), affiche un avertissement dans l'atelier quand l'aperçu natif tourne alors que Studio n'a pas le focus.

### 16. Documentation

`CLAUDE.md` doit couvrir :
- la correction du Squash ;
- le piège des flipbooks qui commencent vides ;
- le mode Libre et les raccourcis ;
- le kit multi-instances.

Tant que le point 7 n'existe pas, dis clairement que l'export `.lua` ne joue qu'un effet à la fois, aligné sur le monde.

## Rapport attendu à la fin

- Ce qui est fait, point par point, avec les fichiers modifiés.
- Ce qui n'est pas fait ou pas sûr, et pourquoi.
- Les tests lancés et leur résultat (sortie réelle).
- Comment tester à la main : quel bouton, quelle commande.
