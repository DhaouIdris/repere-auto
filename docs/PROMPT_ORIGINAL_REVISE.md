# Prompt de réalisation originale — Repère Auto

Tu es responsable de concevoir, écrire, exécuter et tester une application originale de comparaison des prix demandés de voitures d'occasion en France. Produis un projet utilisable, avec son code, ses tests et ses procédures de lancement et d'exploitation. Ne te limite pas à un document d'architecture.

## Origine et limites de réutilisation

Le projet https://github.com/Dropio12/used-car-deal-finder sert uniquement de référence fonctionnelle et de contexte d'audit. Son auteur a été contacté ; aucune autorisation de réutilisation n'est supposée acquise. Ne copie, ne traduis et ne porte aucun de ses fichiers, modules, tests, schémas, styles, médias ou fixtures. N'utilise pas un changement de langage ou de noms comme justification d'originalité. Les idées générales — comparer des annonces, employer une médiane, recevoir des alertes — peuvent être reformulées et implémentées indépendamment. Si la source a été consultée, ne prétends pas avoir travaillé en clean room stricte.

Écris dans un dossier distinct, choisis la pile la plus simple justifiée par l'usage et vérifie les licences des dépendances. Documente l'origine des composants et les limites réelles de ton analyse ; aucune certification juridique générale ne doit être inventée. Une éventuelle future autorisation sur le code amont est indépendante des droits d'accès aux annonces.

## Produit attendu

Interface française privée : tableau de bord, recherche multicritère, détail du véhicule, historique des prix, références comparables, recherches sauvegardées, journal d'alertes et monitoring des sources. EUR, kilomètres et géographie métropolitaine. Affiche clairement chargement, vide, erreur, données périmées et sources indisponibles. Une annonce synthétique ne doit jamais passer pour une offre réelle.

Commence par un parcours démo/import totalement autonome. Les cibles Leboncoin, La Centrale, AutoScout24 et ParuVendu ne deviennent des intégrations supportées qu'après vérification documentaire et test réussi sur un canal autorisé. Préférer API officielles, flux licenciés ou exports avec droits établis. Ne contourne aucun CAPTCHA, authentification, robots ou restriction d'accès ; n'imite pas une autre identité et n'abuse pas d'API privée. Une interdiction ou absence d'autorisation désactive la source correspondante, sans empêcher le développement du mode synthétique.

## Contrat de données

Modèle typé et versionné : source et identifiant source, URL, marque/modèle/génération/finition/moteur, immatriculation année/mois, kilométrage, prix en centimes EUR, carburant, boîte, puissances avec unités distinctes, Crit'Air seulement si fiable, ville/code postal/département/région, vendeur particulier/professionnel, dates de publication et observation, historique, état/défauts et informations déclarées d'entretien/contrôle technique/accident/garantie, provenance, champs manquants et drapeaux de qualité.

N'invente aucun champ manquant. Valide les imports avant écriture, avec erreur compréhensible par ligne et rejet atomique des lots invalides. Sépare les bases synthétiques et réelles. Une clé `(source, source_id)` protège l'annonce ; un groupe distinct de véhicule probable traite les republications et doublons interplateformes. Documente faux positifs et faux négatifs possibles. Préserve l'historique et empêche les anciennes observations d'écraser les nouvelles.

Évite nom/contact vendeur, VIN et plaque ; examine aussi les contenus libres et les droits sur les photos. N'assimile ni contenu public ni déclaration de l'utilisateur à une preuve générale de conformité RGPD.

## Valorisation

Commence par une statistique transparente et explicable. Exige la compatibilité du modèle, de la génération, du moteur, de la finition, du carburant, de la boîte, du vendeur et de l'état ; fenêtres d'année/km et géographie justifiées. Exclue le candidat et toutes ses republications de leur propre référence. Un véhicule probable ne compte qu'une fois. Aucune observation future dans une estimation historique.

Retourne médiane de prix demandés, quartiles observés, remise EUR/%, effectif réel, dispersion, fraîcheur, motifs et abstention lorsque les données ne suffisent pas. Les quartiles ne sont pas des intervalles de confiance calibrés. Le mot « confiance » doit être clairement défini. Ajoute une analyse de sensibilité de la médiane. Ne transforme pas une remise en promesse de bon achat ou de profit : défauts, frais et transactions finales ne sont pas connus.

Règles configurables : remise initiale 15 %, effectif minimum, dispersion maximale, observation récente, absence de dommages/vente pour pièces/prix conditionné au financement et qualité de données suffisante. Ces seuils sont à évaluer, pas universels. Pas de ML sans amélioration démontrée sur une référence statistique. Fournis une évaluation temporelle à groupes disjoints avec MAE, RMSE, erreur médiane, segments et abstentions ; les résultats synthétiques ne prouvent pas une performance réelle.

## Alertes, sécurité et exploitation

Recherches privées et filtres de budget, véhicule et rayon. Outbox durable avec unicité des événements, cooldown, baisse significative, livraison suivie par message, retries bornés, timeout et reprise après échec. La simulation ne doit pas consommer les envois réels. N'invente pas une garantie exactement une fois lorsque le service externe ne la permet pas.

Authentification réelle, contrôle du périmètre utilisateur, secrets hors Git, CSRF pour les sessions web, validation, SQL paramétré, URLs sûres, limites d'entrée et capacité explicites. Logs et métriques sans secrets, liveness et readiness distinctes, migration, backup/restauration testée, rétention et suppression. L'analyse d'images IA est optionnelle, désactivée sans droits et jeu d'évaluation approprié.

## Recette et livraison

Teste la normalisation, les champs absents, imports malformés, schémas inconnus, doublons, fuite temporelle, auto-influence, groupes rares, médiane/remise, filtres et distance. Teste aussi persistence, API, sessions, CSRF, base vide, limites de taille, rate limits, notifications partielles, concurrence, credentials expirés, reprise et restauration. Un parcours réel doit aller de l'ingestion synthétique à l'API, au classement, à l'affichage et à une alerte simulée. Vérifie desktop/mobile en navigateur lorsque possible.

Fournis README, licence du nouveau code, `.env.example`, configuration locale reproductible, Docker ou équivalent, dépendances verrouillées, CI de tests et scans, environnements isolés, procédures de déploiement, rollback et supervision. Ne déploie pas sur un compte ou un domaine qui n'a pas été configuré. Consigne chaque commande exécutée, résultat et contrôle indisponible. Ne déclare ni couverture, performance, conformité, source supportée ni production prête sans preuve correspondante. Livre le projet complet et une commande de lancement vérifiée.
