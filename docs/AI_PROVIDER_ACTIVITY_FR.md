# Suivi réel des API IA — BloodMoon AI

## Objectif

Le fait qu'un bot réponde en IM ne prouve pas quel fournisseur a été utilisé. Ce suivi fournit **la preuve du fournisseur/modèle ayant réellement produit la réponse**, avec les tentatives précédentes et les motifs de basculement.

## Fonctionnement

- Dans **Administration BloodMoon AI → Modules IA → Activité des modèles IA**, sélectionner l'avatar à examiner.
- Une fois les nouveaux fichiers déployés, chaque tentative d'IA peut générer un événement horodaté en UTC. Les **50 plus récents** sont visibles sur la page ; le journal en conserve **100 au maximum par avatar**.
- **Dernière réponse** présente le dernier événement `success` (fournisseur, modèle, date, et `Basculement réussi` si au moins un moteur précédent a échoué/été écarté dans la même demande).
- `http_error (429)` indique une réponse HTTP de limitation du fournisseur ; `local_quota` indique le plafond **local** atteint avant l'appel au fournisseur ; `cooldown` signifie un moteur temporairement mis en pause ; `transport_error` indique une erreur réseau ; `empty_reply` une réponse vide.
- Un événement `success` **sans** `Basculement` indique seulement que la réponse a été produite par ce moteur, sans échec préalable enregistré pour cette requête. Cela ne prouve pas que le fallback est testé.
- Les profils désactivés/non vérifiés ne sont pas tentés et n'apparaissent donc pas comme échecs : ne pas confondre configuration et activité réelle.
- **Aucun texte d'IM, UUID résident, clé API, réponse, adresse IP, coût ni volume de tokens** ne sont enregistrés dans ce journal.

## Fichiers privés

Le bot écrit un fichier JSON privé sous `data/ai-provider-activity.json` **à côté du `appsettings.json` du bot** : installation principale, ou `/var/lib/opensim-ai-bridge/bots/<id>/data` pour un bot secondaire. Écriture atomique, maximum 100 événements, et aucune dépendance réseau supplémentaire.

Le contrôleur Python ne renvoie **que les champs autorisés** au navigateur Web authentifié et ne retourne jamais le contenu des conversations. La lecture n'accepte que le fichier régulier attendu dans le dossier de données de l'avatar sélectionné.

## Déploiement sur robust-vm

**Ne pas redéployer tout le serveur automatiquement.** Télécharger un nouvel artefact GitHub Actions **avec build entièrement réussi**, puis effectuer une **maintenance générale** depuis le panneau Web.

1. Sauvegarder le binaire `OpenSimAiBridge.Bot.dll`, le contrôleur privilégié `/usr/local/libexec/opensim-ai-bridge/control.py` et `/var/www/BloodMoon/OpenSim_AI/index.php`.
2. Arrêter et verrouiller les bots depuis **Maintenance générale**, mais **laisser le contrôleur** actif.
3. Depuis l'artefact vérifié, copier le nouveau binaire .NET dans le dossier d'installation (avec ses dépendances si elles ont changé), le nouveau contrôleur dans **`/usr/local/libexec/opensim-ai-bridge/control.py` sous root:root** et la page Web dans `/var/www/BloodMoon/OpenSim_AI/index.php` avec ses permissions historiques.
4. Vérifier `python3 -m py_compile /usr/local/libexec/opensim-ai-bridge/control.py` et `php -l /var/www/BloodMoon/OpenSim_AI/index.php`. Redémarrer seulement **le contrôleur** pour rendre l'action `ai_activity` disponible.
5. Terminer la maintenance générale depuis l'administration ; vérifier que les bots sont reconnectés. Envoyer une **nouvelle question en IM** à un bot autorisé, puis consulter **Modules IA**. Les anciennes conversations ne seront pas reconstituées.
6. En cas d'échec, restaurer les trois sauvegardes puis redémarrer le contrôleur et reprendre les bots avec l'ancien binaire.

**Aucun changement** aux clés secrètes, `appsettings.json`, `multi-ai.json`, connaissances PDF/SQLite, ROBUST ni simulateurs n'est requis.

## Tester le fallback de manière fiable

D'abord vérifier qu'une requête normale crée un événement `success` indiquant fournisseur et modèle. Ensuite, sur un avatar de test et sans compromettre la grille en production, provoquer **un échec maîtrisé** du premier modèle ou un vrai plafond de quota local, puis poser une question unique. Le journal doit montrer deux événements : d'abord `http_error` (ou `local_quota`), puis `success` sur le second modèle avec `Basculement`.

Une simple modification de l'ordre des modèles ne suffit pas à **prouver** une reprise après incident : il faut observer un essai raté/écarté puis une réponse de secours dans le même échange. Éviter de provoquer artificiellement des 429 en spammant des fournisseurs ou en consommant des crédits.

**Limites :** le système ne publie pas de métrique de facturation ou de tokens ; les événements signalent les réponses HTTP et erreurs vues par le client, pas les dépenses ni les quotas fournisseur restants. L'historique appartient au bot et ne remplace pas les métriques du fournisseur.
