# IA distante pour les avatars — première version expérimentale (23 novembre 2026)

> **Guide du pilote IA initial (23/11/2026).** Les instructions ci-dessous précèdent l'administration **multi-fournisseurs** et peuvent décrire l'ancien mode par avatar. Pour la configuration actuelle des modèles et des clés séparées, consulter [Multi-fournisseurs](MULTI_PROVIDER_ROUTING_FR.md), [README](../README.md) et [Architecture](ARCHITECTURE.md). Ne pas remplacer la configuration multi-IA de production par l'ancien formulaire.

## Objectif

Faire de **BloodMoon AI** un véritable assistant IA répondant aux **messages privés (IM)** dans OpenSimulator, sans installer de modèle local (pas d'Ollama). Chaque bot possède une configuration IA et une clé séparées. L'IA est **désactivée par défaut** ; elle ne s'active qu'après configuration explicite.

## Fournisseurs

Un adaptateur HTTP compatible « Chat Completions » est implémenté pour trois fournisseurs disposant de clés API séparées :

- **OpenAI** : `https://api.openai.com/v1/chat/completions` ; exemple d'identifiant de modèle `gpt-4.1-mini`.
- **Groq** : `https://api.groq.com/openai/v1/chat/completions` ; choisir un identifiant de modèle réellement proposé par le compte Groq.
- **OpenRouter** : `https://openrouter.ai/api/v1/chat/completions` ; choisir un identifiant de modèle actif du fournisseur. Certains modèles peuvent être gratuits sous conditions, sans garantie.

Ces adresses HTTPS sont **fixées dans le code**, et non éditables depuis le Web, pour éviter toute redirection vers un serveur arbitraire. Le compte ChatGPT et son abonnement n'attribuent pas automatiquement de crédits API. Une requête API peut être payante : vérifier les conditions et facturations du fournisseur.

## Interface Web

Dans `/OpenSim_AI/?page=modules&bot=...` :
1. Choisir l'avatar.
2. Choisir un fournisseur et un identifiant de modèle.
3. Saisir la clé API **une fois** (champ masqué). Une clé existante reste en place si le champ est laissé vide.
4. Saisir la liste d'UUID OpenSimulator autorisés, **un par ligne**, maximum 12.
5. Paramétrer la limite des demandes par heure (1–120) et l'intervalle minimum (5–3600 secondes) par utilisateur, puis les consignes système.
6. Cocher l'activation IA, sauvegarder et redémarrer **uniquement le service de cet avatar**.

La clé API n'est jamais renvoyée vers le navigateur. Elle se trouve dans un fichier privé `ai-api-key.txt` à côté du `appsettings.json` du bot, mode 0600. Pour BloodMoon AI, c'est `/home/louna49400/OpenSim-AI-Bridge/ai-api-key.txt`. Pour un bot secondaire, c'est `/var/lib/opensim-ai-bridge/bots/<id>/ai-api-key.txt`. Le lanceur `scripts/start-bot.sh` charge ce fichier dans `OSAI_AI_API_KEY` uniquement à l'exécution ; aucune valeur secrète ne doit apparaître dans GitHub, les logs ou le Web root.

## Comportement et limites

- **Pas d'IA sans activation, clé valide et UUID dans la liste d'autorisation.**
- Les IM directs reconnus comme `MessageFromAgent` peuvent déclencher une réponse IA ; les IM de groupe, invitations, inventaire et conversations publiques sont exclus.
- Les commandes gratuites `ping`, `help`/`aide`, `where`/`position` restent disponibles et n'appellent pas de fournisseur.
- L'historique des conversations n'est **pas** conservé dans ce premier prototype. Chaque demande contient seulement les consignes système et le texte de l'IM reçu.
- Limite de 1000 caractères entrants ; réponse tronquée à 600 caractères ; maximum 250 tokens de sortie ; délai HTTP de 20 secondes ; une requête en cours par bot.
- Compteur de requêtes par heure et délai par UUID **en mémoire uniquement**. Ces limites sont remises à zéro après redémarrage : **elles ne constituent pas un plafond budgétaire fiable ou persistant**. Mettre des limites de facturation directement chez le fournisseur.
- Les messages d'erreur ne réaffichent pas le corps HTTP, les jetons secrets ni les conversations privées.
- En cas d'indisponibilité du fournisseur, une réponse courte signale la panne, sans boucle de répétition.

## Déploiement et validation

1. Confirmer une compilation GitHub Actions réussie, notamment `--verify-ai-safety`.
2. Télécharger l'archive dans `OpenSim-AI-Workspace/`, puis installer le contrôleur et le Web PHP. Le script `install-multibot.sh` déploie aussi le lanceur `scripts/start-bot.sh` avec lecture de la clé de chaque bot.
3. Avant de remplacer la **DLL commune**, utiliser l'onglet **Maintenance générale** pour arrêter et verrouiller tous les bots. Sauvegarder l'ancienne DLL, puis copier `OpenSimAiBridge.Bot.dll` et ses nouvelles dépendances si nécessaires. Ensuite lever le verrou.
4. Dans Modules IA, configurer **un seul bot de test et un seul UUID autorisé** et laisser l'IA désactivée pour les autres.
5. Redémarrer ce bot et vérifier qu'un IM non-commandé de cet UUID reçoit une réponse IA. Vérifier qu'un UUID non autorisé ne déclenche **aucun** appel distant. Tester les limites de fréquence.
6. Tester l'arrêt/reprise par bot et le passage Firestorm, puis relever RAM, CPU et logs.

**Statut** : code expérimental, pas encore validé avec une vraie clé/fournisseur sur BloodMoon. Ne pas annoncer l'IA en production avant ce test. Les fonctionnalités futures comprennent fournisseur gratuit pour le public, facturation et quotas persistants, modération, RAG/base de connaissances et traduction.

## Sélecteur de modèles dans Modules IA (23 novembre 2026)

Le formulaire Web propose désormais une liste déroulante dépendant du fournisseur (Groq, OpenAI, OpenRouter). Choisir un modèle renseigne le champ `Identifiant du modèle`, conservé comme saisie modifiable pour les modèles non listés ou récemment publiés. Changer de fournisseur propose son premier modèle ; ouvrir la page conserve un identifiant déjà enregistré même s'il n'est pas dans les suggestions. Aucun appel API n'est effectué pour remplir cette liste ; les droits d'accès et les catalogues restent ceux du fournisseur et de son compte. La modification ne touche ni au contrôleur ni à la DLL et s'installe en remplaçant uniquement `web/OpenSim_AI/index.php`.

### Correction du sélecteur vide (23 novembre 2026)

Le sélecteur pouvait rester vide parce que la politique Content-Security-Policy historique de la page interdisait tous les scripts. `index.php` emploie désormais un nonce CSP aléatoire par réponse HTML (`script-src 'nonce-...'`) sur son seul script de sélection, sans recourir à `unsafe-inline` pour JavaScript. La liste peut ainsi être initialisée sans élargir l'exécution d'autres scripts. Correction purement Web ; aucune modification des clés, UUID, réglages IA, service .NET ou contrôleur.

## Accès public aux IM Groq (23 novembre 2026)

Après validation d'une réponse IA réelle dans Firestorm, l'administration propose **« Autoriser tous les résidents à converser en IM »** sur la page Modules IA. Cette option enregistre `Ai.PublicAccess`, **désactivé par défaut** et disponible **uniquement avec le fournisseur Groq**. Un UUID autorisé reste accepté lorsque l'accès public est inactif. Avec l'accès public Groq actif, tout utilisateur, y compris un visiteur Hypergrid capable d'envoyer un IM, peut interroger le bot. Il s'agit d'un accès par IM privé avec l'avatar IA, **pas** d'une réponse automatique à tout le chat local ou de groupe.

Les garde-fous existants restent : compteur partagé `MaxRequestsPerHour` (1–120) par avatar, délai `MinSecondsBetweenRequests` (5–3600 s) par utilisateur, un seul appel IA simultané par avatar, requêtes limitées en taille. Les quotas sont remis à zéro au redémarrage du service et **ne constituent pas une limite financière garantie**. La clé Groq reste privée, jamais transmise au navigateur. Le panneau désactive la case d'accès public quand un autre fournisseur est sélectionné, et le contrôleur refuse toute tentative d'accès public avec OpenAI ou OpenRouter. Le moteur .NET vérifie également la restriction Groq. Les tests de sécurité hors ligne couvrent le mode public Groq et le refus du mode public OpenAI.

Déploiement : le changement concerne le Web, le contrôleur et **la DLL .NET**. Télécharger un nouvel artefact GitHub Actions validé, mettre à jour le Web et le contrôleur avec l'installateur multi-bot ; ensuite activer la maintenance générale pour arrêter les bots, sauvegarder et remplacer la DLL, terminer la maintenance, cocher l'accès public Groq, enregistrer et redémarrer uniquement l'avatar concerné. Ne pas interrompre ROBUST, Money ou les simulateurs.

**Évolution future distincte :** créer deux profils fournisseurs sur un même bot (Groq public, OpenAI avec UUID privilégiés et budgets séparés). Le présent changement n'implémente **pas** encore le routage simultané entre deux API.
