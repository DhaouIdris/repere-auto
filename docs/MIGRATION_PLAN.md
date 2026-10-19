# Correspondance avec le cahier des charges

L'utilisateur a choisi une implémentation originale pendant l'attente de la réponse de l'auteur. Le projet amont n'est donc pas une base de migration ; il reste séparé. Date : 19 octobre 2026.

| Phase initiale | Livraison et limites |
|---|---|
| Audit amont | Réalisé précédemment sur `ebe87fe939cc9abb820764d7da9ea568ca3196ad` ; aucune licence trouvée à cette révision. Rapports antérieurs séparés |
| Modèle français | Contrat versionné, types explicites, EUR centimes, km, région/département/code postal, champs manquants et provenance |
| Ingestion | Démo synthétique, JSON et CSV autorisés ; accès live volontairement indisponibles |
| Valorisation | Médiane explicable, quartiles descriptifs, exclusion du candidat et du groupe, sensibilité et holdout temporel ; pas de ML |
| Détection | Seuils configurables, fraîcheur, état, financement, moteur/génération/finition compatibles, groupes effectifs |
| Frontend | Dashboard, recherche/rayon, fiche/références/historique, recherches sauvegardées, alertes et état des sources |
| Notifications | Outbox, baisse significative, cooldown, reprises et erreurs par message ; transport Telegram écrit et simulé, non validé sur un vrai compte |
| Images IA | Non implémentée, optionnelle ; références d'images autorisées conservables sans téléchargement |
| Sécurité/exploitation | Secrets, sessions, CSRF, validation, SQL lié, logs structurés, readiness, sauvegarde/restauration SQLite et rétention |
| Tests | Résultats exacts et limites dans VALIDATION.md |
| Déploiement | Docker, Gunicorn, proxy TLS et CI fournis ; aucun hébergement ni déploiement public effectué |

## Prochaines étapes justifiées

1. Obtenir un export réel autorisé avec une licence d'usage claire ; l'importer dans une base distincte en mode import. Vérifier les champs, la fraîcheur et les erreurs avant d'exploiter les scores.
2. Valider la comparabilité et le rapprochement sur des annonces françaises annotées, notamment générations, moteurs, vrais doublons et prix conditionnels. Les règles actuelles privilégient l'abstention mais ne garantissent pas une identification parfaite.
3. Mesurer les erreurs sur un holdout temporel de groupes distincts, comparer à un baseline simple et vérifier chaque segment. Ne pas faire des six opportunités synthétiques une mesure de performance économique.
4. Exécuter construction/scan de l'image, configuration TLS, restauration et parcours de staging sur l'hébergement retenu avant toute exposition publique. Les commandes et conditions sont dans DEPLOYMENT.md.
5. Si la charge dépasse les budgets mesurés ou si plusieurs personnes doivent avoir des espaces indépendants : concevoir une authentification par identité, des contrôles par propriétaire, un service de jobs et éventuellement PostgreSQL. Ne pas partager le secret mono-utilisateur entre utilisateurs supposés isolés.
6. Ajouter un connecteur live seulement après contrat, documentation de l'API ou du feed, fixtures autorisées et validation réelle. Ne pas convertir les routes des scrapers canadiens en routes françaises.

Une réponse favorable de l'auteur amont pourra permettre un travail dérivé séparé si les droits sont suffisants ; elle ne rend pas nécessaire l'intégration de son code dans cette nouvelle implémentation.
