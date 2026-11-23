# Installation / premier test V0.1 (expérimental)

La V0.1 est un premier client **sans IA**. Elle utilise le paquet LibreMetaverse **3.3.1** depuis NuGet ; son fonctionnement doit être vérifié sur OpenSimulator 0.9.3.1.

## Prérequis
- Linux avec SDK .NET **8** (le runtime seul ne suffit pas pour compiler).
- Accès réseau au service de login et au simulateur de la région de test.
- Un vrai compte avatar OpenSimulator dédié, **sans droits administrateur**.
- Ne pas lancer avec un compte root. Ne pas créer de service systemd avant la validation interactive.

## Préparer la configuration (sur le serveur uniquement)

```bash
git clone https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge.git
cd OpenSim-AI-Bridge
cp config/appsettings.example.json appsettings.json
```

Modifier **le fichier privé** `appsettings.json` (ignoré par Git) :
- `Grid.LoginUri` : URL réelle du service de connexion de la grille (à confirmer).
- `Grid.AvatarFirstName` / `AvatarLastName` : nom du compte bot.
- `Grid.StartLocation.RegionName` : par défaut `BloodMoon_TEST` dans l'exemple pilote.
- `Grid.StartLocation.Position` : X, Y, Z du point de départ.

Le mot de passe **n'est pas** stocké dans le JSON. Un modèle `bot-password.example.txt` se trouve **à la racine du dépôt**, au même niveau que le programme publié. Sur le serveur, créer le fichier privé `bot-password.txt` à ce même emplacement (avec **une seule ligne contenant le mot de passe**) :

```bash
cp bot-password.example.txt bot-password.txt
chmod 600 bot-password.txt
nano bot-password.txt
```

**Important :** le nom `bot-password.txt` est exclu par `.gitignore`, mais ne doit jamais être publié ou transféré avec un mot de passe réel. Ne pas transmettre la valeur dans le chat, un ticket GitHub ou une capture d'écran.

La V0.1 lit toujours le secret depuis une variable d'environnement. Pour charger la valeur depuis le fichier **dans le même terminal que le lancement**, sans l'afficher :

```bash
read -r OSAI_AVATAR_PASSWORD < bot-password.txt
export OSAI_AVATAR_PASSWORD
```

Le futur service systemd utilisera ce fichier protégé automatiquement, sans commande manuelle.

## Compiler et essayer (après validation de la configuration)

```bash
dotnet restore src/OpenSimAiBridge.Bot/OpenSimAiBridge.Bot.csproj
dotnet build src/OpenSimAiBridge.Bot/OpenSimAiBridge.Bot.csproj -c Release --no-restore
dotnet run --project src/OpenSimAiBridge.Bot/OpenSimAiBridge.Bot.csproj -c Release --no-build -- appsettings.json
```

Dans Firestorm, envoyer un IM **ping** à l'avatar : il doit répondre `Pong !`.
Tester ensuite `where`. Le chat local est seulement observé ; aucune réponse automatique n'est publiée.

Arrêt : `Ctrl+C`.

### Sécurité et limites
- Ne pas lancer simultanément le bot et un viewer avec le même compte.
- Reconnexion expérimentale après déconnexion, pas encore supervisée.
- Les IM de test sont limités aux commandes exactes.
- Le prototype ne fournit encore ni interface Web, ni lecture ROBUST, ni OpenAI, ni traduction.
- Si le login échoue, conserver les messages d'erreur **sans mot de passe ni secrets**, puis analyser ensemble.
- Compilation GitHub Actions réussie et premiers tests IM validés sur BloodMoon le 20 novembre 2026 : voir [compte rendu](TESTS_2026-11-20_FR.md). Les tests de reconnexion, d'apparence et de stabilité longue durée restent à faire.
