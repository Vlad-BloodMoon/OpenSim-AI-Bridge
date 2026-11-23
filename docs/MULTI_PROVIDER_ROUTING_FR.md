# BloodMoon AI — Administration multi-fournisseurs et continuité des IM

Statut : **architecture approuvée comme direction de conception, non déployée** (23 novembre 2026).

## Objectif

Remplacer la configuration d'un fournisseur par avatar + liste d'UUID par une **administration multi-IA destinée à tous les résidents**, sans installation de modèle local. Chaque avatar choisit parmi des profils de modèles distants testés et peut fonctionner avec **un seul moteur**, ou avec une **chaîne ordonnée de secours**.

Préserver impérativement la grille, les avatars existants, les clés API, le bot Groq public, les limites horaires, la maintenance générale et l'index SQLite commun. Aucun coût ne doit être engagé automatiquement pour des conversations publiques.

## Parcours dans l'administration

Menu **« Modules IA »**, puis :
- **Mode :** « IA unique » ou « Multi-IA (basculement automatique) ».
- **Profils d'IA :** liste de cartes réordonnables par flèches ↑ / ↓ (accessibles au clavier), avec activation oui/non, fournisseur, modèle, état de validation, limite de coût et bouton **« Tester »**. Les flèches changent la priorité de la chaîne; la première carte *active et validée* est prioritaire. Possibilité de choisir un seul profil pour des essais, ou 2, 3, 4… profils.
- **Gestion des clés :** une clé distincte par fournisseur (ou profil si nécessaire), stockée hors du Web, non réaffichée. La liste des modèles proposés dépend du fournisseur ; identifiant personnalisé possible, avec validation.
- **Configuration par avatar :** activation du service, choix des profils à utiliser, ordre ou héritage d'une configuration commune, consignes propres à l'avatar, quota/cooldown, politique de mémoire, langue des notifications.
- **Page d'état :** moteur effectivement utilisé, échec/429, prochaine tentative autorisée, statut des tests, quotas observés quand l'API les expose.
- **Tests :** bouton « Tester ce fournisseur » avec réponse courte, coût estimé/mesuré si accessible, statut HTTP et validation explicite avant intégration dans le routage automatique. Un test peut consommer un quota et, si une facturation a été activée chez le fournisseur, peut coûter de l'argent ; afficher l'avertissement avant l'appel.
- **Conversations :** accès public par défaut pour les profils *explicitement approuvés pour le public et sans risque de facturation*. Pas de formulaire UUID à saisir pour une conversation publique. Les comptes privilégiés et les éventuelles exceptions payantes doivent être une politique administrative distincte, pas la condition de fonctionnement général.

### Exemple d'état initial de migration

```text
Mode : IA unique
1. Groq / openai/gpt-oss-20b    [activé] [priorité 1] [test connu OK]
2. OpenRouter / modèle :free  [désactivé] [à tester]
3. Gemini / modèle gratuit   [désactivé] [à tester]
```

**Migration non destructive :** convertir l'ancienne configuration `Ai` vers un premier profil Groq sans effacer `ai-api-key.txt`. Une nouvelle clé d'un autre fournisseur ne doit jamais remplacer cette clé. Conserver l'ancienne config lisible pendant une phase transitoire; prévoir retour arrière et tests de non-régression.

## Routage et quotas

1. Filtrer les fournisseurs : activés, validés, acceptés pour le public, paramètres de modèle compatibles, secrets présents, quota disponible et coût autorisé. En mode « IA unique », ne jamais appeler un autre profil automatiquement.
2. Respecter les quotas **internes avant** d'appeler la première API (global, par résident, par avatar, par fournisseur). Une réponse 429, 5xx ou un délai d'attente déclenche éventuellement un secours ; une erreur de configuration ou d'authentification bloque le profil et demande une action administrateur. Ne **jamais** boucler indéfiniment ni contourner une limite horaire volontaire.
3. Si toutes les IA sont indisponibles : envoyer une réponse courte dans la langue détectée, sans appeler un service payant.
4. Stocker des compteurs de quotas locaux persistants et des délais `retry-after` quand communiqués par le fournisseur. Une API gratuite n'est pas nécessairement garantie gratuite dans toutes les configurations : ne pas se baser seulement sur le nom `free`.
5. Garder les secrets et erreurs brutes hors des IM, journaux publics et pages publiques ; autoriser uniquement des endpoints API prédéfinis, ne pas accepter des URL API arbitraires.
6. Basculement : informer au plus **une fois par transition effective** (« Je poursuis avec un autre moteur IA. ») dans la langue du résident, réglable silencieux / discret / détaillé. Ne pas prétendre qu'un basculement a eu lieu si aucune réponse n'a été obtenue.

## Mémoire des conversations

- Historique court **par avatar et résident**, jamais partagé entre résidents : derniers échanges pertinents (par ex. 8 tours) et limite de tokens envoyés par appel.
- Lors d'un changement de moteur, transmettre l'historique récent + les passages de la base documentaire. Le fournisseur n'a pas besoin d'accéder au stockage d'un autre fournisseur.
- Expirer l'historique après inactivité, limiter sa taille et donner aux résidents un moyen explicite de le réinitialiser. Informer les résidents du traitement par des API tierces, limiter la rétention et protéger les données.
- Ne pas faire passer des textes issus du web/SQLite pour des instructions prioritaires. Inclure les liens sources lorsque les réponses s'appuient dessus.
- Éviter de transmettre tout l'historique aux fournisseurs lorsque ce n'est pas nécessaire, pour réduire consommation de tokens et exposition des données.

## Architecture technique pressentie

```text
IM -> accès public + quotas anti-abus -> mémoire courte
   -> recherche SQLite FTS5 BloodMoon -> routeur de modèles
        -> 1. fournisseur prioritaire
        -> 2. fournisseur secondaire, si échec pertinent et autorisé
        -> 3. fournisseur supplémentaire ...
   -> réponse + notification de changement facultative
```

Configuration en profils validés côté **contrôleur root**; UI PHP CSRF, autorisations et validations strictes; service de bot .NET utilise des clés distinctes. Ne pas exposer l'endpoint réseau du contrôleur; maintenir socket UNIX, droits minimaux. Un test réel doit être exécuté explicitement via une action administrative; ne jamais tester automatiquement au chargement de la page.

Prudence : les applications clientes n'ont pas toujours la même notion de contexte ni les mêmes paramètres d'inférence. Les adaptateurs par fournisseur doivent normaliser les réponses sans supposer que tous supportent les mêmes options. Les plafonds free et les modèles doivent rester reconfigurables, car ces offres changent.

## Plan d'implémentation, sans interruption des avatars

1. **Schéma et migration** : profils fournisseurs et clés séparées; tests de validation, droits, rollback, conversion des anciens paramètres.
2. **UI gestion des moteurs** : cartes, ↑/↓, activation, mode unique/multi, test manuel sécurisé; enregistrement contrôlé.
3. **Routeur .NET** : sélection déterministe, statut de quota/429, repli borné, concurrence et protections publiques; tests hors ligne des cas d'échec et d'ordre.
4. **Mémoire courte** : historique isolé par résident/avatar, rétention limitée, notification traduite sur véritable changement.
5. **Validation progressive** : Groq comme premier profil inchangé, test OpenRouter sans activation publique, puis petite flotte pilote et activation multi uniquement après vérification.
6. **Migration en production** : sauvegarde des fichiers, maintenance générale des avatars lors du déploiement DLL, restauration des services. Aucun changement à ROBUST, Money ni aux simulateurs.

## À ne pas faire avant validation

- Ne pas enlever aujourd'hui la vérification d'UUID dans le backend tout en laissant OpenAI ou OpenRouter accessibles publiquement sans contrôle de coûts.
- Ne pas confondre « API utilisable sans paiement initial » et « gratuité garantie ».
- Ne pas écraser la clé Groq de production avec une clé OpenRouter.
- Ne pas déployer une interface qui affiche multi-IA si le routeur .NET ne sait pas encore gérer le basculement.
