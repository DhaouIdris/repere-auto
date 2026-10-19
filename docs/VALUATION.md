# Valorisation et limites statistiques

La cible est un **prix demandé dans des annonces comparables**. Ni prix de transaction, ni rentabilité, ni qualité mécanique ne sont observés.

## Référence

Même marque, modèle, génération, finition, moteur, carburant, boîte, catégorie de vendeur et région après normalisation. L'année peut différer d'un an et le kilométrage de 20 000 km au maximum. Ces fenêtres peuvent être modifiées dans `Rules`, mais ne constituent pas des paramètres universellement optimaux. Aucun mélange particulier/professionnel ni ajustement appris implicite.

La complétude requise est explicite. Si un champ de signature manque, l'estimation s'abstient. Le Crit'Air n'est jamais déduit de l'année seule. La connaissance du code moteur ne prouve pas qu'un libellé source a été correctement attribué : l'import et l'évaluation sur données annotées restent indispensables.

Le candidat et toutes ses republications probables sont exclus. Chaque groupe de référence contribue une seule fois, à travers sa dernière observation connue à la date d'estimation, avec un départage déterministe. Les prix inférieurs à 1 000 €, annonces endommagées, pour pièces, liées à un financement ou trop anciennes ne servent pas de références.

La référence est la médiane de ces prix. L'intervalle affiché représente les quartiles observés Q25–Q75. Il n'est pas un intervalle de prédiction ni de confiance. La dispersion est `(Q75 − Q25) / médiane`. La sensibilité affichée recalcule la médiane après suppression de chaque référence à tour de rôle.

La remise nominale est `(référence − prix demandé) / référence × 100`. Exemple : 9 200 € contre 11 000 € donne 16,36 %. Un véhicule est retenu seulement si la remise atteint le seuil configuré, les références sont suffisantes et peu dispersées, l'observation est fraîche, la publication récente connue et les drapeaux de risque non bloquants. Un écart supérieur à 60 % est signalé et exclu.

## Paramètres par défaut

6 références effectives, remise 15 %, dispersion maximale 0,25, observation de moins de 14 jours, publication de moins de 30 jours. « Élevée » désigne au moins 12 références et une dispersion maximale de 0,12 ; sinon « modérée » si les limites sont respectées. Ces termes sont descriptifs, sans probabilité de fiabilité associée.

## Évaluation temporelle

```sh
python -m repere --db data/repere-import.sqlite --mode import evaluate \
  --cutoff 2026-09-01T00:00:00Z --as-of 2026-10-01T00:00:00Z
```

Les observations du holdout sont postérieures au cutoff. Les groupes du holdout sont retirés de l'entraînement, même s'ils apparaissent auparavant. Une seule observation par groupe est évaluée. Les références futures sont impossibles. Le rapport donne MAE, RMSE, erreur absolue médiane, taux d'abstention via les effectifs, segments de prix et couverture descriptive Q25–Q75.

Cette évaluation compare aux prix demandés observés. Elle n'est pas validée contre des transactions et la couverture IQR n'est pas calibrée. Les cas sans estimation sont comptés explicitement. Les résultats sur fixtures ne mesurent pas l'erreur sur le marché français. Aucun CatBoost/LightGBM/XGBoost n'est ajouté sans démonstration d'amélioration sur un jeu temporel autorisé.
