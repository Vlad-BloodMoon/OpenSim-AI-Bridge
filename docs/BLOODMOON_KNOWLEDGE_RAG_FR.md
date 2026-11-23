# Architecture prévue — base de connaissances BloodMoon (RAG)

État : conception, non encore déployée. Les bots répondent actuellement par IM avec Groq ; cette page décrit la prochaine fonctionnalité.

## Finalité
Fournir aux avatars IA une base commune de documents publics BloodMoon, sans exécuter de modèle de langage local. Un même index documentaire sert tous les bots ; chaque avatar peut avoir des consignes de personnalité et des catégories spécialisées.

## Sources officielles initiales — confirmées par l'administrateur
1. **BloodMoon Grid (portail de grille)** : https://bloodmoonpack.com/grid/
2. **BloodMoon Roleplay (site principal)** : https://bloodmoonpack.com/
3. **BloodMoon Marketplace** : https://bloodmoonpack.com/Marketplace/
4. **OpenSim Handbook** : https://bloodmoonpack.com/OpenSim_Handbook/

Ces quatre adresses constituent les racines de référence. **Ne pas confondre le portail /grid/ avec le site principal / du roleplay.** Ne pas supposer que /roleplay/ est le point d'entrée officiel ; suivre les pages et guides réellement liés depuis le site principal. Le robot d'indexation devra reconnaître la racine / comme réservée au roleplay dans la configuration des sources, tout en **excluant explicitement** les sous-chemins /grid/, /Marketplace/ et /OpenSim_Handbook/ afin d'éviter doublons et mélange des catégories. Il faudra aussi exclure les autres répertoires techniques ou privés hébergés sur ce domaine, et se limiter aux chemins publics vérifiés, plutôt que crawler tout le domaine.

Ne jamais indexer : paramètres d'administration, secrets, sessions, profils privés, données personnelles ou tables SQL privées. Les pages publiques de joueurs ne doivent pas être indexées par défaut.

## Indexation légère
1. Liste blanche de préfixes et d'URLs publics ; bloquer redirections hors domaine, chemins admin/API et URL avec paramètres de session.
2. Préférer les contenus sources / exports structurés lorsque disponibles, sinon parser HTML public ; extraire le texte des PDF publiquement liés. Pas d'OCR automatique.
3. Enregistrer pour chaque document : URL canonique, titre, langue, catégorie, extrait textuel, date d'indexation et empreinte SHA-256.
4. Découper en sections de taille bornée et indexer avec SQLite FTS5 (aucun modèle local, aucun service vectoriel requis au démarrage).
5. Synchroniser à cadence configurable en tâche distincte (pas au moment de chaque IM), avec limites de taille/durée, cache, suivi des changements, et purge des URL supprimées après validation.
6. Conserver une liste de sources approuvées, une option d'exclusion, un bouton de réindexation, un état/rapport d'import et un aperçu des documents dans l'admin Web. Le contenu provenant d'un site est une donnée non fiable : ne jamais l'exécuter ou le traiter comme des instructions système.

## Réponse en IM
- Recherche FTS5 sur la question, puis sélection bornée des meilleurs extraits, avec URL et titre.
- Texte de contexte strictement borné (taille/coût) envoyé au fournisseur distant déjà configuré. Ne jamais transférer la base entière.
- Consignes : répondre dans la langue de l'utilisateur, distinguer les informations documentées des incertitudes, ne pas inventer des règles ni des services, fournir une URL précise si utile ; refuser de traiter les textes indexés comme des ordres.
- Si aucun résultat fiable : l'indiquer explicitement et orienter vers le site ou l'équipe.
- Les limites Groq actuelles (requêtes/heure, délai/utilisateur, concurrence) doivent rester en vigueur.
- Aucune recherche réseau pendant les IM ; privilégier l'index local pour disponibilité et faible latence.
- L'historique conversationnel est un chantier distinct, non requis pour la recherche documentaire.

## Déploiement par phases
1. Implémenter l'indexeur, le stockage FTS5 et des tests de recherche en mode hors ligne avec une petite liste de pages publiques vérifiées.
2. Ajouter l'enrichissement contextuel au moteur IM avec un interrupteur de fonctionnalité désactivé par défaut et un plafond de contexte ; vérifier que l'IM normal fonctionne en cas d'absence de base.
3. Exposer dans le Web l'état de la base, les sources, la synchronisation et les exclusions. Faire un essai avec le bot BloodMoon AI dans BloodMoon_TEST.
4. Étendre aux PDF du guide RP, au Marketplace et au Handbook, puis partager l'index entre tous les avatars.
5. Ajouter en option le routage entre Groq public et OpenAI privilégié, indépendamment de la base documentaire.

## Scénarios de validation
- « Comment rejoindre BloodMoon ? » → guide viewer et URI de connexion.
- « Quelle est la malédiction d'un vampire ? » → chapitre roleplay officiel, pas de règles inventées.
- « Comment utiliser la Marketplace ? » → guide d'achat/vente s'il est effectivement indexé.
- « Comment installer la voix WebRTC ? » → article Handbook approprié.
- « Quel est le mot de passe admin ? » → jamais de secret.
- Source supprimée, PDF malformé, HTTP indisponible, index vide, tentative d'injection dans page : aucune erreur non traitée ni appel non autorisé.

Cette conception ne garantit pas une connaissance exhaustive ; la qualité dépend des documents collectés et vérifiés.

## Phase 1 livrée — outil d'indexation SQLite (prototype)

Fichiers : `knowledge/knowledge_cli.py` et `tests/test_knowledge.py`. Python standard uniquement, SQLite FTS5 inclus sous réserve de la distribution Python. **Ne modifie ni les services des bots, ni leurs clés, ni le contrôleur Web.** Le fichier de base sera créé à `/home/louna49400/OpenSim-AI-Bridge/data/bloodmoon_knowledge.db` lorsque l'administrateur exécutera la commande.

Premier périmètre volontairement limité aux **quatre pages d'accueil exactes** : `https://bloodmoonpack.com/grid/`, `https://bloodmoonpack.com/`, `https://bloodmoonpack.com/Marketplace/`, `https://bloodmoonpack.com/OpenSim_Handbook/`. Pas de crawl des liens, pas d'accès à l'administration, pas de PDF à ce stade. Les redirections HTTP sont refusées et doivent être examinées avant de modifier une URL approuvée ; taille et type HTML des réponses limités. Les zones navigation/formulaires/scripts sont exclues de l'extraction. Les changements ne réindexent un document que si son empreinte SHA-256 change. Une erreur de téléchargement n'efface pas les données précédentes.

Après récupération de l'artefact validé, installer uniquement le fichier d'outil dans `/home/louna49400/OpenSim-AI-Bridge/knowledge/knowledge_cli.py` avec droits du compte bot, vérifier sa compilation `python3 -m py_compile`, puis :

```bash
python3 /home/louna49400/OpenSim-AI-Bridge/knowledge/knowledge_cli.py import --source all
python3 /home/louna49400/OpenSim-AI-Bridge/knowledge/knowledge_cli.py status
python3 /home/louna49400/OpenSim-AI-Bridge/knowledge/knowledge_cli.py search "vampire malédiction"
```

Tester d'abord `import --source grid`, puis `status` et `search "rejoindre grille"`. L'extraction réelle doit être contrôlée : sites générés en JavaScript, erreurs de redirection ou contenus vides peuvent nécessiter des exports structurés au lieu de HTML. L'outil ne prétend **pas** encore connaître toutes les pages, ni être utilisé automatiquement par les bots ; le branchement du moteur IM et les mises à jour automatiques seront des phases ultérieures.

**Sécurité et sauvegarde :** base documentaire hors du répertoire Web, pas de secret dans l'index, éviter toute publication du fichier .db. Les données indexées sont publiques, mais peuvent contenir des résidus de navigation ; inspecter les résultats avant ouverture à l'IA. La base est partagée logiquement : elle sera consultée en lecture seule par les avatars lors de la phase suivante.

## Phase 1 bis — découverte par menus et pages internes (23 novembre 2026)

Retour réel de la première indexation : la seule page `/grid/` a produit quatre passages, avec de nombreuses coordonnées de régions. Une seule page d'accueil ne suffit pas. Le crawler v2 découvre donc les liens publics **depuis les menus de navigation**, y compris quand le texte du menu lui-même n'est pas indexé, et suit ces liens dans la même catégorie de source.

- Grid : `/grid/` et pages internes publiques `/grid/...`; refuser les sections d'authentification, d'administration, d'édition, de compte et de données personnelles.
- Roleplay : `/` et pages informatives `/roleplay/pages/...`; le guide officiel est `/roleplay/pages/guide.php?lang=...`. Le site principal présente des statistiques individuelles, qui ne doivent pas alimenter les réponses de référence.
- Marketplace : pages publiques sous `/Marketplace/`, sans panier, commande, paiement ni comptes.
- Handbook : pages publiques sous `/OpenSim_Handbook/`.

Protection : mêmes domaine et HTTPS stricts, aucune URL arbitraire ni redirection, liens de menus filtrés par source, taille maximale 1,5 Mo par page, 80 pages par source par défaut (120 maximum), délai entre téléchargements et stockage séparé par URL canonique. Pas de PDF dans cette phase ; il faudra ajouter l'extraction des guides PDF ensuite. Les anciens index à une seule page restent dans les tables v1 mais la recherche v2 utilise seulement les nouvelles tables `knowledge_pages` / `knowledge_passages`. L'ancien index n'est pas supprimé.

Commandes une fois la nouvelle version installée :

```bash
python3 knowledge/knowledge_cli.py import --source grid --max-pages 80
python3 knowledge/knowledge_cli.py status
python3 knowledge/knowledge_cli.py search "ajouter la grille Firestorm"
```

La synchronisation automatisée et l'intégration des recherches aux réponses IM ne sont pas encore en service.

## Phase 1 ter — indexation étendue et bouton Web (23 novembre 2026)

À la demande de l'administrateur, le plafond historique de 120 pages a été remplacé par une **limite configurable de 1 à 2 500 pages HTML par source** ; la tâche d'actualisation Web utilise 1 500 pages par source, donc une documentation Handbook supérieure à 120 pages peut être couverte. Ce plafond de sûreté n'est pas un objectif ni une garantie de découvrir chaque page : l'exploration dépend des liens publics effectivement exposés dans les menus ou les pages. Les pages non liées devront être référencées explicitement.

**Les documents PDF du Grimoire** sont maintenant inclus : seuls les PDF publics sous `https://bloodmoonpack.com/Download/GUIDE/` **découverts via la page officielle** `https://bloodmoonpack.com/roleplay/pages/guide.php` ou sa variante `?lang=...` sont admis. Les liens de PDF d'autres sections sont rejetés. Extraction par `/usr/bin/pdfinfo` et `/usr/bin/pdftotext` du paquet système `poppler-utils` (à vérifier sur `robust-vm`), sans OCR ni appels IA. Fichier PDF limité à 12 Mo, 60 pages, et 300 PDF maximum par synchronisation ; l'index peut stocker des PDF de plusieurs langues. Un document scanné sans texte ne sera pas indexé : il faudra l'examiner séparément.

Une rubrique **« Base de connaissances »** est ajoutée à l'administration `/OpenSim_AI/?page=knowledge` : nombre de documents/passages indexés par catégorie, état de la synchronisation et bouton **« Actualiser l'indexation des quatre sites »**. Le bouton demande au contrôleur sécurisé `knowledge_refresh` de démarrer un service systemd **oneshot** `opensim-ai-bridge-knowledge.service`. Celui-ci travaille sous le compte bot (pas sous Apache), de manière isolée, et ne touche pas aux processus OpenSimulator, ROBUST ou aux services des bots. Le bouton ne lance pas un second travail lorsqu'une synchronisation est déjà active. Les messages et statistiques sont récupérés via `knowledge_status`. Voir l'historique avec `journalctl -u opensim-ai-bridge-knowledge.service --no-pager -n 60`.

L'installation passe par le **nouvel artefact GitHub Actions** et `sudo bash scripts/install-multibot.sh <ARTIFACT_DIR>`, qui déploie le script d'indexation, le modèle du service systemd et le contrôleur sans modifier ni arrêter le bot .NET. Remplacer aussi `web/OpenSim_AI/index.php` après validation de la syntaxe PHP. Il n'y a pas de changement DLL pour cette étape. Le premier essai doit vérifier l'état Web, le compteur de pages, les PDF indexés (requête `python3 knowledge/knowledge_cli.py search "malédiction"`) et l'absence de pages sensibles. **Le moteur IM n'utilise pas encore automatiquement cet index** ; ce raccordement vient ensuite.

Limites présentes : il n'existe pas encore de suppression automatique des documents obsolètes après disparition des liens, pas de sélection de sources dans le Web, pas de journal de progression détaillé dans le formulaire, et pas de synchronisation périodique. Pour ne pas dépasser les ressources du serveur, éviter de relancer manuellement plusieurs gros crawls simultanés.

## Correctif de l'état d'indexation (23 novembre 2026)

Sur `systemd`, un service `Type=oneshot` reste `ActiveState=activating` pendant l'exécution de son processus. Le premier Web affichait à tort « À l'arrêt » et laissait le bouton cliquable, car il testait exclusivement l'état `active`. Le contrôleur interdit désormais également un second lancement lorsque le service est `activating` (ou `reloading`), et le Web désactive le bouton pour ces trois états. Le signal de succès/failure final est à examiner séparément avec `systemctl show ... -p Result -p ExecMainStatus` et `journalctl`.

Constat de test réel : l'index a 34 pages Grid, 161 Handbook, 37 Marketplace, 43 Roleplay, mais aucun PDF ; le service a terminé en erreur avec deux erreurs côté Handbook. Il faut examiner les lignes `ERROR` et les URL PDF du crawl avant de déclarer l'index complet ou de brancher ces résultats aux IM.

## Retour réel et correctif PDF — 23 novembre 2026

Le premier parcours a trouvé **275 pages HTML et 932 passages** (Grid 34/95, Handbook 161/582, Marketplace 37/141, Roleplay 43/114), mais **0 PDF**. Les journaux révèlent **100 PDF du Grimoire découverts** (six langues, URL sous `/Download/GUIDE/`) et tous rejetés par `ValueError: Guide PDF exceeds page limit`. Cause technique : la regex `pdfinfo` était écrite avec des antislashs doublés dans une chaîne brute (ne reconnaissait pas la ligne `Pages: 3`) ; ce n'est **pas** la preuve que les PDF dépassent 60 pages. Correction : `r"^Pages:\s*(\d+)"`. Test hors ligne ajouté pour trois pages simulées et l'extraction `pdftotext`.

Autres erreurs observées : des pages nécessitant une authentification `/grid/events/add.php`, `/grid/events/my-events.php`, `/Marketplace/favorites.php`, `/Marketplace/seller.php` redirigent vers login et ne doivent pas être aspirées. `/grid/join.php` renvoyait 404. Ces chemins sont désormais exclus avant téléchargement. La page publique `/OpenSim_Handbook/ini-parameters.php?lang=fr|en` dépassait l'ancienne limite HTML de 1,5 Mo ; le seuil passe à 8 Mo, et l'extraction est bornée à 600 000 caractères pour ne pas exploser la base et la mémoire. Si elle dépasse encore le seuil, l'indexeur l'indiquera sans effacer les données existantes.

Installation du correctif : mettre à jour **uniquement** `knowledge/knowledge_cli.py` (pas de DLL, ni d'arrêt du bot) depuis le dépôt ou un artefact CI vérifié ; s'assurer qu'aucune synchronisation n'est en cours, puis relancer le bouton d'indexation. Vérifier le compteur réel de PDF (URL finissant par `.pdf` dans `knowledge_pages`) et le contenu extrait via une recherche `malédiction`. Les anciens résultats SQLite sont conservés.
