# Mémoire artistique portable

`tool/fx_ai_memory.py` conserve des observations explicites et retrouve les
références pertinentes par recherche textuelle. Il ne crée pas de VFX, n'entraîne
pas le modèle et ne reconstruit pas de propriétés Roblox depuis une vidéo.

## Sources et provenance

* Références ajoutées explicitement : URL de source, description, phases et
  horodatages éventuels, palette, tags et notes. Elles vivent dans
  `editor/local_ai/knowledge.json`, avec un ID et une provenance.
* Annotations vidéo humaines déjà enregistrées dans
  `editor/local_ai/video/analyses/<id>/annotations/`. Elles sont relues sans
  modification. Les IDs d'analyse et de référence, l'URL et les fenêtres
  temporelles restent dans le contexte retrouvé. Les phases d'analyse ne sont
  reprises comme phases artistiques que lorsqu'elles sont explicitement manuelles.
* Avis acceptation/rejet dans `editor/local_ai/feedback/`, liés à leur génération.
  Le dernier avis explicite est conservé par génération. Son commentaire reste
  attribué à l'utilisateur. Accepter une création violette n'est pas transformé
  en préférence générale pour le violet ; un refus sans raison n'en invente pas.

Une annotation de vidéo n'est jamais créée automatiquement à partir des seuls
changements de luminosité ou des images extraites. Une annotation externe
`observer="vision"` exige une preuve textuelle fournie par son auteur ; la mémoire
la conserve comme une observation déclarée, sans affirmer avoir exécuté un modèle
vision ni avoir vérifié les pixels.

Les sources et notes sont des données de référence, pas des instructions qui
remplacent la demande en cours. Les techniques exactes non connues et les droits
non documentés restent inconnus. Aucune ressource distante n'est téléchargée.

## API

```python
from tool import fx_ai_memory as memory

record = memory.add_reference({
    "source_url": "https://example.org/reference",
    "description": "Une lame cyan étroite suivie d'une traînée plus fine",
    "tags": ["sword", "slash"],
    "phases": [{"name": "impact", "start": 0.5, "end": 0.7}],
    "notes": "Observation humaine : le flash ne masque pas le tranchant."
}, root=application_folder, observer="human")

context = memory.search("entaille cyan avec impact lisible", root=application_folder, limit=4)
```

`search` renvoie `items`, `method="lexical"`, `counts`, `revision`,
`total_matches`, `warnings` et `limitations`. La révision SHA-256 suit les données
réellement lues. Les sources sont relues à chaque appel ; les nouvelles
annotations et les nouveaux avis sont donc récupérables sans redémarrer.

## Limites et vérification

La recherche utilise les noms, descriptions, tags, notes, observations et des
synonymes français/anglais simples. Il ne s'agit pas d'embeddings ni d'une mesure
de similarité visuelle. Des vecteurs locaux pourront être ajoutés plus tard avec
un protocole de mesure et une invalidation de cache explicite.

Chaque recherche renvoie au plus huit références et borne les extraits pour le
contexte du modèle. Les notes complètes restent conservées sur disque. Le registre
accepte 512 références et 8 Mio ; les sources externes sont bornées à leurs 512
fichiers les plus récents par catégorie, avec avertissement si la limite est
atteinte. Les avis et les analyses externes ne sont jamais réécrits par ce module.

L'index utilise une écriture atomique et un verrou entre processus. Une erreur de
JSON dans l'index explicite est visible ; les sources externes corrompues sont
ignorées avec avertissement. Les chemins relatifs et les IDs permettent de
déplacer la copie complète de l'application avec ses références.

`tool/test_fx_ai_memory.py` vérifie provenance, refus des horodatages invalides,
notes vision non attestées, annotations vidéo humaines, avis non transformés en
goûts généraux, lecture sans modification des sources, portabilité et quatre
processus d'écriture simultanés. Aucun test n'utilise des recettes de VFX
prédéfinies pour alimenter le modèle.
