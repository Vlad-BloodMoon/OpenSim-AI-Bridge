# TODO — Routeur IA intelligent et catalogue de modèles distants

> **Statut : PLANIFIÉ — non implémenté dans ce document.** Dernière revue des sources : **27 novembre 2026**.
>
> Objectif : faire évoluer **OpenSim AI Bridge / BloodMoon AI** en s'inspirant de deux projets publics, **sans les installer comme dépendances**, sans ajouter d'inférence IA locale, sans perturber les bots existants et sans remplacer notre administration PHP, notre routeur .NET 8 ou la base SQLite partagée.
>
> **Règle de suivi :** une case cochée signifie qu'une fonctionnalité a été implémentée, testée et documentée. Les tâches ci-dessous sont initialement non cochées. Une description dans un projet tiers ne vaut pas preuve de fonctionnement dans notre code.

## 1. Références externes, licences et limites

### A. FreeLLMAPI — idées de routage / basculement

- Projet : https://github.com/tashfeenahmed/freellmapi
- Documentation principale : https://github.com/tashfeenahmed/freellmapi/blob/main/README.md
- Vue d'architecture : https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/architecture/00-high-level-index.md
- Licence **MIT** : https://github.com/tashfeenahmed/freellmapi/blob/main/LICENSE
- Mécanismes annoncés dans son README : sélection dynamique des modèles, stratégies de routage, repli sur HTTP 429 / 5xx, rotation des clés, refroidissement, suivi de quotas, catalogue de modèles.
- **Précaution essentielle :** le README indique expressément que le projet est conçu pour l'expérimentation et l'apprentissage, **pas une garantie de production**. La mise à jour du catalogue est différenciée entre flux gratuit différé et flux « premium » ; ne pas présumer que tous les flux sont librement réutilisables.

### B. Free-LLM — annuaire actualisé ET routeur

- Projet : https://github.com/nejib1/Free-LLM
- Annuaire : https://free-llm.com/
- README : https://github.com/nejib1/Free-LLM/blob/main/README.md
- Routeur : https://github.com/nejib1/Free-LLM/blob/main/router/README.md
- Code des décisions / fallback : https://github.com/nejib1/Free-LLM/blob/main/router/src/router.js
- État et apprentissage des limites : https://github.com/nejib1/Free-LLM/blob/main/router/src/state.js
- Classification des erreurs / headers : https://github.com/nejib1/Free-LLM/blob/main/router/src/upstream.js
- Catalogue et métadonnées : https://github.com/nejib1/Free-LLM/blob/main/router/src/catalog.js
- Historique des offres : https://github.com/nejib1/Free-LLM/blob/main/FREE-TIER-CHANGELOG.md
- Source publique annoncée par le projet : https://free-llm.com/catalog.json
- Licence **MIT** : https://github.com/nejib1/Free-LLM/blob/main/LICENSE
- Code observé : classification `rate_limit` / `quota` / `auth` / `server` / `timeout`, lecture `Retry-After` et en-têtes `x-ratelimit-*`, santé par fournisseur/modèle/clé, statistiques de latence et refroidissements persistants, sélection et réessais avant la réponse.
- Les **nombres de fournisseurs/modèles et leur gratuité varient** ; ce sont des données indicatives à dater et vérifier auprès des fournisseurs. Le catalogue cite aussi des outils locaux : **ne proposer que les API distantes** dans BloodMoon AI.

### Conditions de réutilisation

- **Idées et architectures :** les étudier, puis écrire une implémentation adaptée en C# / Python / PHP.
- **Copie/adaptation substantielle de code MIT :** garder les mentions de copyright et le texte de licence exigés par l'auteur, documenter la provenance et les modifications ; ne pas effacer les crédits.
- **Données de catalogue :** vérifier séparément conditions d'accès, de redistribution, fiabilité, fréquence des mises à jour et éventuelles restrictions de flux. Un dépôt sous MIT ne garantit pas automatiquement la licence de toutes les données servies par un site tiers.
- **Fournisseurs :** respecter leurs conditions, leurs limites de comptes et leurs éventuels coûts. Pas de rotation de fausses identités ni de multiplication de clés destinée à contourner une limite commune au compte.
- **Ne pas promettre « gratuit illimité » ni « haute disponibilité garantie »** pour les API distantes.

## 2. Point de départ réel dans OpenSim AI Bridge

| Élément | Situation vérifiée dans le dépôt | Fichier / documentation |
| --- | --- | --- |
| IM et réponses distantes | Implémentés avec LibreMetaverse et routeur .NET | [RemoteAiResponder.cs](../src/OpenSimAiBridge.Bot/RemoteAiResponder.cs) |
| Bascule automatique ordonnée | Mode `auto`, profils actifs/vérifiés, réponse du premier moteur disponible | [RemoteAiResponder.cs](../src/OpenSimAiBridge.Bot/RemoteAiResponder.cs) |
| HTTP 429 / 5xx / erreurs réseau | Le routeur essaie un autre profil, applique un refroidissement **local au processus** ; respect partiel de `Retry-After` | [RemoteAiResponder.cs](../src/OpenSimAiBridge.Bot/RemoteAiResponder.cs) |
| Budget partagé | SQLite `ai-provider-quotas.db`, plafond applicatif **30 tentatives par fournisseur/heure** ; ce n'est **pas** le quota réel du fournisseur | [SharedProviderQuota.cs](../src/OpenSimAiBridge.Bot/SharedProviderQuota.cs) |
| Cooldown partagé | `RecordCooldown()` existe, mais n'est pas encore appelé lors des erreurs du routeur | [SharedProviderQuota.cs](../src/OpenSimAiBridge.Bot/SharedProviderQuota.cs) |
| Suivi des réponses | Historique privé des tentatives et du modèle gagnant, **par avatar**, déjà implémenté ; pas encore de mesures de latence/consommation | [AI_PROVIDER_ACTIVITY_FR.md](AI_PROVIDER_ACTIVITY_FR.md) |
| Configuration multi-IA | Profils et priorités partagés via fichiers privés, contrôleur Python et PHP | [controller/control.py](../controller/control.py), [index.php](../web/OpenSim_AI/index.php) |
| Catalogue externe | **Non intégré** | À développer |
| Multi-clés par fournisseur | **Non intégré** ; étude de faisabilité / politique fournisseur obligatoire | À étudier |
| Validation en production du fallback | Une réponse directe réelle a été observée ; **un scénario live de repli sur erreur reste à vérifier** | [MULTI_PROVIDER_ROUTING_FR.md](MULTI_PROVIDER_ROUTING_FR.md) |

### Contraintes non négociables

1. **Zéro modèle local** (aucun Ollama / LLM CPU/GPU sur `robust-vm`) : requêtes vers des API distantes uniquement.
2. Garder **OpenSimulator, bots existants, Web PHP, contrôleur Unix et SQLite**. Ne pas transformer la recherche documentaire FTS5 ou la traduction.
3. **Fail-closed** : jamais d'appel payant imprévu, jamais de clé à un hôte non autorisé, pas de fallback vers un modèle non validé.
4. Quotas et périodes d'indisponibilité **partagés entre tous les avatars** concernés ; interdiction de contourner un plafond global en changeant de bot ou de modèle.
5. Configuration des modèles **stable par défaut** ; tout mode de sélection automatique nouveau est **opt-in**, contrôlable, et réversible.
6. Pas de contenu d'IM, UUID résident, secret, clé API ou base privée dans les métriques, le catalogue, le dépôt ou les réponses du contrôleur.
7. Les sources tierces servent à **informer** ; le catalogue doit pouvoir être hors ligne sans empêcher le bot de répondre avec ses profils déjà configurés.
8. Préserver l'accès aux services existants, la compatibilité .NET 8, Linux, PHP et le fonctionnement via Firestorm.

## 2 bis. Architecture cible commune à V1, V2 et V3 — à définir avant de coder

**Principe impératif : V1, V2 et V3 sont des incréments d'une même architecture, PAS trois versions à réécrire.** V1 installe le socle final ; V2 ajoute des données de découverte ; V3 ajoute une autre stratégie de sélection. Le moteur d'exécution des API, le stockage de l'état, le schéma de configuration et les frontières de sécurité restent les mêmes.

### Chaîne de traitement définitive dès V1

```text
IM OpenSimulator
   → autorisation / anti-abus / connaissance documentaire existante
   → demande IA normalisée (modèle, capacités, priorité, budget, délai)
   → sélection des candidats [IModelSelector]
        V1 : PrioritySelector
        V2 : PrioritySelector inchangé + catalogue consultatif indépendant
        V3 : AdaptiveSelector opt-in ; PrioritySelector reste disponible
   → validation commune [IEligibilityPolicy] :
        modèle explicitement autorisé, coût, quotas, cooldown, capacités
   → réservation partagée et atomique [IProviderStateStore : SQLite]
   → exécution du fournisseur [IProviderAdapter / client HTTP existant]
   → classification commune [IProviderErrorClassifier]
   → événement d'observabilité [IAiActivitySink] sans IM ni identifiant résident
   → succès IM OU candidat de secours dans la même enveloppe de délai
```

Les noms d'interfaces sont **des contrats de conception proposés**, pas des classes déjà créées. Ne pas forcer une abstraction inutile si l'implémentation .NET peut être plus simple ; garder **les responsabilités et contrats stables**.

### Contrats stables à poser dès V1

- [ ] **A0.1 — Modèle commun de candidat** : `ProviderId`, `ModelId`, `CredentialRef` (référence privée, jamais la clé), rang manuel, capacités, identité de politique de coût. Les identifiants sont stables et ne dépendent pas de l'ordre d'affichage.
- [ ] **A0.2 — États communs de disponibilité** : `ready`, `rate_limited`, `daily_quota`, `auth_failed`, `model_unavailable`, `provider_unavailable`, `network_timeout`, `unknown`. Portée précise : modèle / clé / compte / fournisseur ; horodatage UTC de reprise, source de la décision et fiabilité de l'information.
- [ ] **A0.3 — Un seul stockage SQLite partagé** : schéma versionné et migrations **additives** pour quotas, cooldowns et métriques agrégées ; mêmes clés logiques pour V1/V2/V3 ; écritures transactionnelles entre processus. Le catalogue a ses propres tables/cache, sans écraser l'état opérationnel.
- [ ] **A0.4 — Un seul pipeline de tentatives** : exécution, classification HTTP, budget temps, autorisation, protection des coûts, enregistrement et failover sont partagés par le mode manuel et le futur mode intelligent. **Ne jamais dupliquer ce code en V3.**
- [ ] **A0.5 — Sélection interchangeable** : politique de priorité actuelle activée par défaut ; ajout du mode automatique en V3 **sans changer l'exécuteur, les quotas, les API ou les profils**. Un simple retour de paramètre permet de revenir à la priorité fixe.
- [ ] **A0.6 — Catalogue dissocié** : V2 lit une source externe vers un cache **consultatif**, sans appeler le routeur ni déclencher une activation automatique. On convertit un modèle du catalogue vers un candidat uniquement après validation humaine.
- [ ] **A0.7 — Contrat admin versionné** : le contrôleur expose des vues de statut, capacités, quotas et catalogue sans secrets. Ajout de champs rétrocompatible (pas de changement de sens ni renommage non migré des champs du PHP existant).
- [ ] **A0.8 — Compatibilité persistante** : lecture de `config/multi-ai.json`, clés `ai-keys/*` et SQLite existants ; migration idempotente, sauvegarde automatique avant migration et aucun effacement de données. Éventuels nouveaux réglages avec valeurs par défaut égales au comportement actuel.
- [ ] **A0.9 — Tests transversaux dès V1** : même corpus de tests contractuels exécuté à chaque phase : ordre manuel, autorisation, sélection non facturable, cooldown, reprise, concurrence multi-bots, protection contre les dépenses, absence de fuite de secrets et d'IM.
- [ ] **A0.10 — Décision explicite avant la première PR** : noter le schéma SQLite, les invariants, les points d'extension, le format des événements et les exemples de migration ; revue des risques sur les bots en production. Ces décisions guident toutes les issues, sans rouvrir l'architecture à chaque version.

### Garantie de continuité de service : le bot doit toujours répondre

**Critère bloquant pour chacune des trois phases : l'évolution ne doit jamais interrompre ou dégrader le circuit IM actuellement en production.** Ce projet améliore l'existant ; il ne remplace ni le bot ni sa pile logicielle.

- [ ] **B0.1 — Ligne de base reproductible** : tests hors ligne + test IM réel avant modification sur avatar de référence : réception IM, réponse de Groq, réponse longue Firestorm, autorisations, mémoire courte, connaissance PDF/TXT/FTS5, traduction, délais anti-abus et reconnexion.
- [ ] **B0.2 — Configuration rétrocompatible** : conserver tous les profils, IDs, clés et paramètres existants ; nouveaux champs facultatifs et désactivés par défaut. Aucun changement imposé aux avatars ni aux résidents.
- [ ] **B0.3 — Séparation des défaillances** : indisponibilité de l'annuaire, cache, statistiques ou lecture d'un en-tête inconnu ne doit jamais devenir une panne de l'IM ; les composants annexes dégradent leur fonction propre et le routeur se replie sur la stratégie stable.
- [ ] **B0.4 — Une route de réponse stable** : un seul chemin `IM → recherche documentaire → candidats autorisés → API distante → retour IM`. Le socle V1 doit pouvoir répondre même sans catalogue V2 ni stratégie V3.
- [ ] **B0.5 — Tests de non-régression obligatoires** à chaque PR et version : réponses directes, secours, profils désactivés, limites, multi-avatar, mémoire, traduction, recherche documentaire, Firestorm, erreurs réseau et persistance des quotas.
- [ ] **B0.6 — Déploiement progressif** : tester hors ligne, puis un **avatar de test**, puis déployer aux avatars utilisés par les résidents ; pas de remplacement simultané sans retour arrière prêt. Une interruption courte et planifiée en maintenance n'est pas une garantie de zéro coupure.
- [ ] **B0.7 — Retour arrière garanti** : sauvegarde du binaire, PHP, contrôleur et données SQLite avant changement, migrations additives, version antérieure et procédure de restauration vérifiées. Garder les copies protégées hors Web.
- [ ] **B0.8 — Go/no-go** : **bloquer toute mise en production** si un test IM ancien échoue, si une donnée/configuration est perdue, si un profil non autorisé est appelé ou si le bot ne peut plus répondre. Corriger sur environnement de test puis retester.

**Règle d'exploitation :** si la nouvelle rotation échoue, revenir immédiatement au routage à priorité fixe et au binaire validé ; ne pas tenter de corriger la panne en direct sur les bots publics. Ne jamais promettre qu'un fournisseur distant répondra toujours : en cas d'indisponibilité de *toutes* les API autorisées, le bot doit émettre une réponse d'indisponibilité claire, sans bloquer ni planter.

### Compatibilité et évolution incrémentale

| Aspect | V1 — socle stable | V2 — extension | V3 — extension |
| --- | --- | --- | --- |
| Pipeline HTTP et fallback | Créé / fiabilisé | **Réutilisé tel quel** | **Réutilisé tel quel** |
| Stockage des états opérationnels | SQLite commun migré | Identique | Identique + champs de métriques additifs |
| Profils et clés existants | Conservés et migrés sans perte | Conservés ; catalogue propose des profils inactifs | Conservés ; nouvelle stratégie optionnelle |
| Sélection | Priorité déterministe | Même priorité déterministe | Sélecteur intelligent supplémentaire, désactivable |
| Catalogue | Contrat de métadonnées prévu, **aucun besoin du catalogue** | Import et recherche ajoutés | Peut contribuer au score **seulement après validation** |
| Administration Web | État du moteur et événements | Onglet catalogue supplémentaire | Graphiques/stratégie en plus |
| Retour arrière | Version précédente + schéma compatible | Désactivation catalogue sans effet IM | Repasse en priorité fixe instantanément |

### Règles anti-refonte

1. **Pas de « V2 remplace V1 » :** aucune suppression de classe, table ou API introduite en V1 pour gagner seulement une fonctionnalité V2/V3. Toute modification de contrat exige une migration explicite et des tests de compatibilité.
2. **Pas de second routeur** pour le catalogue ou le mode intelligent. Un seul chemin pour tous les appels distants.
3. **Pas de seconde vérité pour les quotas** : les règles configurées et les observations des en-têtes fournisseur sont réconciliées dans le stockage partagé ; l'annuaire ne définit jamais à lui seul les limites effectives.
4. **Pas de déploiement global pour chaque ajout de modèle** si l'adaptateur du fournisseur existe déjà : configuration validée et test réel explicite doivent suffire.
5. **Données privées séparées du dépôt** ; pas de modèle local, pas de nouvelle dépendance runtime FreeLLMAPI / Free-LLM.
6. **Une étape achevée reste fonctionnelle seule** : V1 peut tourner sans V2 ni V3 ; V2 sans V3 ; V3 peut être désactivée sans rétrograder tout le système.

### Critères de « prêt pour V2 » et « prêt pour V3 »

- **Passage V1 → V2 :** contrats A0.1–A0.10 documentés et stables, migrations testées depuis une installation V1, aucun échec de tests IM/quotas, et un scénario de secours factice confirmé. **On ajoute uniquement les services/cache/écrans du catalogue.**
- **Passage V2 → V3 :** catalogue indépendant et optionnel, pipeline V1 toujours unique et testé, événements et état partagé exploitables par le nouveau sélecteur. **On ajoute une stratégie de sélection et des métriques ; on ne réécrit pas le fallback.**
- À chaque release : démontrer un **upgrade** depuis l'artefact précédent **et un rollback** documenté, sans supprimer clés ni bases ni historique.

---

## 3. Phases d'implémentation — ordre recommandé

### V1 — Fiabilité du routeur (priorité P0)

**But :** un modèle indisponible est correctement écarté dans tous les bots, la suite de secours répond rapidement et le journal démontre le chemin effectivement pris.

- [ ] **P0.1 — Inventaire de la logique actuelle** : vérifier les modes `single`/`auto`, le nombre maximum de tentatives, les cool-downs actuellement locaux, l'enregistrement d'activité, et les règles d'autorisation ; conserver les comportements compatibles.
- [ ] **P0.2 — Cooldown persistant et partagé** : brancher `SharedProviderQuota.RecordCooldown()` sur HTTP 429 / 503 / autres erreurs appropriées, relire son état avant chaque appel. Distinguer **modèle**, **clé** et **fournisseur** ; n'immobiliser tout un fournisseur que si l'erreur le justifie. Ne pas exclure les autres modèles d'une clé ou d'un fournisseur lorsqu'une erreur ne concerne qu'un modèle. Stocker le motif, la portée, l'expiration UTC et l'horodatage.
- [ ] **P0.3 — Classification d'erreurs** : différencier `rate_limit`, `daily_quota`, `bad_key`, `unsupported_model`, `provider_unavailable`, `timeout`, `network`, `empty_response` ; ne jamais journaliser la réponse d'erreur brute si elle peut contenir des données privées.
- [ ] **P0.4 — Gestion des en-têtes** : gérer `Retry-After` (secondes et HTTP-date), bornes raisonnables, et les en-têtes connus documentés **par fournisseur**. Si absent ou ambigu, dégradation prudente avec date d'expiration. Ne pas supposer que les valeurs de Groq s'appliquent à Gemini/OpenRouter.
- [ ] **P0.5 — Budget de temps par réponse** : distinguer timeout d'une tentative et durée totale de l'échange ; permettre au moins une tentative de secours lorsqu'elle peut réussir, puis répondre clairement sans bloquer indéfiniment l'IM.
- [ ] **P0.6 — Observabilité** : événements `candidate_selected`, `skipped`, `http_error`, `cooldown`, `fallback`, `success` corrélés par **identifiant de tentative aléatoire non résident**, pour prouver la séquence au sein d'une demande ; anonymisation et taille bornée. Présenter l'**état de santé partagé** dans `Modules IA` sans clé ni IM.
- [ ] **P0.7 — Tests déterministes sans API** : serveurs HTTP factices pour 429/Retry-After, 503, 401, timeout, réponse vide ; deux processus/avatars partageant SQLite ; cooldown et reprise après redémarrage ; expiration; absence de double appel; aucun passage vers un fournisseur non approuvé.
- [ ] **P0.8 — Test en conditions réelles** : scénario de repli contrôlé **sur avatar de test**, sans provoquer de spam ni saturer artificiellement les services ; vérifier la continuité IM et les événements dans l'admin.

**Livrables :** changements C# et SQLite migrés sans perte, tests automatiques, affichage état partagé, procédure de retour arrière, guide d'exploitation.

**Critères d'acceptation V1 :** une réponse simulée 429 sur le premier profil conduit au second profil ; un autre bot n'appelle plus une cible bloquée si le cooldown est de portée commune ; reprise à l'expiration ; une défaillance SQLite interdit les appels risquant de dépasser le budget ; `single` n'appelle aucun secours ; journal admin affiche le modèle gagnant sans données privées.

### V2 — Catalogue distant consultatif (priorité P1)

**But :** découvrir des modèles distants éligibles dans l'administration sans les activer automatiquement.

- [ ] **P1.1 — Sources de catalogue** : documenter `Free-LLM` (dépôt, format et conditions de `catalog.json`) et l'éventuelle compatibilité d'un export de FreeLLMAPI ; choisir **une source autorisée et vérifiable** avant téléchargement automatisé.
- [ ] **P1.2 — Import séparé du routeur** : synchronisation planifiée (objectif : 1 fois/jour) avec timeout, taille maximale, vérification HTTPS/hôte, limitation des redirections, parsing strict et stockage cache local horodaté. Aucune clé API n'est transmise au fournisseur du catalogue.
- [ ] **P1.3 — Normaliser les métadonnées** : fournisseur, identifiant de modèle, URL de documentation, type d'API, texte/vision, contexte, quotas connus, conditions d'accès, besoin de carte bancaire, frais éventuels, date et provenance. Valeur **« inconnu »** lorsque non vérifiée, plutôt que supposer « gratuit ».
- [ ] **P1.4 — Catalogue Web** : nouvel onglet admin `Catalogue IA`, recherche, filtres **API distante seulement**, fournisseur, gratuité vérifiée/inconnue, capacités et date de dernière vérification ; avertissement sur volatilité des offres. Ne jamais exposer de clé au navigateur.
- [ ] **P1.5 — Compatibilité explicite** : distinguer `supporté par le routeur`, `adaptateur à écrire`, `incompatible`. Un modèle listé n'est **pas automatiquement utilisable** par `RemoteAiResponder.cs`.
- [ ] **P1.6 — « Préparer l'ajout »** : renseigner les champs du modèle sans activer l'accès public ; nécessiter une clé gérée par le contrôleur, une vérification active explicite (requête API réelle) et un enregistrement administrateur.
- [ ] **P1.7 — Mode dégradé** : catalogue absent, périmé, URL cassée, erreur JSON ou projet tiers indisponible n'affecte **jamais** les IM. Garder le dernier cache valide et afficher sa date.
- [ ] **P1.8 — Tests** : corpus fictif de catalogue (champs malveillants, HTML, URL inconnue, doublons, modèles retirés, coût inconnu), sécurité PHP, synchronisation hors réseau et péremption des métadonnées.

**Livrables :** importeur isolé, cache daté, panneau PHP/contrôleur sécurisé, documentation d'utilisation, avertissements sur les conditions des fournisseurs.

**Critères d'acceptation V2 :** recherche et filtres fonctionnent ; aucune activation implicite d'API ; la disparition de la source externe ne provoque aucune panne de bots ; seuls des modèles explicitement approuvés peuvent entrer dans la configuration active.

### V3 — Pilotage intelligent facultatif (priorité P2)

**But :** choisir automatiquement la meilleure cible autorisée, tout en respectant la priorité définie par l'administrateur.

- [ ] **P2.1 — Mesures partagées** : collecter nombre d'essais/réussites/échecs, latence complète, délai de premier token **uniquement si le protocole le permet**, erreurs classées, durée cooldown et dernière activité ; enregistrement agrégé, sans contenus privés.
- [ ] **P2.2 — Quotas multi-fenêtres** : minute / heure / jour / tokens lorsque disponibles, avec règles spécifiques par fournisseur et unité de comptage correcte. Une limite globale de sécurité reste prioritaire sur les valeurs fournies par le catalogue.
- [ ] **P2.3 — Modes** : `Priorité manuelle` (mode actuel par défaut) et `Auto intelligent` (opt-in) ; filtre préalable pour modèles valides, approuvés, compatibles et budgétés. Pondérer fiabilité, temps de réponse, coût autorisé et quota restant sans écraser les contraintes de l'administrateur.
- [ ] **P2.4 — Multi-clés (optionnel)** : seulement si nécessaire, permis par les conditions du fournisseur et associé à des comptes explicitement autorisés ; secrets hors Web et hors journaux ; respect des limites **par compte**, non seulement par clé. Ne jamais créer une stratégie de contournement des quotas.
- [ ] **P2.5 — Tableau de bord** : santé actuelle, modèle réellement sélectionné, fenêtre de quotas, raison d'exclusion, moyenne mobile de latence, date de mesure et état des sources externes ; aucune donnée de conversation.
- [ ] **P2.6 — Test de basculement** : bouton admin **« Simuler le basculement »** sur routeur d'essai / fournisseurs factices, sans faux 429 envoyés à de vraies API et sans consommation de quotas ; clairement distinguer test simulé et test live.
- [ ] **P2.7 — Évaluation A/B contrôlée** : comparer priorité fixe et auto intelligent sur scénarios reproductibles ; conserver un interrupteur de désactivation immédiate et une restauration des profils antérieurs.
- [ ] **P2.8 — Tests de charge/sûreté** : plusieurs avatars, connexions concurrentes, annulation IM, budget temps total, partage transactionnel, reprise après redémarrage, fournisseur très lent et persistance de cooldown.

**Critères d'acceptation V3 :** le mode automatique ne choisit jamais un profil non vérifié, facturable sans autorisation, ou en cooldown ; le mode manuel reste déterministe ; tests multi-bots passent ; la désactivation d'une fonction avancée restaure le routage V1.

## 4. Ordre technique des modifications dans ce dépôt

| Ordre | Fichier(s) à adapter | Sujet |
| --- | --- | --- |
| 1 | `src/OpenSimAiBridge.Bot/SharedProviderQuota.cs` | Persistance SQLite par cible et cooldown partagé, migrations rétrocompatibles |
| 2 | `src/OpenSimAiBridge.Bot/RemoteAiResponder.cs` | Classification des erreurs, sélection et repli borné, observations réelles |
| 3 | `tests/` et vérifications hors ligne .NET | HTTP mock, scénarios multi-processus, contrôles sécurité |
| 4 | `controller/control.py` | Actions admin **lecture seule** pour état et quotas ; gestion verrouillée de la configuration |
| 5 | `web/OpenSim_AI/index.php` | Visualisation en `Modules IA`, puis nouvel onglet `Catalogue IA` |
| 6 | Nouveaux modules d'import catalogue + `deploy/systemd/` | Cache à accès restreint, timer séparé et opt-in |
| 7 | `docs/`, `README.md`, notes de version | Installation, sécurité, limitations, récupération |

**Important :** vérifier le chemin de déploiement réel du contrôleur (ex. `/usr/local/libexec/opensim-ai-bridge/control.py`) et du binaire avant tout script d'installation. Ne pas écraser les secrets, fichiers par avatar, `multi-ai.json`, base de connaissances `bloodmoon_knowledge.db`, historiques ou données financières.

## 5. Plan de tests, sécurité et déploiement

### Avant modification

- [ ] Vérifier la branche `main`, le dernier build GitHub Actions et les tests existants.
- [ ] Sauvegarder `appsettings.json`, `config/multi-ai.json`, clés privées, DB de quotas et binaires selon leur procédure sécurisée (sans publier ces sauvegardes).
- [ ] Capturer **la configuration active sans les secrets** : modèles validés, ordre de priorité, budgets, mode `single`/`auto`.
- [ ] Conserver un artefact de retour arrière et ne pas modifier la release `v1.0.0` existante.

### Développement

- [ ] Une phase = des modifications et tests clairement isolés ; ouvrir un suivi GitHub dédié et noter les commits associés.
- [ ] Tests déterministes en CI : aucune vraie clé, aucun débit réel vers Groq/Gemini/OpenRouter.
- [ ] Valider migration SQLite, verrous, concurrence, écritures atomiques, retour arrière, absence d'exfiltration de clés et de textes IM.
- [ ] Vérifier conformité aux licences amont en cas de reprise de fragments de code. **Le dépôt OpenSim AI Bridge ne dispose pas actuellement d'un fichier LICENSE explicite** : décider séparément de sa politique de licence avant d'affirmer qu'il est open source sous une licence donnée.

### Déploiement BloodMoon

- [ ] Utiliser **Maintenance générale** pour les changements de DLL et contrôleur, sauvegarder les fichiers déployés et droits avant remplacement.
- [ ] Préférer un avatar / une région de test avant déploiement à tous les avatars.
- [ ] Valider GitHub Actions, `python3 -m py_compile`, `php -l` et tests du code .NET correspondant.
- [ ] Vérifier le dashboard, le maintien de la recherche documentaire/translation, le retour des réponses IM, les quotas et l'état des bots.
- [ ] Effectuer **un test simulé** de 429 → secours, puis si approprié un test live non perturbateur.
- [ ] Prévoir des métriques de réussite et **une restauration documentée** des trois composants (DLL, contrôleur, Web), et si nécessaire de la structure SQLite.
- [ ] Ne jamais considérer une validation de modèle ou un HTTP 200 isolé comme une **preuve de fallback**.

## 6. Décisions à prendre au fil des phases

- Choix du périmètre exact d'un cooldown : clé, modèle, fournisseur, ou compte (selon erreur).
- Sources et droits d'utilisation des données du catalogue ; versionnement et date de vérification.
- Adaptateurs API à développer : ne pas ajouter 79 fournisseurs simplement parce qu'ils figurent dans le catalogue.
- Garantie d'absence de facturation : liste autorisée des API gratuites et consentement explicite à tout service tarifé.
- Budgets de durée : borne par fournisseur et borne totale raisonnable pour un IM Firestorm.
- Conservation / suppression des statistiques techniques sans identifiant résident.
- Faut-il une nouvelle licence explicite pour **notre** dépôt, distincte de celles des références MIT ?

## 7. Suivi

### Issues GitHub dédiées

- **V1 / P0 — Fiabilité de la bascule :** https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge/issues/2
- **V2 / P1 — Catalogue API distantes :** https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge/issues/3
- **V3 / P2 — Sélection intelligente et métriques :** https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge/issues/4

Ordre de réalisation : **socle A0.1–A0.10 → V1 → V2 → V3**, avec CI et validation sur bot de test entre chaque étape. **Aucune refonte intermédiaire** : l'architecture et le pipeline communs sont établis avant la V1.

Ce document est la **source de vérité du TODO**. À l'ouverture de chaque chantier, relier l'issue/PR et cocher les cases seulement après tests réels. Les liens tiers donnent des **pistes techniques**, non des dépendances déjà installées.

**Hors périmètre :** héberger un LLM sur `robust-vm`, déployer FreeLLMAPI ou Free-LLM Router comme service intermédiaire, agrégation de comptes visant à contourner les quotas, découverte automatique suivie d'activation publique sans validation.
