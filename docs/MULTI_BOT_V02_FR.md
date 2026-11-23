# Gestion multi-avatars — V0.2 (preview, à tester)

**Objectif :** depuis l'administration Web, renseigner un compte avatar OpenSimulator existant (Prénom, Nom, mot de passe), une région de départ et des coordonnées X/Y/Z, puis cliquer **Ajouter et connecter**. Chaque compte possède son service systemd, son verrou Firestorm, son état de présence, son jeu de réglages et son fichier secret séparés.

## Important : état réel

- Le service **BloodMoon AI existant n'est pas migré** et conserve `opensim-ai-bridge.service`, `/home/louna49400/OpenSim-AI-Bridge/appsettings.json` et `bot-password.txt`.
- Les nouveaux avatars utilisent des instances `opensim-ai-bridge@<id>.service` générées avec un ID aléatoire hexadécimal contrôlé côté serveur. Il est impossible de fournir arbitrairement un nom de service.
- Les répertoires privés se trouvent sous `/var/lib/opensim-ai-bridge/bots/<id>/` : un `appsettings.json` et un `bot-password.txt` séparés, fichiers mode 0600, sous-dossier `data/` pour le heartbeat, verrou `maintenance.lock` par avatar.
- Le service du nouvel avatar est activé au reboot et démarré immédiatement avec `systemctl enable --now`. Si le compte n'existe pas sur ROBUST, ou si le mot de passe est incorrect, le service pourra tourner et retenter la connexion sans être authentifié ; consulter son statut et ses logs sans jamais partager ses secrets.
- **Ne jamais connecter simultanément un même compte dans Firestorm et comme bot.** Le mode Firestorm est indépendant par compte.
- Les fonctions `list_bots`, `create_bot` et les commandes existantes, maintenant adressées via `botId`, passent par le socket UNIX privé et exigent l'authentification Web actuelle. Le mot de passe est transmis uniquement lors de la création vers le contrôleur local et jamais renvoyé par les actions de lecture.
- La version preview sait désormais supprimer un bot secondaire depuis « Mes avatars », après confirmation explicite de son nom. Renommer ou restaurer un bot supprimé reste à développer.

## Installation sur robust-vm — ne pas tout faire d'un coup

1. Vérifier la compilation GitHub Actions après ajout de tous les fichiers.
2. Télécharger l'artifact récent dans `/home/louna49400/OpenSim-AI-Workspace/MULTI-BOT-V02/`.
3. Sur le serveur, **installer le contrôleur privilégié seulement depuis les fichiers vérifiés**. Le script inclus `scripts/install-multibot.sh` prépare l'unité modèle, le stockage privé, et met à jour le contrôleur (pas le bot principal) :

```bash
sudo bash /home/louna49400/OpenSim-AI-Workspace/MULTI-BOT-V02/scripts/install-multibot.sh \
  /home/louna49400/OpenSim-AI-Workspace/MULTI-BOT-V02
```

Ce script est prévu pour l'environnement pilote (compte Linux `louna49400`, installation `/home/louna49400/OpenSim-AI-Bridge`). Toujours **vérifier et tester avant de le lancer**, car il installe un contrôleur root. Ne pas exposer directement ce code au Web. Il ne redémarre pas le bot existant.
4. Copier uniquement le nouvel `web/OpenSim_AI/index.php` vers `/var/www/BloodMoon/OpenSim_AI/index.php` en conservant le propriétaire `louna49400` et groupe `www-data`. Le site et le fichier de secret Web existent déjà.
5. Vérifier les statuts des deux services et tester une création avec **un compte de test autorisé**, et non avec un compte actuellement utilisé dans Firestorm.
6. Après création, choisir l'avatar dans **Mes avatars**, voir sa présence et ses paramètres, tester arrêt et reprise indépendamment du bot principal.

### Sécurité

- Le contrôleur Python est installé dans `/usr/local/libexec/opensim-ai-bridge/` sous `root:root`. La partie `www-data` ne doit jamais pouvoir le modifier.
- Le contrôleur root doit pouvoir écrire uniquement dans les emplacements nécessaires ; son unité a `ReadWritePaths` pour le répertoire privé des avatars et l'installation existante.
- L'accès Web par simple mot de passe protège des actions d'administration sensibles. Avant une ouverture large du service, mettre en place authentification supplémentaire (2FA/SSO) et isolation PHP-FPM par pool utilisateur ; la vérification actuelle du socket par UID `www-data` n'isole pas encore toutes les applications PHP hébergées sous ce même UID.
- Ne pas copier les mots de passe ou les fichiers privés dans GitHub, ni dans les sauvegardes publiques du site.
- Cette version ne remplace pas les tests de sécurité de production. L'administration n'autorise pas d'exécuter des commandes arbitraires, seulement des opérations définies côté contrôleur.

## Vérifications restantes avant déclaration « fonctionnel »

- Compilation/validation PHP et Python dans GitHub Actions, puis tests sur `robust-vm`.
- Enregistrer un second bot puis vérifier la connexion (IM, région, coordonnées).
- Vérifier le fonctionnement indépendant des commandes arrêt / relance / Firestorm.
- Vérifier l'autostart au reboot **sans redémarrer ROBUST pendant les premiers essais**.
- Vérifier la confidentialité des secrets et le refus des ID invalides.
- Confirmer que le bot principal n'a été ni déconnecté ni modifié.

## Évolutions

À venir : supprimer/archiver proprement un bot, changer le mot de passe, profils de permissions par avatar, moteurs FAQ distincts/partagés, traduction et IA distante avec quotas séparés.

## Navigation de l'administration (23 novembre 2026)

L'interface n'empile plus tous les paramètres sur une seule page. Le menu distingue quatre rubriques accessibles via des URLs internes contrôlées :

- **Tableau de bord** : état du bot choisi, présence/région/coordonnées et démarrage/arrêt/Firestorm.
- **Mes avatars** : grille compacte des comptes et formulaire d'ajout repliable, ouvert seulement lorsque nécessaire.
- **Configuration** : région et XYZ de départ et options IM/chat/reconnexion du bot sélectionné.
- **Modules IA** : emplacement réservé aux futures fonctions FAQ, traduction, fournisseurs distants, permissions et journaux. Les modules ne sont pas encore fonctionnels.

Chaque requête POST inclut l'identifiant serveur du bot sélectionné et sa rubrique pour éviter d'agir involontairement sur le bot principal. Les données de formulaire sont traitées par le même backend PHP authentifié, sans aucun mot de passe renvoyé à la page.

**À tester au déploiement :** passer d'un bot à l'autre via « Mes avatars » puis vérifier que les boutons et réglages ciblent le compte sélectionné, surtout après changement d'onglet.

## Actualisation des informations — 23 novembre 2026

Les anciens bandeaux de succès (« connexion en cours » / « Commande exécutée ») restaient à l'écran après une action POST, sans indiquer la réalité de la connexion. Le correctif utilise **POST → HTTP 303 → GET** et une notification de session consommée une seule fois. La page **Tableau de bord** se réactualise automatiquement toutes les 10 secondes pour lire la présence et l'état réels depuis le contrôleur, sans republier de commande. Les pages **Mes avatars** et **Configuration** ne s'actualisent pas automatiquement afin de ne pas perdre des saisies. Ceci est un rechargement ciblé de page, pas encore une API AJAX en temps réel. Vérifier en production qu'un démarrage, un arrêt et la connexion de Jolie Candy mettent à jour l'état sans laisser de bandeau obsolète.

## Maintenance globale de tous les bots (23 novembre 2026)

Depuis **Maintenance générale**, l'administrateur peut choisir **Arrêter tous les bots et verrouiller**, après avoir coché une confirmation explicite. Le contrôleur, et non PHP, détermine automatiquement la liste autorisée de services : `opensim-ai-bridge.service` et `opensim-ai-bridge@<id>.service` pour chaque bot enregistré. Aucune unité ROBUST, Money ou simulateur n'est ciblée.

- Avant l'arrêt, un instantané privé `/var/lib/opensim-ai-bridge/global-maintenance-state.json` mémorise les services effectivement actifs.
- Un verrou persistant `/var/lib/opensim-ai-bridge/global-maintenance.lock` empêche depuis le contrôleur les démarrages individuels, les reprises Firestorm et la création de bots. Les unités systemd principale et à instances utilisent également `ConditionPathExists=!/var/lib/opensim-ai-bridge/global-maintenance.lock` : après reboot, aucun bot ne doit redémarrer avant une reprise explicite.
- L'arrêt effectif est transmis à systemd en une seule commande `stop` pour tous les bots.
- Le bouton **Terminer la maintenance et relancer** enlève le verrou puis tente de relancer **uniquement** ceux actifs avant l'arrêt, sans supprimer les verrous Firestorm individuels ni démarrer un bot précédemment arrêté.
- Le contrôleur local reste accessible pendant toute l'opération, et le menu Web affiche le nombre de services enregistrés, actifs et l'état du verrou global.

**Installation** : relancer `scripts/install-multibot.sh` depuis le nouvel artefact GitHub pour appliquer le contrôleur et ajouter le drop-in systemd de l'ancien service. Installer le PHP du même artefact. Ces opérations ne nécessitent pas d'arrêter les bots. Avant d'utiliser le bouton global, vérifier la présence du drop-in, des deux unités et des fichiers privés, puis effectuer un arrêt et une reprise en conditions contrôlées.

**Attention :** pendant la maintenance, remplacer uniquement les DLL réellement partagées sous `/home/louna49400/OpenSim-AI-Bridge/`. Le script ne remplace aucune DLL automatiquement. Ne jamais supprimer `appsettings.json`, les mots de passe, ni les profils sous `/var/lib/opensim-ai-bridge/bots/`. La reprise peut échouer partiellement ; regarder les états réels avant de déclarer l'opération terminée.

## Consommation RAM et CPU par service (23 novembre 2026)

Dans **Tableau de bord → État du service**, chaque avatar sélectionné affiche désormais :
- **Mémoire RAM (Mo)** : `systemctl show <service> --property=MemoryCurrent`, divisée par 1 048 576. La valeur inclut la mémoire comptabilisée par systemd pour le cgroup du service (pas uniquement la mémoire managée .NET).
- **CPU (%)** : delta de `CPUUsageNSec` sur le temps monotone écoulé entre deux interrogations du **même service** dans le contrôleur Python. 100 % représente un cœur logique pleinement utilisé ; plusieurs cœurs peuvent produire plus de 100 %. Il s'agit d'une moyenne sur l'intervalle, pas d'un instantané de charge de tout le serveur.
- Le cache des mesures CPU reste uniquement en mémoire dans le contrôleur, séparément pour `opensim-ai-bridge.service` et chaque service `opensim-ai-bridge@<id>.service`.
- Le premier relevé, les compteurs indisponibles ou un bot arrêté donnent `—` ; une remise à zéro du compteur CPU après redémarrage ne crée pas de pourcentage négatif.
- L'écran conserve son actualisation automatique toutes les 10 secondes.

**Déploiement :** mettre à jour `controller/control.py` par le script d'installation multi-bots et le fichier Web PHP depuis le même artefact. Le script active `CPUAccounting=yes` et `MemoryAccounting=yes` pour les unités d'avatar à instances ainsi que via un drop-in pour l'ancienne unité BloodMoon AI. L'installation recharge systemd, **sans redémarrer les avatars existants**. Certaines valeurs peuvent rester indisponibles tant que les unités actives n'ont pas été redémarrées individuellement. Aucun redémarrage systématique n'est requis pour déployer la page Web.

## Suppression d'un bot secondaire — 23 novembre 2026

Dans **Mes avatars**, chaque avatar secondaire possède un panneau « Supprimer ce bot » ; le compte principal BloodMoon AI est protégé et n'affiche aucun bouton de suppression. L'admin doit saisir **exactement** le prénom et le nom de l'avatar puis cocher la confirmation. Le contrôleur authentifié exige également le nom et la confirmation : un appel direct ne peut contourner l'interface.

La suppression agit **uniquement sur OpenSim AI Bridge** : le compte ROBUST/OpenSimulator de l'avatar reste intact, de même que les autres bots et le programme .NET partagé. Le contrôleur :

1. Refuse les IDs inconnus ou l'ID principal `main`, et toute suppression pendant la maintenance générale.
2. Vérifie l'identité exacte de l'avatar dans son fichier de configuration privé.
3. Exécute `systemctl disable --now opensim-ai-bridge@<id>.service` puis vérifie que le service est arrêté avant toute destruction de données.
4. Retire seulement `/var/lib/opensim-ai-bridge/bots/<id>/` (configuration, secret, heartbeat), via un renommage dans le même répertoire avant effacement. Les services des autres avatars ne sont pas modifiés.
5. Revient à la sélection du bot principal après une suppression réussie.

La suppression des fichiers est **définitive** et ne peut pas être annulée automatiquement : pour reconnecter le même avatar comme bot, il faut le recréer et saisir à nouveau son mot de passe. En cas d'échec de l'arrêt systemd, les fichiers sont conservés ; en cas d'échec de leur effacement, un nettoyage manuel peut être nécessaire.

**À vérifier sur robust-vm après installation du correctif** : le formulaire apparaît pour Jolie Candy mais pas pour BloodMoon AI ; annuler/refuser une mauvaise confirmation ne modifie rien ; supprimer un bot secondaire de test désactive son unité et le fait disparaître de la liste, sans déconnecter le bot principal. Ne pas supprimer Jolie Candy si tu souhaites encore la garder comme bot.
