# Application Windows

Double-cliquez sur **Dataky FX Studio.exe**, à la racine du projet. L’atelier s’ouvre dans une fenêtre dédiée, sans terminal. Une icône près de l’horloge permet de rouvrir l’atelier ou de quitter son serveur local. Fermer la fenêtre de l’atelier laisse le serveur disponible ; choisissez **Quitter Dataky FX Studio** pour l’arrêter.

Le lanceur utilise Python 3 déjà installé, .NET Framework et Edge, Chrome ou Brave. Sans navigateur compatible, il ouvre le navigateur par défaut. Il ne contient aucun modèle d’IA. Conservez l’exécutable avec les dossiers `tool`, `editor` et le catalogue. Il réutilise uniquement le serveur correspondant à cette copie du projet et n’arrête que le serveur qu’il a démarré.

Pour reconstruire le lanceur depuis ses sources sur Windows : `powershell -File desktop/build.ps1`. La compilation utilise le compilateur .NET Framework présent dans Windows. Le catalogue et les projets restent dans le dossier de l’application.
