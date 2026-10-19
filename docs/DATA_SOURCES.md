# Contrat d'import v1

Les fichiers `examples/demo.json`, `examples/demo.csv` et `examples/csv-envelope.json` contiennent uniquement des données inventées. Les métadonnées les étiquettent comme `demo`. La génération complète est dans `repere/demo.py` et n'utilise aucune annonce, photo ou identifiant de marketplace.

## Enveloppe JSON

```json
{
  "schema_version": 1,
  "source": "export",
  "authorized": true,
  "rights_reference": "REFERENCE-DU-CONTRAT-OU-AUTORISATION",
  "listings": [
    {
      "source_id": "identifiant-de-votre-export",
      "brand": "Renault",
      "model": "Clio",
      "generation": "V",
      "trim": "Evolution",
      "engine": "TCe 90",
      "year": 2022,
      "month": 4,
      "mileage_km": 51000,
      "price_eur": "11900,00",
      "fuel": "essence",
      "gearbox": "manuelle",
      "seller": "professionnel",
      "condition": "normal",
      "region": "Île-de-France",
      "city": "Créteil",
      "postal_code": "94000",
      "department": "94"
    }
  ]
}
```

Cette illustration de contrat est fictive et ne constitue pas une annonce réelle à importer en mode réel. Remplacer par vos données et leurs justificatifs. Ajouter les dates ISO avec fuseau pour pouvoir juger la fraîcheur : `published_at`, `observed_at`. L'observation manquante est horodatée à l'import, mais une publication inconnue reste inconnue et empêche de déclarer une opportunité récente.

## Champs et validation

| Champs | Convention |
|---|---|
| `source_id` | Requis, texte stable de la source, 120 caractères maximum |
| `brand`, `model`, `generation`, `trim`, `engine` | Textes distincts ; pas d'invention de moteur/génération à partir d'un titre ambigu |
| `price_eur`, `mileage_km`, `year`, `month` | Prix positif, deux décimales ; km entiers ; année ; mois 1–12, tous nullables |
| `fuel` | essence, diesel, electrique, hybride, hybride_rechargeable, gpl ; alias documentés par le parseur |
| `gearbox`, `seller`, `condition` | manuelle/automatique ; particulier/professionnel ; normal/endommage/pieces/inconnu |
| `power_kw`, `fiscal_hp`, `critair` | Unités séparées, entiers ; Crit'Air nullable et seulement fiable si fourni |
| `city`, `postal_code`, `department`, `region` | Métropole seulement ; département corse non inventé à partir de 20xxx |
| `latitude`, `longitude` | Paire de coordonnées fournie, bornée à un rectangle métropolitain ; aucune géolocalisation externe |
| `defects`, `maintenance`, `inspection`, `accident_claim`, `warranty` | Informations déclarées, pas des vérifications certifiées |
| `description` | Maximum 4 000 caractères ; expurgation élémentaire, à contrôler avant import |
| `url` | HTTPS, sans identifiants ni adresse locale/IP ; domaine cohérent pour les sources connues |
| `image_urls`, `images_authorized` | Liste de dix liens HTTPS au maximum avec droits explicites ; aucune image externe en démo |
| `financing_only` | Booléen strict ; des expressions de financement peuvent aussi créer un drapeau conservateur |

Champs inconnus refusés, notamment noms/contacts, VIN et immatriculations. Maximum 500 lignes et 1 Mio par lot, 2 000 annonces par base. Le JSON refuse les clés répétées et nombres non finis. Le CSV est UTF-8, séparateur `;`, en-tête avec les mêmes noms ; booléens `true`/`false`. Les imports acceptent `leboncoin`, `lacentrale`, `autoscout24`, `paruvendu` ou `export` en mode import, mais cela ne signifie pas que leurs APIs sont supportées.

## Rejets et provenance

Un schéma inconnu ou une ligne invalide rejette tout le lot avant écriture. Le statut de la source conserve dernière tentative, succès et nombre d'échecs, sans copier la totalité du fichier invalide. Chaque annonce conserve la référence de droits et les dates d'observation/ingestion. Le mode d'une base est immuable : utiliser une autre base pour changer entre synthétique et réel.
