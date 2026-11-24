# OpenSim AI Bridge v1.0.0 — Installation / evaluation guide

This is the **public release's minimal standalone evaluation path**. The Web controller and multi-bot system require separate administrative setup and review; do not assume the historical BloodMoon installation scripts are universal or safe to run unchanged.

## Français — première connexion sans interface Web

**Prérequis :** Linux x64, runtime .NET 8 (`dotnet --list-runtimes` doit afficher `Microsoft.NETCore.App 8.x`), Python 3 pour le lanceur, accès réseau aux ports de la grille, un **compte avatar OpenSimulator de test**. Ne jamais connecter le même avatar simultanément depuis le bot et Firestorm.

1. Depuis la page **Releases**, télécharger l'archive `OpenSim-AI-Bridge-v1.0.0-linux-x64.zip` et `SHA256SUMS.txt`. Vérifier l'empreinte avant de l'extraire :
   ```bash
   sha256sum -c SHA256SUMS.txt
   ```
2. Décompresser l'archive dans un répertoire appartenant à **un utilisateur Linux non privilégié**, par exemple `~/opensim-ai-bridge`. Le contenu est organisé autour de `OpenSimAiBridge.Bot.dll`, `config/`, `scripts/`, `controller/`, `web/` et `deploy/`. Ne pas publier ce répertoire dans le DocumentRoot du serveur Web.
3. Créer un fichier de configuration **privé** à la racine du dossier :
   ```bash
   cp config/appsettings.example.json appsettings.json
   chmod 600 appsettings.json
   nano appsettings.json
   ```
   Renseigner l'URL de connexion `Grid.LoginUri`, `Grid.AvatarFirstName`, `Grid.AvatarLastName` et `Grid.StartLocation`. Dans l'exemple `Ai.Enabled=false` : les commandes IM de test fonctionnent sans clé de fournisseur. `Bot.ProximityWelcome.Enabled=false` et `FaceVisitor=false` par défaut.
4. Enregistrer le mot de passe du **compte avatar**, sur une ligne dans le même répertoire, sans l'afficher :
   ```bash
   umask 077
   touch bot-password.txt
   chmod 600 bot-password.txt
   nano bot-password.txt
   ```
   Le fichier `bot-password.txt` est **privé**, ne jamais le partager ni l'ajouter au dépôt Git.
5. Avant toute connexion, lancer les contrôles hors ligne depuis le dossier extrait :
   ```bash
   dotnet OpenSimAiBridge.Bot.dll --verify-ai-safety
   dotnet OpenSimAiBridge.Bot.dll --verify-knowledge
   dotnet OpenSimAiBridge.Bot.dll --verify-welcome
   ```
6. Lancer le bot au premier plan avec l'utilisateur non privilégié :
   ```bash
   bash scripts/start-bot.sh
   ```
   Attendre `Connected in ...`, puis envoyer un **IM privé** contenant `ping` ou `where` depuis un autre avatar. Arrêt : `Ctrl+C` dans ce terminal. Observer les éventuelles erreurs dans la console, sans divulguer d'identifiants.

**Accueil des visiteurs :** dans `appsettings.json`, `Bot.ProximityWelcome.Enabled=true` active les annonces en chat local ; `FaceVisitor=true` permet la rotation ponctuelle. Configurer `RadiusMeters`, `RepeatDelayMinutes` et `Message` (variable `{avatar_name}`). Les bots déjà présents au lancement ne sont pas salués en masse. La détection utilise les positions complètes des avatars de la région et convient aux varregions.

**Pour l'IA distante :** commencer avec le mode `Ai.Enabled=false`, puis configurer **son propre compte fournisseur et des plafonds de dépense**. Les détails du routeur multi-fournisseurs sont dans [MULTI_PROVIDER_ROUTING_FR.md](MULTI_PROVIDER_ROUTING_FR.md). Ne jamais mettre les clés dans GitHub, les tickets, les fichiers Web ou les messages de chat. Le passerelle de traduction Azure est **facultative** et n'est pas fournie comme service public.

**Administration HTTPS / multi-bots :** consulter [WEB_INSTALL_V02_FR.md](WEB_INSTALL_V02_FR.md) et [MULTI_BOT_V02_FR.md](MULTI_BOT_V02_FR.md) comme **références historiques d'architecture**, pas comme un installateur prêt à exécuter sur une nouvelle machine. Le contrôleur tourne avec des droits élevés ; revue manuelle des unités systemd, chemins, permissions, UID PHP et secrets obligatoire. Une installation généraliste automatisée n'est pas encore fournie.

**Mise à jour d'un service en production :** réaliser une sauvegarde des anciennes DLL, du contrôleur et du site Web, **laisser les fichiers privés intacts**. Arrêter les avatars depuis la maintenance générale. Installer uniquement les nouveaux fichiers vérifiés pendant que le verrou est actif, puis terminer la maintenance **depuis le panneau Web** ; systemd bloquera à juste titre les redémarrages tant que `global-maintenance.lock` est présent. Ne jamais supprimer manuellement ce verrou pour contourner la sécurité.

## English — standalone headless smoke test

**Requirements:** Linux x64, .NET 8 runtime, Python 3, network connectivity to an OpenSimulator grid, a dedicated test avatar account. Never log in using a viewer and the bot simultaneously.

1. Download the versioned ZIP and `SHA256SUMS.txt` from the GitHub Release. In the download folder verify `sha256sum -c SHA256SUMS.txt`, then extract the ZIP to an unprivileged user's **non-Web** directory such as `~/opensim-ai-bridge`.
2. From the extracted folder copy `config/appsettings.example.json` to `appsettings.json`, `chmod 600 appsettings.json`, and edit `Grid.LoginUri`, avatar first/last names and `Grid.StartLocation` to match **your own** grid. AI and visitor greetings are disabled by default.
3. Create a private one-line `bot-password.txt` containing the avatar account password; `chmod 600 bot-password.txt`. Never publish either file.
4. Run the offline checks:
   ```bash
   dotnet OpenSimAiBridge.Bot.dll --verify-ai-safety
   dotnet OpenSimAiBridge.Bot.dll --verify-knowledge
   dotnet OpenSimAiBridge.Bot.dll --verify-welcome
   ```
5. Run `bash scripts/start-bot.sh` as an **unprivileged** local user. Once logged in, test a private `ping` IM from another account. Stop with Ctrl+C.
6. Configure your own remote provider accounts only after reviewing request limits, data handling and billing. Never assume the BloodMoon translator gateway is public. For optional greet/turn configuration see [PROXIMITY_WELCOME_FR.md](PROXIMITY_WELCOME_FR.md).

**Advanced features:** The authenticated Web/PHP controller and multi-bot services must be deployed and permission-reviewed for **your** system. Existing installation walkthroughs describe the BloodMoon pilot and are not a general installer. Read [SECURITY.md](../SECURITY.md) before exposing any administration. This distribution has no explicit project license yet; receiving the archive does not imply open-source reuse rights.
