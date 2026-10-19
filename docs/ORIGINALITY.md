# Origine du travail

Le besoin fonctionnel est celui du cahier des charges fourni par l'utilisateur : observer les annonces automobiles françaises et comparer leurs prix demandés. Le dépôt https://github.com/Dropio12/used-car-deal-finder a servi à l'audit et à identifier des limites, mais aucun de ses fichiers de code, schémas SQL, fixtures, styles, médias, tests ou déploiement n'a été copié dans ce nouveau projet.

Les fichiers nouveaux sont dans un dossier distinct. Les décisions spécifiques incluent un seul backend Python, un contrat d'import v1 strict, l'abstention sur signature mécanique incomplète, des identités d'annonce séparées des groupes probables, la sensibilité de la médiane, un holdout temporel avec groupes disjoints, et une outbox dont la prévisualisation ne consomme pas les envois.

La syntaxe générale de Python/SQL, les API standard, les algorithmes usuels (médiane, quartiles, HMAC, backoff), le format WSGI et la licence MIT sont des éléments techniques généraux ; aucune exclusivité n'est revendiquée sur ces idées. Les noms de marques automobiles et plateformes identifient les champs ou cibles fonctionnelles ; ils ne signifient ni partenariat ni droit sur leurs bases de données.

Les dépendances tierces conservent leurs propres licences. Le binaire Chromium et Playwright ne sont pas redistribués dans l'archive : leurs références de test sont dans les manifestes. L'inspection préalable du dépôt amont exclut de décrire le processus comme une clean room stricte. Ce document décrit la méthode suivie, pas une certification de non-contrefaçon ou une analyse juridique exhaustive.
