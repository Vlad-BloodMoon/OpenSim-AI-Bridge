# Service Linux et mode Firestorm (V0.2 en préparation)

**État :** service installé et cycle local démarrage/arrêt/Firestorm/reprise **testé avec succès sur BloodMoon le 23 novembre 2026**. L'interface Web et la tenue après reboot ne sont pas encore validées.
Le pilote dispose déjà de son répertoire `/home/louna49400/OpenSim-AI-Bridge` et de son mot de passe privé `bot-password.txt`.

## But
Éviter `screen` et la session SSH persistante ; fournir un service indépendant de ROBUST, avec démarrage / arrêt / redémarrage et une maintenance persistante.
Le bot ne doit jamais se reconnecter pendant que son compte est utilisé dans Firestorm.

## Fichiers dans le dépôt
- `scripts/start-bot.sh` : lit le mot de passe local, respecte le verrou `maintenance.lock`, lance le binaire par `dotnet`.
- `scripts/control-bot.sh` : commandes administrateur locales, distinctes de l'API Web à venir.
- `deploy/systemd/opensim-ai-bridge.service.example` : unité systemd avec placeholders `@BOT_USER@` et `@INSTALL_DIR@` à adapter.
- `maintenance.lock` : créé automatiquement lors du mode Firestorm ; **ne pas publier ce fichier**.

## Sécurité
- L'exemple de service doit tourner sous un compte Linux non privilégié.
- Vérifier que `appsettings.json` et `bot-password.txt` restent lisibles seulement par le compte de service ; mode 0600.
- L'administration Web ne doit **pas** appeler directement `sudo`, `systemctl` ou `control-bot.sh` à partir d'une entrée utilisateur. Un contrôleur à commandes fixes et à authentification stricte sera créé.
- Le mode Firestorm écrit d'abord un verrou persistant, puis arrête le service. Même après reboot, l'unité refuse une nouvelle connexion si le verrou est présent.
- N'activez pas de démarrage automatique avant d'avoir testé le service et l'arrêt propre.
- Un arrêt par `systemctl stop` n'active **pas** le verrou Firestorm ; utilisez la commande dédiée `firestorm` lorsqu'un viewer doit prendre le relais.

## Procédure d'installation proposée (à faire après vérification de l'environnement)
1. Vérifier qu'aucune session manuelle du bot ne tourne : `pgrep -af 'OpenSimAiBridge.Bot'`.
2. Déployer les nouveaux scripts et conserver une copie des fichiers privés.
3. Remplacer les placeholders du modèle systemd par l'utilisateur et le répertoire d'installation réels.
4. Installer le fichier dans `/etc/systemd/system/` puis lancer `sudo systemctl daemon-reload` et tester **sans** `enable`.
5. Tester successivement `status`, `start`, `stop`, `firestorm`, `resume` et le maintien de maintenance après redémarrage du service.
6. Ne pas raccorder l'interface Web avant que ces essais soient validés.

**Rappel :** ces scripts sont des bases de déploiement à tester ; ne pas les utiliser comme une installation en un clic sur une grille de production.
