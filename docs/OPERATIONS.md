# Exploitation

## Santé et observabilité

`/health` est une liveness. `/ready` ouvre la base et contrôle le mode et la version du schéma. `/api/metrics` exige l'authentification et donne les volumes et états de l'outbox. Les logs applicatifs indiquent requête, statut et durée ; le registre des sources conserve tentatives, succès et erreurs d'import. Surveiller readiness, taux d'erreur, latence et ancienneté des imports. La supervision externe et les alertes d'infrastructure sont à configurer sur l'hébergement.

## Jobs

Les imports sont explicites, jamais une collecte automatique de pages. La commande suivante réévalue les recherches et prévisualise l'outbox :

```sh
python -m repere --db /data/repere-import.sqlite --mode import alerts --transport simulation
```

Elle exige les variables de configuration du serveur (secrets et mode compris), n'envoie rien et ne marque aucun message livré. Pour activer le transport externe, configurer `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`, vérifier le destinataire et utiliser volontairement `--transport telegram`. Les annonces synthétiques ne peuvent pas être envoyées par ce transport.

Un planificateur hôte peut lancer cette commande toutes les cinq minutes, avec le même environnement et un verrou de job (`flock`, systemd timer ou orchestrateur adapté). Le fichier `deploy/cron.example` illustre une exécution dans Compose ; il n'est pas installé automatiquement. La durée d'une requête Telegram est bornée à 12 secondes ; les erreurs temporaires sont replanifiées, au plus six tentatives, avec backoff exponentiel. HTTP 400/401/403/404 passe en échec terminal ; une réponse réseau ambiguë requiert un contrôle manuel. Corriger les credentials avant de réarmer un événement échoué.

## Idempotence et limites d'envoi

Une clé unique couvre recherche + groupe probable + prix. Après une première correspondance, une nouvelle alerte exige une baisse significative (3 % par défaut) et respecte le cooldown de 24 h, tous deux configurables. L'écriture de l'outbox et la revendication du message sont transactionnelles. L'échec d'un message ne marque pas les autres livrés.

La livraison à un service externe n'est pas transactionnelle avec SQLite. Chaque réservation possède un jeton propriétaire et un bail calculé à son début. Un worker ayant perdu sa réservation ne peut pas confirmer ni replanifier le message. Un bail expiré passe en échec ambigu et n'est pas repris automatiquement : Telegram peut déjà avoir livré le message. Vérifier les événements ambigus avant tout réarmement manuel ; ce réarmement peut produire un doublon. Le système ne garantit **pas un effet externe exactement une fois dans tous les scénarios de panne**. La simulation n'est pas une preuve d'envoi Telegram réel.

Les messages en attente sont annulés lorsque leur prix ou leurs critères ne correspondent plus aux données actuelles. La livraison revalide aussi l'éligibilité et actualise l'estimation du message. Une modification des données pendant l'appel externe ne peut pas être atomique avec cet appel. Voir [PHASE1_VALIDATION.md](PHASE1_VALIDATION.md) avant migration d'une base existante.

## Sauvegarde et restauration

```sh
python -m repere --db /data/repere-import.sqlite --mode import backup /backups/repere-2026-10-19.sqlite
```

La sauvegarde utilise l'API SQLite cohérente, vérifie `integrity_check` et refuse d'écraser une destination existante. Copier ensuite hors machine avec permissions et chiffrement adaptés. Pour restaurer : arrêter tous les accès à la base, conserver la base actuelle comme secours, remplacer le fichier par la sauvegarde, éliminer les anciens fichiers WAL/SHM seulement après arrêt complet, rétablir propriétaire/permissions, vérifier `integrity_check`, redémarrer et exécuter la recette. Ne pas copier à chaud uniquement le fichier principal d'une base WAL.

Un test de backup/restauration locale est livré ; la restauration sur le volume et la machine de production reste à répéter. Établir un objectif de perte et de reprise selon votre usage ; aucun RPO/RTO contractuel n'est revendiqué.

## Rétention et incident

`prune --days 90` supprime annonces non revues, historique associé et événements anciens. Planifier cette commande séparément et définir la durée des sauvegardes ; une suppression active n'efface pas les anciennes sauvegardes. Export autorisé mal formé : corriger le contrat ou la ligne signalée, sans contourner la validation. Source live indisponible : obtenir le canal autorisé, pas multiplier les tentatives. Fuite de secret : changer les deux secrets, invalider les sessions, examiner les accès et renouveler les accès Telegram concernés.
