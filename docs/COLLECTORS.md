# Connecter un scraper à Repère Auto

## Fonctionnement livré

Un scraper externe dépose ses résultats dans une tâche Apify configurée par l'utilisateur. Repère Auto appelle seulement deux ressources documentées : le dernier run `SUCCEEDED` de cette tâche, puis les lignes de son dataset. Il ne lance pas d'Actor, ne s'authentifie sur aucune marketplace et ne choisit aucun proxy. Le scraper, ses paramètres, ses autorisations, ses quotas et son calendrier restent à configurer chez le fournisseur.

Le raccordement est implémenté pour les quatre sources déjà prises en charge par la base : **Leboncoin, La Centrale, AutoScout24 France, ParuVendu**. Il reconnaît les champs structurés usuels ; cela ne garantit pas la compatibilité avec tous les Actors de l'Apify Store. Un scraper fournissant seulement un titre, un prix formaté ambigu ou une URL sans identifiant ne suffit pas. La compatibilité se vérifie sur la sortie du scraper choisi, et se complète par `field_map`.

## Accès aux données et coûts

Les CGU Leboncoin et La Centrale demandent une autorisation pour les extractions/réutilisations visées. Aucun accord ni accès partenaire n'a été obtenu pour ce projet. L'API ou l'abonnement d'un prestataire de scraping ne prouve pas les droits sur les annonces. Activer `authorized` seulement en disposant effectivement des droits nécessaires, et renseigner leur référence ; le logiciel ne certifie pas cette déclaration.

Il faut un compte Apify, un jeton autorisé à lire la tâche et son dataset, une tâche sauvegardée et au moins un run terminé avec succès. Les Actors peuvent être payants. Vérifier leur tarification et configurer un plafond avant une exécution. Repère Auto n'en démarre aucune : ses requêtes sont uniquement des GET de lecture. La facturation éventuelle et la planification du scraper relèvent du fournisseur.

## Première connexion sous Windows

Arrêter la démo avec Ctrl+C. Télécharger la version incluant ces fichiers, puis ouvrir PowerShell dans le dossier du projet.

1. Dans Apify, créer une tâche avec le scraper choisi et une recherche **de voitures situées en France**, ciblée sur une marque/modèle ou une zone. Commencer avec 50 à 100 annonces, un montant maximal par exécution et une fréquence modérée adaptée à l'accord d'accès. Pour AutoScout24, demander explicitement `FR` ; une recherche européenne ne convient pas.
2. Dans le cadre de vos droits d'accès, exécuter la tâche et vérifier son statut `SUCCEEDED`. Identifier son **Task ID**, pas l'Actor ID ni le Dataset ID. Les sorties doivent contenir les champs indiqués plus bas. Désactiver les options de collecte des téléphones et contacts lorsqu'elles existent.
3. Préparer la configuration locale :

```powershell
Copy-Item examples/collectors.apify.example.json collectors.local.json
notepad collectors.local.json
```

Dans l'entrée de la source choisie, renseigner `task_id`, passer `enabled` et `authorized` à `true`, et remplacer `rights_reference` par la référence réelle des droits. Laisser les autres sources désactivées. Exemple de structure, **sans accès ni autorisation fournis par cet exemple** :

```json
{
  "schema_version": 1,
  "sources": [{
    "source": "leboncoin",
    "enabled": true,
    "task_id": "VOTRE_TASK_ID",
    "authorized": true,
    "rights_reference": "REFERENCE_REELLE_DE_VOTRE_AUTORISATION",
    "max_items": 100
  }]
}
```

4. Saisir le jeton API dans le terminal. Ne pas le mettre dans le JSON, dans GitHub ou dans une conversation :

```powershell
$env:APIFY_TOKEN = Read-Host "Jeton API Apify"
py -m repere collect --config collectors.local.json --check
py -m repere live --config collectors.local.json
```

Le contrôle `--check` vérifie uniquement la configuration, sans accès réseau ni création de base. `live` crée une base en mode import sous `data/repere-import.sqlite`, démarre le serveur local et lit Apify en arrière-plan. Ouvrir l'URL localhost et saisir son code temporaire ; le code change à chaque lancement. L'application démarre même si Apify est momentanément indisponible : les erreurs apparaissent dans le terminal et dans **Sources & imports**. La première lecture peut prendre plusieurs dizaines de secondes.

Le tableau de bord et les statuts des sources se rafraîchissent toutes les 30 secondes lorsque leur page est visible. Les annonces importées se consultent dans **Explorer les annonces** ; appliquer à nouveau les filtres ou ouvrir cette page après une collecte. Une tâche vide, un quota dépassé ou un schéma incompatible est affiché explicitement.

La lecture se répète toutes les 900 secondes. Pour changer ce délai ou utiliser un autre port :

```powershell
py -m repere live --config collectors.local.json --interval 1800 --port 8090
```

Ce délai concerne la **lecture** ; il ne programme aucune extraction. Planifier le scraper dans Apify pour produire de nouveaux runs selon votre accord et votre budget. Arrêter avec Ctrl+C. `APIFY_TOKEN` disparaît à la fermeture de cette session PowerShell. Le CLI ne charge pas automatiquement `.env`.

## Champs et adaptation

| Champ stocké | Champs structurés reconnus, entre autres |
|---|---|
| Identifiant stable | `source_id`, `list_id`, `id`, `listingId`, `adId` |
| URL de l'annonce | `url`, `listingUrl`, `adUrl`, domaine cohérent avec la source |
| Marque / modèle | `brand` / `model`, `make` / `model`, `marque` / `modele`, attributs Leboncoin |
| Prix comptant EUR | `price_eur`, `prix`, `price.amount`, `price.value`, `price`, tableau à un prix |
| Kilométrage | `mileage_km`, `mileageKm`, `kilometrage`, `mileage`, attribut Leboncoin |
| Année et mois | `year`, `annee`, `regdate`, ou `firstRegistration` au format `AAAA-MM` |
| Énergie / boîte | `fuel`, `fuelType`, `energie` ; `gearbox`, `transmission`, `boite` |
| Vendeur | `seller.type`, `sellerType`, `type_vendeur`, `owner.type` ; seul le type est conservé |
| Localisation | Champs explicites de ville, code postal, département, région ; pas de géocodage |
| Comparabilité | `generation`, `trim` / `finition`, `engine` / `motorisation`, `condition` explicites |
| Dates | `published_at`, `first_publication_date`, `publishedAt`, `datePublished` ; `observed_at`, `scrapedAt`, `scraped_at` |

`field_map` dans une source remplace les chemins d'un champ, avec indices de tableau possibles. Un chemin absent laisse le champ inconnu. Exemple :

```json
"field_map": {
  "price_eur": ["vehicle.cashPrice.amount", "price.0"],
  "generation": "vehicle.generation",
  "engine": "vehicle.engineName",
  "published_at": "dates.publishedAt"
}
```

Les formats monétaires ambigus, devises étrangères, pays étrangers, dates futures, identifiants répétés, valeurs non finies et clés JSON dupliquées sont rejetés. L'ensemble du lot d'une source est validé avant import ; une erreur ne supprime aucune donnée précédente et n'empêche pas les autres sources de se synchroniser. Un dataset de plus de `max_items` est refusé sans import partiel : limiter le scraper ou scinder ses recherches. Une configuration par source est actuellement permise.

Les URL AutoScout24 `.com` sont acceptées uniquement par le collecteur si le pays est explicitement France. Les autres URL restent contrôlées par domaine. Le client réseau ne contacte que `https://api.apify.com`, refuse les redirections et ne transmet le jeton que dans l'en-tête Authorization. Délai maximal de 20 secondes par requête, pages de 100 lignes, réponse limitée à 2 Mio, 500 lignes maximum par tâche. Un échec/quota attend le cycle suivant ; aucun retry agressif.

## Dates, prix et signaux

La date d'observation propre à la ligne est conservée lorsqu'elle est fournie. À défaut, la fin du run est utilisée comme **approximation documentée de l'observation**, pas l'heure d'import. Cette approximation ne démontre pas qu'une ancienne ligne du dataset a été revérifiée. Privilégier les scrapers donnant un horodatage par annonce.

Relire un run déjà importé ne rajeunit pas les annonces, n'ajoute pas d'historique et ne change pas `last_seen`. `collect --force` permet de relire le même dataset pour corriger une correspondance de champs ; les règles habituelles restent applicables : un contenu différent avec la même date d'observation est refusé. Pour cette correction, utiliser une nouvelle base ou obtenir une nouvelle observation du scraper, sans réécrire son horodatage artificiellement.

Les dates affichées sous forme « aujourd'hui » sans fuseau restent inconnues. Le titre n'est pas découpé pour inventer une motorisation, une génération ou une finition ; une version commerciale n'est pas automatiquement une finition. Une puissance DIN n'est pas une puissance fiscale. L'état n'est jamais supposé « normal ». Contacts, noms de vendeurs, VIN, plaques, descriptions libres et images du scraper sont exclus de la projection importée. Les réponses brutes ne sont ni enregistrées ni journalisées.

Une vraie annonce peut donc apparaître sans estimation : la baseline exige toujours les champs structurés nécessaires, assez de références compatibles et des observations récentes. Un manque de données ne devient pas une bonne affaire. Le connecteur respecte la limite existante de 2 000 annonces par base ; appliquer la rétention avant de dépasser cette capacité. L'absence d'une annonce du dernier dataset ne prouve pas sa vente et ne provoque pas sa suppression.

Les annonces, leur historique, les alertes en attente et le checkpoint d'un résultat sont validés dans une transaction SQLite commune. Le connecteur ne livre aucun message Telegram ; l'envoi reste une commande distincte. La commande `live` est un serveur de développement local, pas un déploiement public. Pour une exploitation sur serveur, utiliser le mode import avec Gunicorn et exécuter `collect` dans un ordonnanceur avec exclusion mutuelle.

## Validation de cette livraison

- 92 tests Python réussis localement, dont 24 nouveaux : projection des trois formats principaux avec fixtures entièrement inventées, pagination, erreurs de jeton/quota, refus des redirections, isolation des sources, replay sans rajeunissement, variations de prix et rollback commun avec les alertes.
- Lancement `live` testé avec un client fournisseur simulé, une base temporaire et un arrêt contrôlé.
- Neuf groupes de vérifications navigateur réussis localement, dont le parcours d'une fixture de scraper importée vers le statut de source et la liste des véhicules. Test HTTP Gunicorn réussi. Ces parcours ne constituent pas une validation de données réelles.
- Aucun compte Apify, jeton réel, exécution d'Actor payante ni jeu réel de marketplace utilisé. La compatibilité exacte du scraper choisi et l'accès réseau authentifié restent à valider lors de la configuration utilisateur.
- ParuVendu utilise le même raccordement configurable ; aucun schéma de scraper ParuVendu ni accès réel n'a été validé.

## Références consultées le 19 octobre 2026

- API officielle Apify, dernière tâche : https://docs.apify.com/api/v2/actor-task-runs-last-get
- API officielle Apify, lignes et pagination : https://docs.apify.com/api/v2/dataset-items-get
- CGU Leboncoin : https://www.leboncoin.fr/dc/cgu
- CGU La Centrale : https://www.lacentrale.fr/informations/mentions-legales
- CGU AutoScout24 : https://www.autoscout24.fr/entreprise/agb/

Les noms de champs usuels ont été vérifiés sur des pages publiques de fournisseurs ; aucun code de scraper ni exemple d'annonce de ces pages n'est repris dans les fixtures.
