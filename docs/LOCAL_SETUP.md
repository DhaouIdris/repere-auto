# Lancement local

## Sans installation de dépendances

Depuis le dossier décompressé, avec Python 3.12+ : `python -m repere demo`.

Le terminal affiche une URL localhost et un code d'accès temporaire. L'arrêt est Ctrl+C. La base démo est conservée sous `data/repere-demo.sqlite`. À chaque relance `demo`, les dates et prix de la fixture synthétique sont remis à jour. Pour conserver un historique d'essai non réinitialisé, employer `seed-demo` une seule fois puis `serve` avec des secrets stables.

## Serveur WSGI installé

```sh
python -m venv .venv
# Linux/macOS ; sur Windows : .venv\Scripts\activate
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m repere --db data/repere-demo.sqlite seed-demo
```

Le code applicatif n'a pas de dépendance externe ; Gunicorn est utilisé pour la vérification HTTP et l'exploitation sur Linux. Le serveur de développement Python reste disponible sur Windows.

Créer deux secrets distincts : exécuter deux fois `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Pour un serveur stable, définir `ACCESS_TOKEN`, `SESSION_SECRET`, `DATABASE_PATH`, `DATA_MODE`, `APP_ENV` et `APP_ORIGIN`. Les valeurs sont décrites dans `.env.example`. La commande Python ne lit pas `.env` automatiquement : utiliser les variables d'environnement de votre shell ; Docker Compose lit le fichier déclaré `env_file`.

Exemple Bash de développement (remplacer les secrets, ne pas utiliser les libellés comme secrets) :

```sh
export ACCESS_TOKEN='VOTRE_PREMIER_SECRET_ALEATOIRE_DE_32_CARACTERES_MINIMUM'
export SESSION_SECRET='VOTRE_SECOND_SECRET_ALEATOIRE_INDEPENDANT_DE_32_CARACTERES_MINIMUM'
export DATABASE_PATH='data/repere-demo.sqlite'
export DATA_MODE='demo'
export APP_ENV='development'
export APP_ORIGIN='http://127.0.0.1:8080'
python -m repere serve
```

En PowerShell, la syntaxe correspondante est `$env:ACCESS_TOKEN='…'`, et de même pour les autres variables.

## Imports

Une enveloppe JSON contient `schema_version: 1`, `source`, `authorized: true`, `rights_reference` et `listings`. Le prix source est `price_eur` ; le stockage utilise des centimes. Les données CSV utilisent `format: csv`, une chaîne `csv` UTF-8 avec séparateur `;`, et les mêmes métadonnées. Un champ vide reste absent. La validation est atomique : une ligne invalide rejette le lot complet.

Le formulaire web accepte l'un ou l'autre format et les fichiers de 1 Mio maximum, dans la limite de 500 annonces par lot. Une base démo accepte uniquement la source `demo`. Pour les données réelles autorisées, créer une base `--mode import`, puis configurer le serveur sur cette même base avec `DATA_MODE=import`. Les exemples livrés sont fictifs et ne doivent pas être étiquetés comme des annonces réelles.

## Tests

```sh
python -m unittest discover -v
node --check static/app.js
python scripts/http_smoke.py
npm ci --ignore-scripts
npm test
python -m pip install -r requirements-dev.txt
pip-audit --strict --require-hashes -r requirements.lock
npm audit --audit-level=high
```

Le test navigateur utilise Playwright et le binaire Chromium de test sous Linux x64. Il nécessite les bibliothèques système du navigateur. La variable `PYTHON` permet de choisir le Python où Gunicorn est installé ; `CHROMIUM_EXECUTABLE` permet d'utiliser un binaire Chromium déjà installé, sans téléchargement automatique. Aucun test n'envoie de notification externe ni de requête à une marketplace.
