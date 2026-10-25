# Animations de mouvement dans les exports Roblox

Les pistes `Part` et `MeshPart` portant sur `Position` ou `Transparency` peuvent
participer à l'effet joué par `DatakyFXKit` avec le booléen optionnel
`animations[].runtime: true`.

```json
{
  "node": "orb",
  "property": "Position",
  "runtime": true,
  "keyframes": [
    {"time": 0, "value": [2, 0, 0]},
    {"time": 0.5, "value": [3, 2, 0]},
    {"time": 1, "value": [4, 0, 0]}
  ]
}
```

La valeur de `Position` est la position absolue dans les coordonnées de la
recette, comme `nodes[].properties.Position`. Le kit applique `options.scale`,
puis la translation et la rotation de la `CFrame` passée à `FX.play`. Une
`Orientation` animée sur le même objet compose sa rotation avec cette `CFrame`.
`h:Move(cf)` et `follow` utilisent le mouvement local déjà calculé : le mouvement
artistique suit donc le point d'attache du gameplay. Chaque handle possède son
état de position et de rotation ; les recettes et les gabarits préparés restent
inchangés.

Une piste `Transparency` marquée `runtime: true` joue normalement dans le kit.
Après `h:Release()`, les pistes de propriétés cessent d'évoluer ;
`h:Release({hideParts=true})` conserve ainsi les Parts invisibles pendant que les
dernières particules finissent de vivre.

## Compatibilité

- Avec `runtime` absent ou `false`, les pistes `Position` et `Transparency` des
  Parts/MeshParts conservent leur comportement historique : le kit les ignore.
- Les autres pistes, notamment `Attachment.Position`, `Part.Size` et
  `Part.Orientation`, continuent de jouer sans marqueur supplémentaire. `runtime`
  n'est pas un interrupteur général : `false` ne les désactive pas.
- Le validateur accepte uniquement un booléen et préserve sa présence, y compris
  `false`. Les exports JSON, bibliothèque Lua et `.rbxmx`, ainsi que
  `merge_recipes`, le conservent.
- Les lecteurs historiques Lua et `.rbxmx` jouent déjà toutes les pistes. Leur
  comportement reste identique, y compris le placement suivant uniquement la
  translation de leur origine. Utiliser bibliothèque + kit pour composer une
  rotation et un suivi de gameplay.
- Les `MeshPart` demandent toujours `FX.preload(recipe)` avant `FX.play`.
- Les limites existantes restent applicables : 1 000 clés par piste, une piste
  par couple objet/propriété et interpolation linéaire des vecteurs. Un
  générateur procédural doit précalculer ses clés dans ces limites.

## Vérification

`tool/test_fx_kit.py` exécute le véritable code Luau avec le mock Roblox partagé :
comportement historique, `runtime: false`, rejet des valeurs invalides, mouvement
Part et MeshPart, échelle, translation, rotation, suivi, `Move`, deux handles et
ordre des pistes Position/Orientation. Les tests schéma, fusion, bibliothèque et
`.rbxmx` vérifient la conservation du marqueur. Le lecteur embarqué dans le
`.rbxmx` est aussi exécuté par Luau sur des instances reconstruites depuis le
fichier exporté.

```powershell
$env:DATAKY_LUAU = 'C:\chemin\vers\luau.exe'
python -m unittest tool.test_fx_kit tool.test_fx_rbxmx tool.test_fx_server.SchemaTests tool.test_fx_builder
```
