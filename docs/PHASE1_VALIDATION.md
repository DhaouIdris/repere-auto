# Correctifs de fiabilité — phase 1

Base : commit `8fc25d9bd5d43cd2c5aebdf8742f34cb37783ed7`. Travail sur une branche isolée, sans modification de main, déploiement ni envoi Telegram réel.

## Changements

- Empreinte de véhicule normalisée comme la signature de valorisation : les variantes de casse, accents et ponctuation ne créent plus de références distinctes. Prix et dates restent exclus de l'identité. Le rapprochement demeure conservateur : des descriptions ou kilométrages différents peuvent encore nécessiter une résolution ultérieure. Aucun taux de précision réel n'est revendiqué.
- Une observation identique au même instant est ignorée. Un contenu divergent au même instant est rejeté avec rollback de tout le lot. Les observations strictement anciennes restent ignorées.
- Les alertes en attente sont annulées lorsque leurs critères ou prix ne correspondent plus aux données courantes. Chaque livraison revalide la recherche, les références, les risques et la fraîcheur ; son contenu porte la date du calcul actualisé.
- Chaque réservation possède un jeton propriétaire et une échéance calculée au moment de cette réservation. Succès et erreurs sont enregistrés seulement par le propriétaire encore reconnu. Les dates SQL sont comparées chronologiquement, y compris les fractions de seconde.
- Un envoi en cours dont le bail expire passe en échec ambigu avec contrôle manuel. Il n'est pas réémis automatiquement : le service externe peut déjà avoir effectué la livraison. Les échecs temporaires connus conservent leurs retries bornés. Une modification des données survenant après la validation et pendant l'appel externe ne peut pas être annulée atomiquement avec cet appel.
- Image officielle Python 3.12.15 Alpine 3.24, épinglée par digest. Dépendances applicatives inchangées et verrouillées. Le scan HIGH/CRITICAL reste bloquant ; le conteneur complet dispose désormais d'une recette en CI, non-root et avec racine en lecture seule.

## Migration v1 vers v2

Sauvegarder la base avant mise à niveau et arrêter les anciens workers. Le démarrage applique la migration dans une transaction : normalisation des groupes, conservation des historiques de prix et des messages d'alerte, ajout des jetons de réservation et de l'état annulé.

Lorsqu'un regroupement fait converger plusieurs événements identiques, les messages historiques sont conservés, un événement déjà livré prend priorité et les doublons en attente sont annulés. Les anciennes réservations en cours sont signalées comme ambiguës. Un échec de migration restaure le schéma et les données v1 ; ce rollback est testé. Une ancienne version de l'application ne doit pas ouvrir la base v2 : pour revenir en arrière, restaurer la sauvegarde v1.

La migration ne peut pas reconstruire la vérité d'un historique déjà contradictoire : les anciens événements restent conservés et peuvent nécessiter une revue. La conservation de toutes les observations de caractéristiques reste une phase ultérieure.

## Vérifications locales exécutées

19 octobre 2026, Python 3.12.14 et Node 24. Les dépendances de test déjà disponibles ont été réutilisées.

- Référence avant modification : 51 tests Python réussis.
- Reproduction avant correctif : 5 échecs attendus sur 6 scénarios ciblés (doublons, conflit/atomicité, hausse et péremption avant livraison).
- Après correctifs : 68 tests Python réussis, dont migration, rollback, concurrence lente, bail expiré, ancien propriétaire et réactivation d'un événement annulé avant livraison.
- Syntaxe JavaScript : réussie.
- Smoke HTTP réel avec Gunicorn : réussi.
- Navigateur : les huit groupes de contrôles desktop/mobile réussissent.
- Base officielle scannée avec Trivy 0.76.0, téléchargé et vérifié par SHA-256 : zéro signalement HIGH/CRITICAL et zéro secret. Ce résultat concerne la base, et ne remplace pas le scan de l'image applicative complète en CI.

Docker et son socket sont absents de l'environnement local. Les résultats historiques de `docs/VALIDATION.md` décrivent la livraison initiale ; ils ne sont pas réécrits comme de nouvelles exécutions.

## Vérifications GitHub Actions exécutées

[Exécution 39287258674](https://github.com/DhaouIdris/repere-auto/actions/runs/39287258674), code au commit `a527a0e914f2144843a5dd100f7727947e75db47` : job `test` terminé avec succès, toutes les étapes réussies. Les preuves portent sur ce commit ; cette mise à jour de documentation ne change aucun fichier incorporé dans l'image.

- 68 tests Python réussis et huit groupes de contrôles navigateur réussis.
- Smoke HTTP Gunicorn, audits Python/Node et construction Docker réussis.
- Recette du conteneur complet réussie : utilisateur 10001, racine en lecture seule, SQLite et migrations, six opportunités synthétiques, refus de l'accès anonyme.
- Scan Trivy 0.76.0 de l'image applicative : **zéro signalement HIGH/CRITICAL et zéro secret** dans le périmètre configuré. Il s'agit d'un scan de vulnérabilités connues, sans garantie de sécurité exhaustive.
- Image scannée : `sha256:5b0171c177586429020823fca4a41ec695f90626779d0300b236527ba08e3adf`, Alpine 3.24.2.
- Rapport `trivy-image.json` conservé dans l'artefact `image-security-a527a0e914f2144843a5dd100f7727947e75db47` ; archive vérifiée par SHA-256 : `4ace01e08b005e54a0bda8f2fbb38a1c5194500597adffd9745c26d0718efda6`. La rétention GitHub configurée est de 14 jours.

## Commandes de recette

```sh
python -m unittest discover -v
node --check static/app.js
python scripts/http_smoke.py
npm test
docker build --pull -t repere-auto:check .
python scripts/container_smoke.py repere-auto:check
trivy image --severity HIGH,CRITICAL --exit-code 1 repere-auto:check
```

Les connecteurs live, les droits sur les données, la validation statistique réelle et la recette de staging restent hors de cette phase.
