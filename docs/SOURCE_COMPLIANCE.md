# Sources et droits

Décision au 19 octobre 2026 : aucun accès direct ou partenaire aux marketplaces n'est accordé au projet. Un raccordement aux résultats de scrapers externes via l'API officielle Apify est implémenté, sans jeton ni exécution réelle. Les droits demeurent à établir avant activation ; un prestataire de scraping ne les confère pas automatiquement. Les CGU Leboncoin, La Centrale et AutoScout24 ont été reconsultées le 19 octobre. Lire [COLLECTORS.md](COLLECTORS.md) pour les modalités et limites exactes.

| Source | Constat de la revue | État du logiciel |
|---|---|---|
| Leboncoin | Les CGU encadrent extraction, réutilisation et robots, avec autorisation préalable | Lecteur Apify configurable ; aucun accès direct ni droit fourni |
| La Centrale | Les mentions/CGU soumettent l'extraction et la réutilisation hors consultation à accord écrit | Lecteur Apify configurable ; aucun accès direct ni droit fourni |
| AutoScout24 France | Mentions restrictives, restrictions robots sur des routes de recherche/API ; portail partenaire réel, sans accès accordé au projet | Lecteur Apify configurable ; aucun accès partenaire fourni |
| ParuVendu | Conditions consultées ; aucune permission ni API/flux sous licence vérifiés | Lecteur Apify générique ; schéma du scraper et accès non validés |

Robots Leboncoin et AutoScout24 ont été récupérés. Ceux de La Centrale et ParuVendu n'ont pas pu être récupérés par l'outil de consultation ; cela ne signifie ni absence de fichier ni autorisation. Une règle robots permissive ne vaut pas licence de réutilisation. L'existence d'une offre partenaire ne signifie pas que le projet en bénéficie.

## Références officielles

- https://www.leboncoin.fr/dc/cgu et https://www.leboncoin.fr/robots.txt
- https://www.lacentrale.fr/informations/mentions-legales et https://www.lacentrale.fr/robots.txt
- https://www.autoscout24.fr/entreprise/mentions-legales/ et https://www.autoscout24.fr/robots.txt
- https://www.autoscout24.fr/partner-infoportal/schnittstellen/
- https://www.paruvendu.fr/pa/informations-legales et https://www.paruvendu.fr/robots.txt

## Accès permis par l'application

Les adaptateurs lisent des données synthétiques, des fichiers soumis volontairement et, après configuration explicite, les datasets de tâches Apify terminées avec succès. L'import exige une autorisation déclarée et une référence de provenance. Cette déclaration ne prouve pas juridiquement les droits ; conserver le contrat ou l'accord correspondant et vérifier sa portée, sa durée et ses finalités. Les contacts, textes libres et images sont exclus de l'import des datasets. Un export manuel ou une clé de prestataire n'efface pas les droits éventuels de la plateforme.

L'application ne contourne ni CAPTCHA, ni authentification, ni restrictions d'accès. Elle n'utilise ni API privée ni identité de navigateur pour extraire des annonces. Les liens externes sont des liens HTTPS d'ouverture volontaire ; le serveur ne télécharge pas leurs contenus. Les références d'images sont conservées uniquement après déclaration de droits, sans téléchargement, affichage ou traitement IA.

Le connecteur Apify ne démarre pas de tâche et n'accède pas aux endpoints des marketplaces. Le choix et l'exécution du scraper externe restent à la charge de l'utilisateur, dans le cadre de ses autorisations.

Le mail envoyé à l'auteur du dépôt amont reste sans réponse connue de l'application. Le code de ce nouveau dossier est indépendant ; aucune autorisation sur l'ancien code n'est supposée acquise.

## Activation future d'une source

Exiger un canal documenté, contrat/autorisation, périmètre des usages, quotas, schéma, droits sur images/textes, dates d'expiration et fixtures autorisées. Revalider les documents, implémenter des limites et une politique de retry compatible avec le contrat, puis tester réellement le canal avant d'afficher « supporté ». Ne pas assimiler le registre actuel à un connecteur réseau prêt à activer.
