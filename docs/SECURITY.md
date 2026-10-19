# Sécurité et confidentialité

MVP privé **mono-utilisateur**. L'utilisateur possédant le code d'accès dispose des mêmes données et recherches que tout autre détenteur de ce code. Ce n'est pas un service multi-tenant ; ne pas présenter un secret partagé comme une séparation de comptes.

## Mesures livrées

- Deux secrets indépendants, 32 caractères minimum, aucun secret de production embarqué.
- Bearer pour les clients scripts ; session HMAC avec expiration de huit heures, cookie HttpOnly/SameSite Strict, Secure en staging/production.
- CSRF exigé pour les écritures par cookie, contrôle d'origine et aucune politique CORS permissive. Dix essais de connexion par minute et adresse du pair, conservés en SQLite ; les proxys peuvent faire partager cette limite au seul compte privé.
- SQL avec paramètres liés ; champs d'import et filtres validés, corps limité à 1 Mio et capacité bornée.
- Rendu des annonces avec `textContent`, CSP sans script inline, liens HTTPS sans identifiants, sans adresses IP/locales ; aucun fetch d'URL d'annonce ou d'image.
- Logs applicatifs structurés par identifiant de requête, méthode, statut et durée, sans corps d'import ni code d'accès. Les erreurs inattendues n'exposent pas la requête SQL.
- `.env` et bases ignorés par Git et exclus de l'image. Conteneur sans root, capacités supprimées et système de fichiers applicatif en lecture seule.

## Limites

Le logout efface le cookie du navigateur ; il n'existe pas encore de registre de révocation individuelle des sessions signées. Une session copiée reste valide jusqu'à expiration, sauf rotation de `SESSION_SECRET`. Le chiffrement disque, la gestion de secrets managée, la limitation réseau, les journaux du proxy et les sauvegardes hors machine relèvent du déploiement. Aucun audit d'intrusion indépendant n'a été réalisé.

L'expurgation du texte est un filtre prudent (emails, téléphones français, motifs de VIN/plaque), pas une preuve d'anonymisation. Elle ne détecte pas toute identité ni toute formulation personnelle. Éviter l'import de descriptions contenant des informations personnelles, examiner les licences de contenu et définir la base légale et les obligations d'information pour le cas d'usage réel. Aucune affirmation générale de conformité RGPD n'est faite.

## Suppression et rétention

`DELETE /api/listings/{id}` supprime le groupe de véhicule, ses historiques par cascade et ses événements d'alerte. `DELETE /api/searches/{id}` supprime la recherche et son outbox. La commande `prune --days 90` élimine les annonces non revues et événements anciens. Les références de provenance et statistiques de source peuvent rester ; elles ne doivent pas contenir de données personnelles. Les sauvegardes ont leur propre politique de rétention et doivent être supprimées/renouvelées en conséquence.

## Dépendances et production

Runtime Python minimal : Gunicorn et packaging verrouillés par version et SHA-256. Les dépendances Node servent exclusivement aux tests. Le workflow vérifie tests, audits de dépendances et image. Un scan positif ne prouve pas l'absence de vulnérabilité ; voir les résultats datés dans VALIDATION.md. Avant exposition : TLS, contrôle du domaine, secrets, permissions du volume, restauration et recette sur staging.
