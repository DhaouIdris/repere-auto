# Sources et droits

Décision au 19 octobre 2026 : toutes les connexions live sont indisponibles. Aucun scraping n'a été implémenté. Les documents primaires ci-dessous ont été consultés lors de l'audit du 18 octobre ; leur contenu n'est pas présenté comme un contrat de licence accordé au projet.

| Source | Constat de la revue | État du logiciel |
|---|---|---|
| Leboncoin | Les CGU encadrent extraction, réutilisation et robots, avec autorisation préalable | Connecteur live absent ; import autorisé seulement |
| La Centrale | Les mentions/CGU soumettent l'extraction et la réutilisation hors consultation à accord écrit | Connecteur live absent ; import autorisé seulement |
| AutoScout24 France | Mentions restrictives, restrictions robots sur des routes de recherche/API ; portail partenaire réel, sans accès accordé au projet | Connecteur live absent ; intégration partenaire à négocier |
| ParuVendu | Conditions consultées ; aucune permission ni API/flux sous licence vérifiés | Connecteur live absent ; autorisation à établir |

Robots Leboncoin et AutoScout24 ont été récupérés. Ceux de La Centrale et ParuVendu n'ont pas pu être récupérés par l'outil de consultation ; cela ne signifie ni absence de fichier ni autorisation. Une règle robots permissive ne vaut pas licence de réutilisation. L'existence d'une offre partenaire ne signifie pas que le projet en bénéficie.

## Références officielles

- https://www.leboncoin.fr/dc/cgu et https://www.leboncoin.fr/robots.txt
- https://www.lacentrale.fr/informations/mentions-legales et https://www.lacentrale.fr/robots.txt
- https://www.autoscout24.fr/entreprise/mentions-legales/ et https://www.autoscout24.fr/robots.txt
- https://www.autoscout24.fr/partner-infoportal/schnittstellen/
- https://www.paruvendu.fr/pa/informations-legales et https://www.paruvendu.fr/robots.txt

## Accès permis par l'application

Les seuls adaptateurs actifs lisent des données synthétiques ou des fichiers locaux soumis volontairement par l'utilisateur. L'import exige une autorisation déclarée et une référence de provenance. Cette déclaration ne prouve pas juridiquement les droits ; conserver le contrat ou l'accord correspondant et vérifier sa portée sur les descriptions, images, durée de conservation et finalités. Un export manuel n'efface pas les droits éventuels de la plateforme.

L'application ne contourne ni CAPTCHA, ni authentification, ni restrictions d'accès. Elle n'utilise ni API privée ni identité de navigateur pour extraire des annonces. Les liens externes sont des liens HTTPS d'ouverture volontaire ; le serveur ne télécharge pas leurs contenus. Les références d'images sont conservées uniquement après déclaration de droits, sans téléchargement, affichage ou traitement IA.

Le mail envoyé à l'auteur du dépôt amont reste sans réponse connue de l'application. Le code de ce nouveau dossier est indépendant ; aucune autorisation sur l'ancien code n'est supposée acquise.

## Activation future d'une source

Exiger un canal documenté, contrat/autorisation, périmètre des usages, quotas, schéma, droits sur images/textes, dates d'expiration et fixtures autorisées. Revalider les documents, implémenter des limites et une politique de retry compatible avec le contrat, puis tester réellement le canal avant d'afficher « supporté ». Ne pas assimiler le registre actuel à un connecteur réseau prêt à activer.
