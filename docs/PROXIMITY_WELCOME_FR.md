# Accueil automatique des visiteurs — chat local

**Version pilote : 24 novembre 2026.** Cette fonctionnalité utilise le client LibreMetaverse 3.3.1 et fonctionne sans IA, sans appel à Azure, sans IM de bienvenue et sans scripts OSSL dans les régions.

## Principe

Chaque avatar bot peut publier **un message de bienvenue en chat local** lorsqu'un résident entre dans son rayon. **Correctif varregion (24/11/2026) :** la détection lit désormais les positions complètes des avatars dans le cache d'objets LibreMetaverse plutôt que les seules coordonnées *Coarse Location* (8 bits par axe, insuffisantes au-delà de 255 mètres). Les régions telles que BloodMoon_Welcome où le bot est vers X=350, Y=320 sont ainsi prises en compte. Dans l'administration HTTPS, sélectionner l'avatar, ouvrir **Configuration → Accueil automatique des visiteurs**, puis renseigner :

- **Activer l'accueil** (désactivé par défaut, y compris après mise à jour) ;
- **Rayon** : 5–20 mètres, valeur initiale 15 m ;
- **Temporisation par visiteur** : 5–1440 minutes, valeur initiale 30 minutes ;
- **Message de bienvenue**, jusqu'à 650 caractères et 700 octets UTF-8, contenant éventuellement `{avatar_name}`.

Exemple de message par défaut :

> Welcome to BloodMoon, {avatar_name}! I'm your AI assistant, here to answer questions about BloodMoon and its role-playing game. Please send me a private message (IM); I only answer questions via IM, not local chat.

Le nom provient de `client.Avatars.RequestAvatarName` et du retour `UUIDNameReply` (nom classique OpenSimulator). Après trois secondes sans résultat, le bot supprime le placeholder et utilise le texte sans nom ; **aucun UUID n'est affiché dans le chat**. Le plugin Display Names et les noms personnalisés ne sont pas requis.

## Anti-répétition

- Le cache `client.Network.CurrentSim.ObjectsAvatars` est alimenté par les mises à jour `ObjectUpdate` et `ImprovedTerseObjectUpdate` et fournit des positions complètes `Vector3`. Le bot le consulte toutes les 2 secondes, après 12 secondes de stabilisation à la connexion, et uniquement pour sa région active.
- Au premier instantané après connexion, les avatars déjà présents sont considérés comme connus ; aucun accueil en masse.
- Le bot ne se salue jamais lui-même ; les identités sont distinguées par UUID.
- L'entrée dans le rayon déclenche au maximum **un accueil**, qui est mémorisé même si les mises à jour de positions continuent.
- Une absence ou une sortie pendant moins de **30 secondes** ne réarme pas la détection.
- Après une vraie sortie, le même visiteur ne peut être accueilli de nouveau qu'après le délai configuré (30 min par défaut).
- Deux accueils publics du même bot sont espacés d'au moins **8 secondes** ; les arrivées pendant cette période restent candidates aux instantanés suivants.
- La mémoire anti-répétition reste active lors d'une reconnexion du même processus bot, mais **n'est pas persistée après un arrêt/redémarrage complet**. Le premier instantané au redémarrage évite néanmoins un accueil massif.

## Portée et limites techniques

La mesure est en XY, sans filtrer l'étage Z pour conserver le comportement d'origine. Les positions d'avatars assis ou sur un objet mobile méritent un test en situation réelle. Une autre personne sur un étage très différent peut donc déclencher un accueil si elle se trouve au même endroit en plan. Les données ne garantissent pas une détection instantanée : elles dépendent des instantanés envoyés par le simulateur OpenSimulator.

`Self.Chat(message, 0, ChatType.Normal)` envoie sur le canal 0 en chat normal, **pas en IM**. Le rayon est limité à 20 m pour rester cohérent avec le chat normal usuel ; la portée effective dépend des paramètres de la région.

La recherche des noms par paquet UUID n'assure pas le retour du *Display Name*. Les bots voisins peuvent chacun souhaiter la bienvenue à un résident si leur rayon est traversé ; aucune coordination entre bots distincts n'est encore implémentée.

## Installation / vérification

1. Faire une sauvegarde des binaires et configurations des bots existants, ainsi que de `controller/control.py` et de la page `web/OpenSim_AI/index.php`.
2. Utiliser un artefact GitHub Actions **réussi**, puis installer le nouveau `OpenSimAiBridge.Bot.dll`, la nouvelle page PHP et le contrôleur Python.
3. Laisser l'option **désactivée** tant que l'avatar est en production. Vérifier le contrôleur et exécuter `dotnet OpenSimAiBridge.Bot.dll --verify-welcome` hors connexion.
4. Activer le module uniquement pour un avatar en région de test, enregistrer sa configuration, **redémarrer cet avatar**.
5. Tester : résident déjà présent au démarrage → silence ; arrivée à 15 mètres → une annonce en chat local ; attente à proximité → aucune répétition ; sortie puis retour rapide → silence ; retour après délai → nouvel accueil.

Il reste indispensable de valider les paquets de positions et l'émission chat avec la version OpenSimulator du serveur concerné. **Un build CI vert ne remplace pas les tests réels en région.**

Les journaux comportent un message `Proximity welcome: observing N avatar objects around position ...` environ une fois par minute lorsque la fonction est active, ce qui permet de vérifier que les données de présence parviennent effectivement au client. `N=0` lors d'une présence connue en région suggère de vérifier le flux d'objets, la connexion du bot et le mode de suivi LibreMetaverse.
