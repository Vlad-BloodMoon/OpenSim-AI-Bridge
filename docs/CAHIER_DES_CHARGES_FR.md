# Cahier des charges — OpenSim AI Bridge

**Version :** 0.1 (spécification initiale) — 20 novembre 2026  
**État :** projet en conception ; les fonctionnalités ci-dessous ne sont pas encore implémentées.

## 1. Vision et objectifs

Créer une plateforme open source, modulaire et réutilisable, permettant à un avatar **réellement connecté** à une grille OpenSimulator de dialoguer, d'aider les visiteurs, d'interagir avec les outils de grille et, à terme, de se déplacer et d'utiliser la voix.

BloodMoon est l'environnement pilote ; aucune adresse, compte, clé ou schéma privé ne doit être indispensable à l'installation sur une autre grille.

L'objectif est ambitieux, mais livré par jalons testables. Le premier résultat n'est **pas** une IA autonome : c'est un avatar stable qui se connecte sans viewer et répond à un IM.

## 2. Décisions validées

1. Client avatar **headless .NET 8 / LibreMetaverse**, sous réserve d'essais sur OpenSimulator 0.9.3.1.
2. **Aucun modèle de langage local** : aucune installation Ollama, aucune inférence IA consommant CPU/GPU serveur.
3. Accès IA via fournisseur **distant**, OpenAI en priorité, pour les seuls UUID autorisés.
4. Abonnement ChatGPT ≠ crédits API : facturation distincte, avec quotas, journal d'usage et coupure côté application.
5. Un **moteur gratuit de réponses** éditable dans l'administration Web fonctionne sans appel à l'API IA.
6. Fournisseur de traduction HTTP configurable ; adaptateur BloodMoon Translator envisagé.
7. Interopérabilité ROBUST et services de grille via interfaces restreintes, en lecture seule par défaut.
8. Le projet public ne doit contenir aucun secret, identifiant privé ni accès d'administration réel.

## 3. Publics et permissions

| Profil | Par défaut | API IA |
| --- | --- | --- |
| Visiteur | Accueil, FAQ, destinations et réponses publiques prédéfinies | Non |
| Résident autorisé | Fonctionnalités accordées explicitement par UUID | Sur autorisation et quota |
| Administrateur autorisé | Diagnostic, tableau de bord et commandes définies | Oui selon politique |
| Super-administrateur Web | Gestion des comptes et des accès, secrets gérés hors interface de contenu | Selon politiques |

L'identité de l'interlocuteur repose sur un UUID vérifié par le connecteur de grille, jamais sur le nom affiché ou une affirmation dans le texte. Une autorisation d'usage IA n'implique pas une autorisation d'exécuter des actions de grille.

## 4. Avatar passerelle

- Connexion avec un compte dédié sur le service de login configuré, sans Firestorm.
- État de session, health check, coordonnées, région, événements de connexion et présence affichables en Web.
- Lecture et émission du chat local et des IM ; filtrage anti-boucle et anti-spam.
- Reconnexion avec backoff, gestion des déconnexions, prévention des connexions doublons.
- Réponses découpées selon les limites du protocole ; gestion des conversations simultanées.
- Respect des limites de fréquence, journalisation sans données sensibles par défaut.
- Déplacements, téléportations, animation et interactions : ajout progressif, après tests.

## 5. Moteur de réponses gratuites

Géré sans redeployer ni redémarrer : création, édition, suppression logique, activation, désactivation, prévisualisation et test.

Chaque fiche peut définir : identifiant, catégorie, déclencheurs et variantes, langue, réponse, priorité, contexte (local/IM), statut, dates et propriétaire de l'édition. Détection de correspondance explicable : exact, variantes normalisées, puis règles configurées. Pas de réponse hasardeuse sur simple mot commun.

Fonctions à prévoir :
- variables dynamiques **autorisées** (nom du monde, région, liens, événements, etc.) ;
- réponses en plusieurs langues et cache de traduction ;
- messages adaptés au canal et aux limites du chat ;
- destination/TP proposés uniquement via des actions autorisées ;
- questions non reconnues dans une file de modération (« questions à traiter »), anonymisées/minimisées ;
- import/export JSON, historique de modification, catégories et statistiques agrégées ;
- désactivation possible de toute journalisation de contenu.

Si aucune réponse fiable : annoncer l'absence d'information, sans inventer. Aucun appel payant si l'utilisateur n'est pas éligible.

## 6. Intelligence artificielle distante

- Fournisseur OpenAI via couche d'abstraction remplaçable par d'autres **API distantes**.
- Accès sur liste d'UUID autorisés ; un administrateur choisit les modèles, quotas, limites de tokens, délais et contextes.
- Distinguer réponses publiques, contexte privé, contenu du wiki et mémoire personnelle.
- Isolation des discussions par utilisateur/session et conservation configurable avec consentement adapté.
- Suivi d'usage : requêtes, tokens, coûts estimés, échecs, plafonds par utilisateur/jour/mois.
- Bloquer côté application lorsqu'un plafond interne est atteint ; configurer séparément les contrôles de facturation du fournisseur.
- Aucun accès brut à SQL, shell, HTTP arbitraire ou secrets par le moteur de langage.
- Actions via outils typés, liste blanche, permission côté serveur, confirmation humaine pour opérations sensibles.
- Résilience : moteur gratuit disponible quand l'IA distante est désactivée ou indisponible.

## 7. Traduction

- Interface `ITranslationProvider` indépendante du moteur IA, avec langue source/target, timeout, retries bornés et traitement des erreurs.
- Intégration pilote envisageable : `https://bloodmoonpack.com/translator/translate.php`.
- **À vérifier dans le code existant** : structure JSON, authentification, détection de langue, coûts/quotas, codes d'erreur, politique de données.
- Langue préférée par UUID (avec choix explicite), langue par défaut et langues disponibles.
- Cache par hash de contenu + langue + version ; pas de fuite de messages privés dans les clés de cache exposées.
- Possibilité de fournir des traductions manuelles stables pour les réponses fréquentes.
- Traduction entre résidents : fonctionnalité optionnelle, explicite, avec consentement, distincte du bot.

## 8. Administration Web

Interface responsive sécurisée ; vues prévues :
- état de chaque avatar, grille, région, coordonnées, connexions et erreurs ;
- carte/liste des régions et commandes autorisées (ex. revenir au point de départ) ;
- éditeur FAQ, test de règles, langues, catégories, queue des questions non reconnues ;
- autorisations par UUID, rôles Web, exclusions et quotas ;
- fournisseurs IA et traduction, configuration sans affichage de secrets ;
- budget et consommation, métriques, logs techniques, audit des actions ;
- paramètres d'intégration et état des services ROBUST.

Toutes les routes d'administration exigent authentification, contrôle serveur, protections CSRF si sessions cookies, rate limiting et HTTPS. Ne jamais faire confiance aux seuls contrôles de l'interface.

## 9. Intégration ROBUST et grille

Les opérations de **lecture** sont privilégiées : régions, services, présence, informations non sensibles. Les accès se font par interfaces contrôlées et comptes à privilèges minimaux ; utiliser les services OpenSimulator lorsqu'ils conviennent.

La position de l'avatar doit idéalement venir du client connecté ; une entrée `GridUser` n'est pas une preuve suffisante de présence instantanée. Le schéma et les modules peuvent varier d'une grille à l'autre.

Le Marketplace BloodMoon peut déjà envoyer des IM Web vers des avatars : analyser le mécanisme avant toute réutilisation. Les connecteurs BloodMoon restent optionnels et isolés du noyau open source.

Interdictions : requêtes SQL écrites par l'IA, modification directe des tables en fonction d'une conversation, accès administrateur général au système, commandes système non validées.

## 10. API Web (contrat indicatif, NON implémenté)

```text
GET  /api/health
GET  /api/bots
GET  /api/bots/{id}/status
GET  /api/bots/{id}/location
POST /api/bots/{id}/send-im
POST /api/bots/{id}/teleport
GET  /api/answers
POST /api/answers
GET  /api/unanswered
GET  /api/permissions
GET  /api/usage
GET  /api/grid/regions
GET  /api/grid/users/{uuid}/presence
```

Versions, authentification et formats de réponse seront définis avant implémentation. `send-im` et `teleport` nécessitent droits spécifiques et traces d'audit.

## 11. Exigences non fonctionnelles

- Faible consommation sur l'hôte : pas de modèle local, processus .NET léger, files bornées, caches contrôlés.
- Déploiement Linux Ubuntu 24.04 / .NET 8 pour les pilotes, sans présumer du support universel.
- Services séparables, redémarrage autonome, gestion des secrets via environnement/coffre.
- Tests unitaires pour les règles, permissions, budgets ; tests d'intégration sur grille isolée.
- Compatibilité Web locale et HTTPS derrière reverse proxy.
- Protection vie privée : minimisation, opt-in pour mémoire, purge/export, politiques de rétention.
- Documentation FR/EN pour installation, sécurité, dépannage et contribution.
- Inventaire et vérification des licences tierces avant fixation d'une licence de distribution.

## 12. Feuille de route et critères d'acceptation

**V0.1 — Avatar:** login depuis service headless, présence visible dans Firestorm, IM aller/retour, réponse statique, reconnect, position reportée. Aucune IA requise.

**V0.2 — Administration & FAQ:** dashboard HTTPS, rôles, éditeur de réponses persistantes, variantes de questions, réponses sans API IA, diagnostics et file de questions non reconnues.

**V0.3 — Traduction & API distante:** fournisseur de traduction confirmé par tests, gestion des langues, autorisations UUID, OpenAI réservé aux rôles, quotas et coupure applicative.

**V0.4 — Grille & connaissances:** connecteur de lecture ROBUST, wiki/documentation optionnels, mémoire avec règles de confidentialité, outils d'administration strictement contrôlés.

**V0.5+ — Vie du monde:** déplacements, animations, navigation, multi-avatars, WebRTC vocal, Hypergrid, extensibilité MCP après étude de sécurité.

## 13. Risques et questions ouvertes

- Compatibilité réelle de LibreMetaverse avec OpenSimulator 0.9.3.1, et effets des mises à jour.
- Limites de chat/IM, événements multilingues et cas Hypergrid.
- API précise du Translator BloodMoon et licence/dépendances de la bibliothèque.
- Calcul du coût des modèles distants et politique de modération.
- Séparation entre comptes Web, comptes de grille et sessions bot.
- Protection contre prompt injection, manipulation par des résidents, usurpation de noms, boucles de messages et actions indésirables.

## 14. Ce que ce dépôt n'est pas

Ce n'est ni un remplacement de ROBUST, ni une modification obligatoire du code OpenSimulator, ni un service IA gratuit illimité, ni un système prêt à agir sans contrôle sur la production.

La vision reste large ; l'exécution suit des étapes courtes, mesurables et réversibles.
