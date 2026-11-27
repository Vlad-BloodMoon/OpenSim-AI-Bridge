# Bibliothèque PDF évolutive — `/var/www/BloodMoon/files/`

**BloodMoon AI — 27 novembre 2026.** Un importeur distinct de l'indexation du site Web et des fiches TXT lit récursivement les fichiers PDF présents sous `/var/www/BloodMoon/files/`, **y compris tous les sous-dossiers**.

## Fonctionnement

- Les fichiers sont lus localement, sans crawler HTTP, sans API IA et **sans OCR**. `pdftotext` extrait toutes les pages, séparées en passages FTS5 avec leur numéro de page dans le texte. Aucun seuil de 60 pages et **aucun nombre maximal de PDF**. Un PDF individuel est limité à 200 Mo et à 180 secondes d'extraction pour protéger le serveur.
- L'indexeur calcule une empreinte SHA-256 de chaque PDF : le contenu inchangé n'est pas réextrait ; un PDF ajouté ou modifié est pris en compte ; un PDF disparu est supprimé de l'index. Les erreurs d'extraction conservent l'ancienne version indexée, s'il en existait une.
- Les **PDF de `Physics_Engine/`** sont indexés sous `source=handbook` (questions techniques OpenSimulator) ; les autres documents sous `source=grid` (grille BloodMoon). Ces deux catégories sont déjà reconnues par la DLL déployée : **aucun redémarrage du bot** et aucune nouvelle DLL ne sont nécessaires.
- Les liens source utilisent le chemin HTTPS public `https://bloodmoonpack.com/files/...`. Vérifier que les PDF sont **destinés à être publics et transmis éventuellement par extraits à un fournisseur IA distant**. Ne pas indexer de secrets, de données privées ou de documents dont la publication n'est pas autorisée.
- Les autres index (sites Web, PDF du guide roleplay, TXT privés) ne sont pas effacés. La synchronisation utilise sa propre table de suivi SQLite `knowledge_files_pdf`.

## Installation BloodMoon existante, sans redémarrage du bot

Pré-requis : `poppler-utils` (`/usr/bin/pdftotext`) et le fichier `knowledge/knowledge_cli.py` issu d'un artefact GitHub Actions **réussi**.

L'artefact contient un installateur : `scripts/install-files-pdfs.sh`, ainsi que `deploy/systemd/opensim-ai-bridge-files-pdfs.service.example` et `deploy/systemd/opensim-ai-bridge-files-pdfs.timer.example`.

```bash
sudo bash scripts/install-files-pdfs.sh <DOSSIER_ARTIFACT_EXTRAIT>
```

Il sauvegarde l'indexeur Python précédent, installe l'importeur, vérifie sa syntaxe, configure un service oneshot distinct et un timer **toutes les 5 minutes**, puis déclenche la première indexation. Il ne redémarre ni les bots, ni ROBUST, ni les simulateurs.

Pour vérifier l'indexation :

```bash
systemctl status opensim-ai-bridge-files-pdfs.service opensim-ai-bridge-files-pdfs.timer --no-pager
journalctl -u opensim-ai-bridge-files-pdfs.service -n 80 --no-pager
python3 /home/louna49400/OpenSim-AI-Bridge/knowledge/knowledge_cli.py status
python3 /home/louna49400/OpenSim-AI-Bridge/knowledge/knowledge_cli.py search "uBODE moteur physique"
```

Une recherche IM sur uBODE doit désormais pouvoir sélectionner les documents techniques. Un scan PDF composé uniquement d'images n'aura pas de texte extractible : le journal affichera une erreur et un OCR externe sera nécessaire.

**Attention aux accès :** le service fonctionne avec l'utilisateur Linux du bot, et cet utilisateur doit avoir la permission de traverser les sous-répertoires et lire les PDF. Ne pas élargir les droits d'accès à des dossiers privés pour contourner un refus. Vérifier les permissions avant déploiement.

## Retour arrière

Arrêter puis désactiver le timer et le service PDF. Restaurer la sauvegarde `knowledge_cli.py.bak-...` créée par l'installateur si nécessaire. Les pages déjà importées restent dans SQLite tant qu'elles ne sont pas explicitement supprimées. Ne supprimer ni la base SQLite ni les index des autres sources.
