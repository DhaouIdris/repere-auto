# Déploiement préparé, non effectué

Le lancement Python, les tests et le serveur Gunicorn ont été vérifiés localement. Docker, le proxy TLS et l'hébergement cloud n'ont pas été exécutés dans cet environnement : la présence des fichiers n'est pas une preuve de déploiement réussi. Aucun compte, domaine, certificat ni accès serveur n'a été fourni.

## Local avec Docker Compose

1. Copier `.env.example` vers `.env`, générer deux secrets distincts et renseigner `ACCESS_TOKEN` / `SESSION_SECRET`.
2. Garder `APP_ENV=development`, `APP_ORIGIN=http://127.0.0.1:8080`, `DATA_MODE=demo`, `DATABASE_PATH=/data/repere-demo.sqlite`.
3. Construire et lancer : `docker compose up --build -d`.
4. Charger les données : `docker compose exec app python -m repere --db /data/repere-demo.sqlite seed-demo`.
5. Ouvrir l'URL et se connecter avec `ACCESS_TOKEN`.

La base est conservée dans un volume nommé. `docker compose down` conserve les données ; ne pas utiliser `down -v` si elles doivent être conservées.

## Staging et production distincts

Utiliser des répertoires de déploiement, secrets, domaines et volumes indépendants. Exemple staging : `APP_ENV=staging`, `APP_ORIGIN=https://staging.votre-domaine.fr`, `DATA_MODE=import`, `DATABASE_PATH=/data/repere-import.sqlite`. Production : `APP_ENV=production`, autre origine HTTPS et autres secrets. Le mode import démarre vide ; charger seulement des données autorisées.

Construire une image validée, scanner, puis l'identifier par son digest immuable. Le Dockerfile fixe la version Python et les roues Python par hash, mais le tag d'image de base n'est pas un digest : consigner son digest réel lors de la construction de release. Il en va de même du proxy Caddy d'exemple. Les versions et correctifs doivent être revérifiés lors de chaque release.

Définir `REPERE_IMAGE` sur l'image effectivement construite et `DOMAIN` sur un domaine sous votre contrôle, puis :

```sh
docker compose -p repere-staging -f deploy/compose.production.yml up -d
```

Les variables d'interpolation `REPERE_IMAGE` et `DOMAIN` doivent être exportées dans le shell ou passées avec `--env-file`. Le `env_file` du service configure l'application, pas cette interpolation. Le chemin relatif vers `.env` est basé sur le fichier Compose. Ne pas réutiliser le même répertoire et `.env` pour deux environnements distincts.

Le proxy est la seule exposition réseau de cette configuration ; l'application n'a pas de port publié. Configurer le DNS et les ports TLS selon la documentation officielle Caddy : https://caddyserver.com/docs/install et https://caddyserver.com/docs/automatic-https . Aucun certificat n'est préprovisionné par cette livraison.

## Recette et migration

Avant chaque release : tests métier, HTTP et navigateur, audits Python/Node et scan de l'image, backup hors volume, test de restauration. Exécuter en staging les routes `/health`, `/ready`, connexion, refus anonyme, imports invalides/valides, recherche, historique, simulation et redémarrage. Vérifier les cookies Secure et la protection des données sur le domaine réel.

La version de schéma est suivie par `PRAGMA user_version`. La migration initiale est transactionnelle. Une base plus récente que le logiciel est refusée. Les prochaines migrations devront être additives autant que possible ; une restauration n'est pas équivalente à un rollback applicatif sans vérification de compatibilité.

## CI et livraison d'image

`.github/workflows/verify.yml` vérifie les sources, le navigateur, le serveur HTTP, les dépendances et une image Docker. Il n'a pas été exécuté sur GitHub pendant cette livraison. Un workflow manuel de release est fourni pour tester et publier une image versionnée dans GHCR ; ne l'exécuter qu'après avoir choisi un dépôt et vérifié les permissions. Aucun dépôt distant ni registre n'a été créé.

Le déploiement hôte reste une opération explicite : mettre à jour `REPERE_IMAGE`, vérifier les sauvegardes puis relancer Compose. Pour revenir en arrière, rétablir le digest précédent ; si le schéma n'est plus compatible, arrêter l'application et restaurer la sauvegarde testée. Ne pas supprimer les nouvelles données sans stratégie de reprise.

## Capacité et coûts

Budget applicatif : 2 000 annonces/base, lots de 500 et 1 Mio, 20 recherches sauvegardées, pagination 100 maximum, mono-utilisateur, une instance SQLite locale. Ces limites ne constituent pas une garantie de débit ou de disponibilité. Mesurer CPU, latence, écritures, taille et temps de sauvegarde avant augmentation. Pas de partage SQLite sur NFS ni d'instances distribuées.

Coût mensuel à établir après choix de l'hébergeur : calcul + volume + sauvegardes hors site + transfert + domaine + éventuelle licence de données. Aucun tarif d'hébergement ni quota commercial actuel n'a été vérifié ou engagé. La démo n'appelle aucun fournisseur payant ni modèle d'IA.
