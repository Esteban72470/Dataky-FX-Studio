# Application Windows

Double-cliquez sur **Dataky FX Studio.exe**, à la racine du projet. L’atelier s’ouvre dans une fenêtre dédiée, sans terminal. Une icône près de l’horloge permet de rouvrir l’atelier ou de quitter son serveur local. Fermer la fenêtre de l’atelier laisse le serveur disponible ; choisissez **Quitter Dataky FX Studio** pour l’arrêter.

Le lanceur utilise Python 3 déjà installé, .NET Framework et Edge, Chrome ou Brave. Sans navigateur compatible, il ouvre le navigateur par défaut. Il ne contient aucun modèle d’IA. Conservez l’exécutable avec les dossiers `tool`, `editor` et le catalogue. Il réutilise uniquement le serveur correspondant à cette copie du projet et n’arrête que le serveur qu’il a démarré.

Pour reconstruire le lanceur depuis ses sources sur Windows : `powershell -File desktop/build.ps1`. La compilation utilise le compilateur .NET Framework présent dans Windows. Le catalogue et les projets restent dans le dossier de l’application.

## Fichier complet autonome

Le paquet **DatakyFX-Studio-Complet.exe** intègre l’atelier, son catalogue et ses ressources, Python, les dépendances vidéo et images, Node et Chromium. Double-cliquez sur ce seul fichier : la préparation se fait automatiquement au premier lancement. Les lancements suivants réutilisent les ressources préparées et conservent les projets enregistrés.

Le fichier complet est construit localement depuis `desktop/build_portable.py`, avec un runtime préparé hors du dépôt. Exemple : `python desktop/build_portable.py --root . --runtime CHEMIN_RUNTIME --out CHEMIN_SORTIE.exe --payload-zip CHEMIN_TEMPORAIRE.zip`. Le runtime comprend les sous-dossiers `python`, `node`, `node_modules` et `browsers`. Le lanceur choisit ces composants embarqués en priorité.

## Mises à jour automatiques

Le fichier complet vérifie les versions stables publiées sur [GitHub Releases](https://github.com/Esteban72470/Dataky-FX-Studio/releases) à chaque démarrage. Il installe les mises à jour du programme avant d’ouvrir l’atelier, après vérification de leurs empreintes SHA-256. Le catalogue, les projets, les médias personnels et les runtimes restent dans leurs dossiers. Les mises à jour du programme utilisent une petite archive séparée du téléchargement complet.

Si l’atelier est déjà ouvert pour cette copie, la mise à jour attend le prochain démarrage après fermeture. Sans réseau ou si une vérification échoue, la version installée reste disponible. Les résultats sont enregistrés dans `editor/desktoplogs/update-status.json`. Le menu de l’icône près de l’horloge permet aussi de vérifier les mises à jour et d’ouvrir la page de téléchargement. Le petit lanceur ouvert directement vérifie les versions ; relancez le fichier complet pour installer automatiquement une nouvelle version.

Lors du premier lancement d’un nouveau fichier complet, les fichiers personnels absents sont recopiés depuis la précédente copie préparée, en privilégiant celle qui est ouverte. Aucun fichier existant ni original n’est remplacé. Cette recopie n’est pas exécutée pendant `--self-test`.

L’option `--include-user-data` ajoute les projets et médias personnels présents dans cette copie au fichier complet. Le paquet personnel préparé pour le propriétaire reste local ; seuls les sources du constructeur et le petit lanceur sont versionnés dans le dépôt.
