# Administration Web V0.2 — installation pilote BloodMoon

**État :** code disponible dans GitHub, **non encore déployé ni testé sur robust-vm**.
La V0.2 fournit un **tableau de bord sécurisé de contrôle du bot**, pas encore le moteur FAQ ou l'IA.

## Architecture

```text
https://bloodmoonpack.com/OpenSim_AI/
  └─ PHP 8.3, connexion administrateur + CSRF
       └─ Socket UNIX /run/opensim-ai-bridge-control/control.sock
            └─ Service opensim-ai-bridge-control.service (Python stdlib)
                 └─ commandes systemctl prédéfinies sur opensim-ai-bridge.service
```

Le socket accepte uniquement le **UID www-data** (vérifié par `SO_PEERCRED`) et six actions fixes :
`status`, `start`, `stop`, `restart`, `firestorm`, `resume`.
Aucun chemin, commande shell ou nom de service n'est accepté du navigateur.
Le contrôleur tourne sous root pour contacter systemd, avec confinement systemd ; le serveur Web **ne dispose pas de sudo**.

## Répertoires BloodMoon

- Bot existant : `/home/louna49400/OpenSim-AI-Bridge/`.
- Web : `/var/www/BloodMoon/OpenSim_AI/`.
- Mot de passe **Web distinct** de celui de l'avatar : hachage dans `/etc/opensim-ai-bridge/web-admin.php` (root:www-data, 0640), **hors du DocumentRoot**.
- Mot de passe de l'avatar : `bot-password.txt` déjà privé dans le dossier du bot. Ne jamais le copier vers le Web.
- Socket : `/run/opensim-ai-bridge-control/control.sock` (root:www-data, 0660), créé au démarrage du contrôleur.

`louna49400` appartient à `www-data` et doit continuer à pouvoir éditer les fichiers du site avec Notepad++. Préférer `louna49400:www-data` avec répertoires 2775 et PHP 0664. Ne **jamais** donner les permissions d'écriture `www-data` sur la configuration privée.

## Procédure manuelle, à faire pas à pas

1. **Sauvegarder l'installation actuelle.** Vérifier que le service bot existant fonctionne et éviter toute session Firestorm simultanée.
2. Télécharger l'artifact GitHub Actions `OpenSim-AI-Bridge-v0.2-preview-linux-x64` dans un répertoire temporaire.
3. Installer `controller/control.py` **dans `/usr/local/libexec/opensim-ai-bridge/control.py`**, propriétaire `root:root`, mode `0644`, répertoires parents non modifiables par `louna49400` ou `www-data`. **Ne jamais exécuter comme root une copie du contrôleur depuis un dossier utilisateur ou Web modifiable.** Ne pas toucher aux fichiers privés ni aux DLL validées.
4. Générer l'unité de contrôle en remplaçant `@INSTALL_DIR@` par `/home/louna49400/OpenSim-AI-Bridge` dans `deploy/systemd/opensim-ai-bridge-control.service.example`, puis installer dans `/etc/systemd/system/opensim-ai-bridge-control.service`.
5. `sudo systemctl daemon-reload`, puis `sudo systemctl start opensim-ai-bridge-control.service`. **Ne pas activer l'autostart immédiatement.**
6. Créer le mot de passe administrateur Web en exécutant **interactivement** `bash scripts/setup-web-admin.sh`. Il faut un mot de passe fort de 14 caractères minimum, distinct de celui de l'avatar.
7. Créer `/var/www/BloodMoon/OpenSim_AI` puis y copier **uniquement** `web/OpenSim_AI/index.php` et `.htaccess`. Régler propriétaire `louna49400`, groupe `www-data`, répertoire 2775, fichiers 0664.
8. Vérifier en CLI : `php -l /var/www/BloodMoon/OpenSim_AI/index.php` ; `python3 -m py_compile /usr/local/libexec/opensim-ai-bridge/control.py`.
9. Ouvrir en HTTPS `https://bloodmoonpack.com/OpenSim_AI/`, se connecter et tester d'abord le **statut**, ensuite une action à la fois, puis le verrou Firestorm.

**N'exécute pas toutes les étapes sans contrôle :** on validera chaque étape ensemble sur le serveur.

## Paramètres Apache/PHP

- Application réservée à HTTPS ; accès HTTP rejeté côté PHP.
- Authentification par mot de passe haché PHP (`password_hash`, `password_verify`), sessions `Secure`, `HttpOnly`, `SameSite=Strict`, rotation d'ID, expiration par inactivité.
- Jetons CSRF exigés pour toutes les actions POST ; aucune action sur GET.
- Tentatives de connexion freinées par session : **ce n'est pas une défense réseau globale**. Pour une exposition publique durable, ajouter un filtrage Apache/IP, mod_security ou fail2ban et idéalement une seconde authentification.
- La page affiche uniquement l'état `systemd` : `active` n'implique pas que l'avatar est déjà connecté à la grille.
- Le serveur PHP/Apache doit réellement utiliser `www-data` pour l'accès au socket (la présence des modules `php_module` et `proxy_fcgi` ne suffit pas à identifier le worker réellement utilisé).
- `mod_auth`, SSO ou authentification 2FA existante pourront être intégrés ultérieurement ; ne pas présumer qu'ils sont déjà branchés.

## Fonctionnalités et limitations

| Fonction | Statut |
| --- | --- |
| Connexion administrateur PHP | Implémentée, tests de déploiement à faire |
| Démarrer, arrêter, redémarrer | Implémenté, tests Web à faire |
| Mode Firestorm persistant | Implémenté via le verrou existant |
| Bouton reprise avec confirmation Firestorm fermé | Implémenté |
| État systemd + mode maintenance | Implémenté |
| Indicateur réel de présence / région / coordonnées | À venir (endpoint de santé côté bot) |
| FAQ multilingue, traduction, IA distante | À venir |

## Sécurité des déploiements

Le contrôleur est un service **privilégié**. Il doit conserver son code hors du répertoire Web, en lecture réservée, et être lancé uniquement après revue de sa configuration. Le socket autorise l'identité système `www-data` ; si d'autres applications Web compromises s'exécutent sous ce même UID, elles pourraient solliciter ces commandes fixes. Envisager un pool PHP-FPM distinct et une identité Unix dédiée pour isoler complètement l'interface.

Ne pas mettre les secrets, fichiers `/etc` ni le verrou de maintenance sur GitHub.

L'interface peut être ouverte au départ avec un filtrage IP Apache en plus du mot de passe Web, particulièrement pendant les essais.

## Correction sécurité du 23 novembre 2026

L'unité de contrôle exécute désormais le code Python depuis `/usr/local/libexec/opensim-ai-bridge/control.py`, sous propriété `root:root` et répertoire parent non modifiable par les utilisateurs ordinaires. Une unité privilégiée ne doit **jamais** charger son code Python depuis le répertoire de travail `louna49400` susceptible d'être modifié via SFTP.
