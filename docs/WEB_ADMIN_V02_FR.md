# Conception de l'administration Web — V0.2

**État : spécification de la prochaine implémentation, pas une interface existante.**  
**Priorité :** prendre le contrôle du bot pour permettre son utilisation dans Firestorm, puis administrer un moteur de réponses gratuites.

## 1. Principes

- Aucun modèle IA local ; `OpenAI` ou fournisseurs distants optionnels dans un jalon ultérieur.
- Le pilote est hébergé sur `robust-vm` ; le bot n'est pas ROBUST et doit fonctionner séparément.
- Garder le bot configurable et réutilisable sur d'autres grilles ; éviter de coder des chemins privés ou noms propres.
- Une interface Web **authentifiée**, HTTPS derrière reverse proxy, avec RBAC ; aucun appel direct du navigateur vers systemd, SQL ou des clés.
- API sur boucle locale ; ne publier que l'interface via proxy protégé.

## 2. Contrôle du service : systemd plutôt que screen

- Un service Linux dédié, avec utilisateur restreint, répertoire de travail explicite et secrets dans des fichiers locaux protégés.
- `start` : démarre la session si maintenance inactive.
- `stop` : empêche les relances puis demande Logout et l'arrêt du service.
- `restart` : arrêt propre, puis relance contrôlée.
- `maintenance/firestorm` : met un verrou durable **avant** le Logout, bloque toute auto-reconnexion, survit au redémarrage du système ; un second opérateur ne doit pas pouvoir remettre le bot en route par accident.
- `resume` : uniquement après confirmation que le viewer du même avatar est fermé ; retire le verrou puis lance le bot.
- En cas de reconnexion refusée, session remplacée ou conflit viewer, suspendre retries et avertir plutôt que boucler.
- Une page d'état montre l'état service OS et l'état avatar **séparément** (service lancé n'implique pas connecté).

Pour ne pas ouvrir de privilèges système à un serveur Web, prévoir une petite couche de contrôle (daemon local/socket Unix ou helper avec autorisations strictes) avec commandes typées et journaux, et **non** une commande shell fournie par l'interface.

## 3. Écrans

### Tableau de bord
- Avatar/UUID, région, coordonnées observées, heure du dernier heartbeat.
- États : `offline`, `starting`, `online`, `reconnecting`, `stopping`, `maintenance`, `error`.
- Actions : connecter, arrêter, redémarrer, activer/relever le mode Firestorm, uniquement pour les rôles autorisés.
- Logs techniques à durée de conservation limitée, filtrés (aucun secret).
- Compteurs d'IM reçus / de réponses / erreurs, sans contenu privé par défaut.

### Réponses gratuites (FAQ)
- CRUD de fiches (catégorie, langue, canal, variantes de question, réponse, priorité, actif/inactif).
- Correspondances contrôlées et traçables ; ignorer les correspondances ambiguës.
- Réponses localisées FR/EN/ES/DE/PT/IT selon disponibilité.
- Test de correspondance depuis l'administration et prévisualisation avant publication.
- Variables autorisées `{grid_name}`, `{region_name}` et références de destinations, sans exposition de données privées.
- Historique des modifications et file des questions sans réponse (minimisation et délai de rétention).

### Traduction
- Fournisseur HTTP configurable (endpoint, méthode, authentification côté serveur).
- Adaptateur BloodMoon : `https://bloodmoonpack.com/translator/translate.php`, **contrat JSON à vérifier dans le code existant avant développement**.
- Langue par défaut, langue préférée par utilisateur (UUID), choix manuel prioritaire, contrôle des langues supportées.
- Cache des traductions des **réponses publiques** ; ne pas conserver des messages privés sans accord.
- Quotas, délai, indisponibilité, fallback vers langue d'origine ; traduire avant ou après correspondance selon la stratégie testée.
- Écran de test d'une phrase sans envoyer de secrets au navigateur.

### IA externe (V0.3, écran réservé)
- Liste d'utilisateurs autorisés (UUID), choix du fournisseur distant, quotas et budget par personne.
- Route `public` : FAQ et option future d'une API distante avec offre gratuite, désactivée par défaut.
- Route `authorized` : OpenAI API ou autre fournisseur à droits et quotas définis.
- Fournisseurs candidats : GroqCloud Free, OpenRouter free models, Gemini API Free ; limites, disponibilité, traitement des données et conditions à revérifier avant activation.
- Ne jamais utiliser une API tierce pour des données de compte, des logs privés ou l'administration ROBUST sans validation explicite.

## 4. API indicatives (non implémentées)

```text
GET  /api/admin/bots
GET  /api/admin/bots/{id}/status
POST /api/admin/bots/{id}/start
POST /api/admin/bots/{id}/stop
POST /api/admin/bots/{id}/restart
POST /api/admin/bots/{id}/maintenance/enable
POST /api/admin/bots/{id}/maintenance/disable

GET    /api/admin/answers
POST   /api/admin/answers
PUT    /api/admin/answers/{id}
DELETE /api/admin/answers/{id}
POST   /api/admin/answers/test

GET  /api/admin/translation/status
POST /api/admin/translation/test
GET  /api/admin/unanswered
```

Les opérations d'écriture demandent authentification forte, rôle et CSRF (si cookies), validation et audit. Toutes les opérations sont idempotentes quand possible.

## 5. Séquence proposée

1. Contrôle local robuste (démarrage/arrêt, secret fichier, état maintenance persistant) sans Web public ; tests manuels.
2. Administration HTTPS et authentification, statut et boutons.
3. FAQ persistante (SQLite ou DB dédiée), formulaire Web et moteur de règles.
4. Adaptateur de traduction après validation du protocole existant.
5. IA distante et politique des utilisateurs dans une V0.3 distincte.

## 6. Critères d'acceptation immédiats

- Une commande Web **Arrêter** déconnecte le bot et libère le compte.
- En mode Firestorm, aucune tentative de reconnexion pendant l'utilisation du viewer, même après reboot serveur.
- Une commande **Reprendre** reconnecte le bot uniquement sur demande autorisée.
- Seul le rôle administrateur voit les opérations de service ; aucun accès public.
- La FAQ reste consultable sans API IA et sans modèle local.
- Le secret avatar ne figure ni dans le code, ni dans les logs ni dans le dépôt GitHub.
