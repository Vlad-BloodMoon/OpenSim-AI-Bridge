# OpenSim AI Bridge — Roadmap / Feuille de route

**Révision du 24 novembre 2026.** Ce document donne l'état actuel du dépôt et distingue **code livré**, **tests hors ligne**, **tests réels sur BloodMoon** et **travaux à réaliser**. Les documents de conception initiaux restent archivés dans `CAHIER_DES_CHARGES_FR.md` et `REQUIREMENTS_EN.md`.

## Implemented / Développé

- [x] Client autonome OpenSimulator via .NET 8 et LibreMetaverse, sans viewer graphique.
- [x] Connexion de l'avatar et échange IM élémentaire testés sur BloodMoon, OpenSimulator 0.9.3.1.
- [x] Chat local, mécanismes de reconnexion, réponse IM en plusieurs morceaux et protection contre les requêtes simultanées : **implémentés**, pas tous validés sur une longue période.
- [x] Administration HTTPS/PHP avec session authentifiée, CSRF, contrôleur Python par socket Unix, commandes systemd et maintenance générale.
- [x] Infrastructure multi-avatar, configurations et mots de passe distincts ; les scénarios de second avatar ne sont pas tous validés dans la grille.
- [x] Modèles IA distants Groq, OpenRouter, Gemini ; profils activables, vérification administrateur, chaîne de secours en mode auto et mode IA unique.
- [x] Limitation du nombre de tentatives par fournisseur et par heure partagée entre avatars (SQLite), refroidissement par profil en mémoire de processus ; **pas de garantie sur les quotas de tokens du fournisseur ou sur la facturation**.
- [x] Recherche documentaire FTS5 SQLite à partir des sites publics BloodMoon, de PDF et des fiches privées `.txt`, avec réindexation périodique.
- [x] Traduction Azure des questions **pour la recherche documentaire**, via un PHP `ai-translate.php` distinct des services `translate.php` et `web-translate.php` existants.
- [x] Traduction Azure réellement testée depuis `robust-vm` : détection EN/ES/DE et recherche retrouvant la fiche Freeland ; réponse finale de bout en bout dans le viewer **encore à tester**.
- [x] Administration du vocabulaire de recherche : ajout/édition/suppression de termes, variantes, mots-clés et catégorie documentaire via l'interface protégée ; chargement à chaque recherche sans redémarrage.
- [x] Accueil de proximité en **chat local canal 0** avec nom classique OpenSimulator, rayon et délai indépendants par bot, protection anti-répétition, sans coût IA. **Confirmé en jeu sur BloodMoon**, y compris dans une grande région (`ObjectsAvatars`, positions complètes).
- [x] Orientation optionnelle du corps du bot vers le résident au moment de l'accueil (`Movement.TurnToward`) **confirmée en jeu avec Firestorm sur BloodMoon**. Aucun déplacement autonome n'est implémenté.

## Production validations still required / À valider réellement

- [ ] Faire une conversation IM complète dans Firestorm avec questions FR/EN/ES/DE/IT/PT et réponses sourcées.
- [ ] Provoquer un 429 contrôlé, observer le passage au modèle suivant, puis le retour après refroidissement ; vérifier les quotas partagés lors de connexions simultanées.
- [ ] Tester plusieurs avatars connectés simultanément, leurs configurations indépendantes, leur arrêt/reprise et le mode Firestorm.
- [ ] Tester l'accueil dans d'autres régions et viewers, sur un avatar assis ou animé, et lorsque plusieurs visiteurs arrivent simultanément ; vérifier la coordination entre bots proches.
- [ ] Tester les cycles redémarrage machine, déconnexion réseau, retour réseau et disparition/recréation des services.
- [ ] Déployer et vérifier les droits et la confidentialité sur une grille de test distincte de BloodMoon.
- [ ] Vérifier les politiques de données personnelles, de journalisation et de conservation dans le déploiement réel.
- [ ] Faire une revue de sécurité avant distribution publique générale.

## Planned, not implemented / Prévu, pas encore livré

- [ ] Moteur FAQ entièrement éditable sans IA (règles, questions, réponses multilingues, aperçu, historique).
- [ ] File des questions non reconnues, modération, audit et statistiques de coûts réels/tokens.
- [ ] Adaptateurs ROBUST/Marketplace contrôlés et opérations limitées par outils.
- [ ] Préférences persistantes de langue par résident ; traduction conversationnelle entre résidents.
- [ ] Animations déclenchées, **navigation/déplacement autonome**, téléportation, WebRTC voice, Hypergrid travel (la simple rotation ponctuelle vers un visiteur est déjà livrée).
- [ ] Autorisations multi-rôles Web et fonctions d'administration avancées.
- [ ] Licence publique explicite après audit des dépendances et de leurs obligations.

## Project quality / Qualité de la distribution

- [x] GitHub Actions compile .NET 8, valide PHP/Bash/Python et exécute des tests comportementaux hors grille.
- [x] Configuration d'exemple simplifiée pour refléter les options réellement prises en charge.
- [x] README et architecture actualisés, séparation du réalisé et du prévu.
- [ ] Mettre à disposition un installateur général multi-grilles avec restauration, sauvegardes et paramètres de chemins documentés.
- [ ] Ajouter des tests d'intégration sécurisés sur une grille OpenSimulator de qualification, sans dépendance à l'infrastructure BloodMoon.

**Important :** un résultat CI vert n'établit ni compatibilité universelle OpenSimulator ni sûreté des dépenses auprès des fournisseurs IA. Les offres et modèles disponibles peuvent changer indépendamment du code.
