# Catalogue IA distant — V2 en développement

> Branche : `feature/ai-catalog-v2` — PR #6. **Ne pas installer en production avant validation de la V2.**
>
> La V1 déjà installée est indépendante : aucune recherche de modèle, aucun IM et aucune clé ne passe par ce catalogue.

## But

Afficher, dans l'administration OpenSim AI Bridge, un **annuaire consultatif de modèles d'API distantes**. Voir un modèle n'est pas une autorisation de l'utiliser : la sécurité du routeur V1 (profils explicitement activés, modèles approuvés, quotas et cooldowns) reste la seule source d'autorité.

La source consultée le 27 novembre 2026 est `https://free-llm.com/catalog.json`, schéma `2` (88 fournisseurs et 465 modèles annoncés ce jour, nombres variables). Le flux déclare une licence MIT et le dépôt source est sous licence MIT ; conserver l'attribution Free-LLM en cas de redistribution et ne pas présumer de droits sur les catalogues tiers imbriqués. Les champs `free_tier`, `rate_limit`, `daily_limit` sont des **allégations du fournisseur de données**, non des garanties officielles de gratuité, de quota ou de disponibilité. Le catalogue est volatil ; vérifier les conditions de chaque API chez son fournisseur.

Aucun Ollama, modèle hébergé localement, ou inférence sur `robust-vm` n'est ajouté. Une API distante qui sert un modèle open weight est différente d'un modèle exécuté localement.

## Architecture additive, indépendante des IM

1. `controller/catalog_models.py` : normalise les données de type `API` / `Proxy`, avec une adresse HTTPS, seulement les modèles `kind=chat`. Filtre des données invalides, dédoublonne, borne le volume, ne renseigne jamais une clé ou un profil actif. `costVerified=false`, `approved=false`, `enabled=false`.
2. `controller/catalog_cache.py` : rafraîchissement **manuel et explicite** (pas de tâche planifiée installée), URL HTTPS fixe, aucun secret, redirections refusées, limite 2 Mo, timeout 10 s. Remplacement atomique du cache ; en cas d'échec, le précédent reste intact.
3. `controller/control.py` : commande `catalog_list` **lecture seule**, maximum 30 modèles retournés, recherche et filtres. Ne lit pas les secrets, ne modifie pas `multi-ai.json`.
4. `web/OpenSim_AI/index.php` : onglet **Catalogue IA** avec filtre, fournisseur et statut indicatif de compatibilité, plus l'action **Préparer** qui présente un identifiant à renseigner **manuellement** dans Modules IA sans écrire de profil. Tous les champs externes sont échappés en HTML.
5. Aucun changement `.NET`, aucun changement des bases de quotas ou du code HTTP des modèles actifs.

## Structure de cache

Chemin fixe prévu : `/var/lib/opensim-ai-bridge/catalog/catalog.json`, hors dossier Web, séparé des bases privées.

L'installateur V2 crée le répertoire en mode privé `0700` pour root et installe un service et un timer systemd séparés, mais **ne les démarre ni ne les active automatiquement**. Le contrôleur lit ce cache sous root, aucune clé n'est envoyée à la source externe. Commande de l'importeur après installation et préparation des droits :

```bash
python3 /usr/local/libexec/opensim-ai-bridge/catalog_cache.py \
  --cache /var/lib/opensim-ai-bridge/catalog/catalog.json
```

Pour activer volontairement la synchronisation quotidienne **après installation et validation**, utiliser `sudo systemctl enable --now opensim-ai-bridge-catalog.timer`. Le timer lance une tâche isolée autour de 04:15 heure du serveur (délai aléatoire jusqu'à 20 minutes). Pour la désactiver : `sudo systemctl disable --now opensim-ai-bridge-catalog.timer`. Aucune modification du service bot ; les IM sont indépendants.

Si aucun cache n'est présent, l'onglet l'indique ; les modèles déjà configurés restent utilisables, sans attente réseau et sans perte de service. Ne pas exposer le cache comme une API publique.

## État actuel de la PR

- Normaliseur et cache : implémentés, tests hors ligne.
- Affichage PHP + commande contrôleur : implémentés dans la branche, tests du filtrage. Action « Préparer » consultative sans écriture, sans clé ni activation.
- Packaging : les deux nouveaux modules sont inclus dans l'artefact et l'installateur du contrôleur.
- Synchronisation planifiée facultative : unités systemd installables sans activation automatique.
- **À finir avant fusion :** exercice complet d'installation V1→V2, validation effective de l'import du flux depuis l'environnement cible, contrôle des droits et retour arrière sur robust-vm. L'ajout d'un profil actif continue de passer par les protections V1.

La présence de fournisseurs `groq`, `gemini` ou `openrouter` dans le catalogue ne prouve **pas** qu'un modèle précis est accepté par le routeur V1. L'indicateur de compatibilité sur la page signale uniquement que le *fournisseur* possède déjà un adaptateur.
