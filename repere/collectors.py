"""Read completed scraper tasks through Apify's documented, read-only API.

No actor is started here. Scraping permissions, search filters, scheduling and
cost limits belong to the configured task. Only vehicle fields enter SQLite.
"""
from dataclasses import dataclass, field
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import db as storage
from .adapters import JsonAdapter, prepare
from .alerts import queue
from .model import date, iso, norm, utcnow
from .valuation import Rules


SOURCES = ('leboncoin', 'lacentrale', 'autoscout24', 'paruvendu')
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,80}(?:~[A-Za-z0-9_-]{1,80})?\Z')
MAX_RESPONSE = 2_097_152
PAGE_SIZE = 100

# Structured fields only. In particular, a title is not parsed into an engine,
# generation or trim. Seller contacts, free text and photos are not imported.
ALIASES = {
    'source_id': ('source_id', 'list_id', 'id', 'listingId', 'adId'),
    'url': ('url', 'listingUrl', 'adUrl'),
    'brand': ('brand', 'make', 'marque', 'vehicle.make', 'attributes.brand'),
    'model': ('model', 'modele', 'vehicle.model', 'attributes.model'),
    'generation': ('generation', 'vehicle.generation'),
    'trim': ('trim', 'finition', 'vehicle.trim'),
    'engine': ('engine', 'motorisation', 'vehicle.engine'),
    'year': ('year', 'annee', 'regdate', 'attributes.regdate'),
    'month': ('month',),
    'price_eur': ('price_eur', 'prix', 'price.amount', 'price.value', 'price'),
    'mileage_km': ('mileage_km', 'mileageKm', 'kilometrage', 'mileage', 'attributes.mileage'),
    'fuel': ('fuel', 'fuelType', 'energie', 'attributes.fuel'),
    'gearbox': ('gearbox', 'transmission', 'boite', 'attributes.gearbox'),
    'seller': ('seller.type', 'sellerType', 'type_vendeur', 'owner.type', 'seller'),
    'condition': ('condition', 'vehicle.condition'),
    'city': ('city', 'ville', 'location.city'),
    'postal_code': ('postal_code', 'code_postal', 'zipcode', 'zipCode', 'location.zipcode', 'location.postalCode'),
    'department': ('department', 'departement', 'location.department_id'),
    'region': ('region', 'location.region_name', 'location.region'),
    'power_kw': ('power_kw', 'powerKw'),
    'fiscal_hp': ('fiscal_hp', 'puissance_fiscale', 'attributes.fiscal_power'),
    'critair': ('critair',),
    'published_at': ('published_at', 'first_publication_date', 'publishedAt', 'datePublished', 'date_publication'),
    'observed_at': ('observed_at', 'scrapedAt', 'scraped_at', 'crawledAt'),
    'financing_only': ('financing_only', 'financingOnly'),
}


class CollectionError(ValueError):
    """Safe to display; never includes an upstream body, URL or credential."""


@dataclass(frozen=True)
class SourceConfig:
    source: str
    task_id: str
    rights_reference: str
    max_items: int = 500
    field_map: dict = field(default_factory=dict)


def load_config(path):
    path = Path(path)
    if path.stat().st_size > 65_536:
        raise ValueError('Configuration limitée à 64 Kio')
    data = JsonAdapter().read(path.read_bytes())
    if not isinstance(data, dict) or set(data) != {'schema_version', 'sources'} or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('Configuration collecteurs : schema_version 1 et sources requis')
    if not isinstance(data['sources'], list) or len(data['sources']) > len(SOURCES):
        raise ValueError('Une configuration par source, quatre sources maximum')
    result, seen = [], set()
    for entry in data['sources']:
        if not isinstance(entry, dict) or set(entry) - {'source', 'enabled', 'task_id', 'authorized', 'rights_reference', 'max_items', 'field_map'}:
            raise ValueError('Configuration de source invalide ; aucun secret dans ce fichier')
        source = entry.get('source')
        if source not in SOURCES or source in seen:
            raise ValueError('Source inconnue ou répétée')
        seen.add(source)
        if type(entry.get('enabled', False)) is not bool:
            raise ValueError('enabled doit être booléen')
        if not entry.get('enabled', False):
            continue
        task, rights = entry.get('task_id'), entry.get('rights_reference')
        if not isinstance(task, str) or not IDENTIFIER.fullmatch(task):
            raise ValueError('task_id Apify invalide')
        if entry.get('authorized') is not True or not isinstance(rights, str) or not 8 <= len(rights.strip()) <= 300:
            raise ValueError('Autorisation et référence des droits requises pour chaque source activée')
        maximum = entry.get('max_items', 500)
        if type(maximum) is not int or not 1 <= maximum <= 500:
            raise ValueError('max_items : entier de 1 à 500')
        mapping = entry.get('field_map', {})
        if not isinstance(mapping, dict) or set(mapping) - set(ALIASES):
            raise ValueError('field_map : champ véhicule inconnu ou interdit')
        for paths in mapping.values():
            paths = [paths] if isinstance(paths, str) else paths
            if not isinstance(paths, list) or not 1 <= len(paths) <= 8 or any(not isinstance(p, str) or len(p) > 150 or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', p) for p in paths):
                raise ValueError('field_map : chemins JSON pointés requis')
        result.append(SourceConfig(source, task, rights.strip(), maximum, mapping))
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ApifyClient:
    def __init__(self, token=None):
        self.token = token if token is not None else os.environ.get('APIFY_TOKEN', '')
        if not self.token or len(self.token) > 1024 or any(ord(c) < 33 or ord(c) > 126 for c in self.token):
            raise CollectionError('Définir APIFY_TOKEN dans le terminal ; ne pas le mettre dans GitHub')
        self.opener = build_opener(NoRedirect())

    def get(self, path, **params):
        # No configurable host, redirect or token in the query string.
        url = 'https://api.apify.com/v2/' + path + ('?' + urlencode(params) if params else '')
        request = Request(url, headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json', 'User-Agent': 'RepereAuto/1.0'})
        try:
            with self.opener.open(request, timeout=20) as response:
                if response.headers.get_content_type() != 'application/json':
                    raise CollectionError('Apify : réponse JSON attendue')
                body = response.read(MAX_RESPONSE + 1)
                if len(body) > MAX_RESPONSE:
                    raise CollectionError('Apify : réponse trop volumineuse')
                return JsonAdapter().read(body), response.headers
        except HTTPError as exc:
            messages = {401: 'jeton refusé', 403: 'accès refusé', 404: 'tâche ou résultat introuvable', 429: 'quota atteint ; réessayer plus tard'}
            raise CollectionError('Apify : ' + messages.get(exc.code, f'erreur HTTP {exc.code}')) from None
        except (URLError, OSError, TimeoutError):
            raise CollectionError('Apify : connexion indisponible ou délai dépassé') from None
        except (ValueError, RecursionError) as exc:
            if isinstance(exc, CollectionError):
                raise
            raise CollectionError('Apify : JSON invalide') from None

    def latest(self, task_id, now):
        if not IDENTIFIER.fullmatch(task_id):
            raise CollectionError('task_id Apify invalide')
        payload, _ = self.get(f'actor-tasks/{task_id}/runs/last', status='SUCCEEDED')
        run = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(run, dict) or run.get('status') != 'SUCCEEDED':
            raise CollectionError('Apify : aucun résultat terminé avec succès')
        for key in ('id', 'defaultDatasetId'):
            if not isinstance(run.get(key), str) or not IDENTIFIER.fullmatch(run[key]) or '~' in run[key]:
                raise CollectionError('Apify : identifiant de résultat invalide')
        try:
            finished, started = date(run.get('finishedAt')), date(run.get('startedAt'))
        except ValueError:
            raise CollectionError('Apify : dates du résultat absentes ou invalides') from None
        if not started <= finished <= now + timedelta(minutes=5):
            raise CollectionError('Apify : dates du résultat incohérentes')
        return run

    def items(self, dataset_id, maximum):
        if not IDENTIFIER.fullmatch(dataset_id) or '~' in dataset_id:
            raise CollectionError('Apify : identifiant de dataset invalide')
        result, total = [], None
        while total is None or len(result) < total:
            page, headers = self.get(f'datasets/{dataset_id}/items', format='json', offset=len(result), limit=min(PAGE_SIZE, maximum), skipHidden='true')
            try:
                count = int(headers['X-Apify-Pagination-Total'])
                offset = int(headers['X-Apify-Pagination-Offset'])
            except (KeyError, ValueError, TypeError):
                raise CollectionError('Apify : pagination absente ou invalide') from None
            if count < 0 or count > maximum:
                raise CollectionError(f'Apify : limiter le scraper à {maximum} annonces par tâche')
            if total is not None and count != total:
                raise CollectionError('Apify : dataset modifié pendant la lecture ; aucun import')
            total = count
            if not isinstance(page, list) or offset != len(result) or len(page) > min(PAGE_SIZE, maximum) or len(result) + len(page) > total or (not page and len(result) < total):
                raise CollectionError('Apify : pagination incohérente ; aucun import')
            result.extend(page)
        return result


def _path(row, path):
    value = row
    for part in path.split('.'):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _pick(row, paths):
    for path in ([paths] if isinstance(paths, str) else paths):
        value = _path(row, path)
        if value is not None and value != '':
            return value
    return None


def _number(value, unit=None):
    if value is None:
        return None
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, str):
        value = value.replace('\u202f', '').replace('\xa0', '').replace(' ', '').strip()
        if unit:
            value = re.sub(r'(?:' + unit + r')$', '', value, flags=re.I)
    return value


def normalize(row, config, observed_at):
    if not isinstance(row, dict):
        raise CollectionError('Annonce : objet JSON attendu')
    # Convert LBC's structured attribute array into a lookup, without copying it
    # into storage. Ambiguous duplicate attributes are rejected.
    data = dict(row)
    if isinstance(data.get('attributes'), list):
        attributes = {}
        for attr in data['attributes']:
            if not isinstance(attr, dict) or not isinstance(attr.get('key'), str):
                continue
            value = attr.get('value')
            if value is None and isinstance(attr.get('values'), list) and len(attr['values']) == 1:
                value = attr['values'][0]
            if attr['key'] in attributes and attributes[attr['key']] != value:
                raise CollectionError('Annonce : attributs contradictoires')
            attributes[attr['key']] = value
        data['attributes'] = attributes
    raw = {key: _pick(data, config.field_map.get(key, paths)) for key, paths in ALIASES.items()}
    identifier = raw['source_id']
    if isinstance(identifier, int) and not isinstance(identifier, bool):
        identifier = str(identifier)
    if not isinstance(identifier, str) or not identifier.strip():
        raise CollectionError('Annonce : identifiant source stable requis')
    raw['source_id'] = identifier
    if not raw['url']:
        raise CollectionError('Annonce : lien vers la source requis')
    # A foreign listing must not enter the France-only baseline.
    country = _pick(data, ('countryCode', 'country', 'location.country', 'seller.country'))
    if country is not None and norm(country) not in ('fr', 'france', 'fra'):
        raise CollectionError('Annonce hors France ; configurer la recherche du scraper sur la France')
    if config.source == 'autoscout24' and urlsplit(raw['url']).hostname in ('www.autoscout24.com', 'autoscout24.com') and country is None:
        raise CollectionError('AutoScout24 .com : pays France explicite requis')
    currency = _pick(data, ('currency', 'price.currency', 'priceCurrency'))
    if currency is not None and currency != 'EUR':
        raise CollectionError('Annonce : seul le prix comptant en EUR est accepté')
    raw['price_eur'] = _number(raw['price_eur'], r'€|EUR')
    for key in ('mileage_km', 'year', 'month', 'power_kw', 'fiscal_hp', 'critair'):
        value = _number(raw[key], r'km' if key == 'mileage_km' else None)
        raw[key] = int(value) if isinstance(value, float) and value.is_integer() else value
    registration = _pick(data, ('firstRegistration', 'first_registration'))
    if not raw['year'] and isinstance(registration, str) and re.fullmatch(r'\d{4}-\d{2}', registration):
        raw['year'], raw['month'] = registration.split('-')
    # Display strings such as "Publiée aujourd'hui" cannot establish a reliable
    # publication timestamp. Missing publication never becomes "now".
    if raw['published_at']:
        try:
            raw['published_at'] = iso(date(raw['published_at']))
        except ValueError:
            raw['published_at'] = None
    raw['observed_at'] = raw['observed_at'] or observed_at
    if isinstance(raw['postal_code'], int) and not isinstance(raw['postal_code'], bool):
        raw['postal_code'] = str(raw['postal_code']).zfill(5)
    if raw['department'] is not None:
        raw['department'] = str(raw['department']).upper().zfill(2)
    gears = {'mecanique': 'manuelle', 'mechanical': 'manuelle', 'auto': 'automatique'}
    raw['gearbox'] = gears.get(norm(raw['gearbox']) if isinstance(raw['gearbox'], str) else '', raw['gearbox'])
    seller = raw['seller']
    raw['seller'] = {'private': 'particulier', 'part': 'particulier', 'pro': 'professionnel', 'dealer': 'professionnel'}.get(norm(seller) if isinstance(seller, str) else '', seller)
    # No description, contact, VIN, plate, photograph or inferred good condition.
    return raw


def _state(db, source, value):
    db.execute('INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               ('collector:' + source, json.dumps(value, ensure_ascii=False)))


def collect(path, configs, client, *, now=None, rules=None, force=False):
    """Each source validates completely before its single ingestion transaction.

    Failures are isolated by source. Re-reading one run never changes its data's
    observation date. This function only queues alerts; it never sends messages.
    """
    now, rules = now or utcnow(), rules or Rules()
    storage.initialize(path, 'import')
    reports = []
    for config in configs:
        report = {'source': config.source, 'provider': 'apify', 'last_attempt': iso(now)}
        with storage.connect(path) as db:
            old = db.execute('SELECT value FROM metadata WHERE key=?', ('collector:' + config.source,)).fetchone()
            previous = json.loads(old[0]) if old else {}
        try:
            run = client.latest(config.task_id, now)
            report.update(run_id=run['id'], observed_at=run['finishedAt'])
            if not force and previous.get('task_id') == config.task_id and previous.get('run_id') == run['id'] and previous.get('status') in ('synced', 'unchanged'):
                report.update(status='unchanged', rows=previous.get('rows', 0), last_success=previous.get('last_success'), task_id=config.task_id)
                with storage.connect(path) as db:
                    _state(db, config.source, report)
                    db.execute('UPDATE source_status SET last_error=NULL WHERE source=?', (config.source,))
            else:
                rows = client.items(run['defaultDatasetId'], config.max_items)
                items = []
                if rows:
                    raw = []
                    for index, row in enumerate(rows, 1):
                        try:
                            raw.append(normalize(row, config, run['finishedAt']))
                        except (ValueError, TypeError, AttributeError):
                            raise CollectionError(f'Ligne {index} : format incompatible ; vérifier field_map et les filtres du scraper') from None
                    items, _ = prepare({'schema_version': 1, 'source': config.source, 'authorized': True,
                                             'rights_reference': config.rights_reference, 'listings': raw}, 'import', now)
                with storage.connect(path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    try:
                        counts = storage.ingest(db, items, config.rights_reference, now)
                        queued = queue(db, storage.records(db), rules, now)
                        report.update(status='synced', rows=len(items), counts=counts, alerts_queued=queued, last_success=iso(now), task_id=config.task_id)
                        _state(db, config.source, report)
                        db.execute('UPDATE source_status SET last_error=NULL WHERE source=?', (config.source,))
                        db.execute('COMMIT')
                    except Exception:
                        db.execute('ROLLBACK')
                        raise
        except (ValueError, sqlite3.Error) as exc:
            # Upstream transport failures are already sanitized. Never print raw
            # provider exceptions, dataset records or task inputs.
            message = str(exc) if isinstance(exc, ValueError) else 'Échec SQLite ; import non confirmé'
            report = {'source': config.source, 'provider': 'apify', 'status': 'error', 'last_attempt': iso(now),
                      'last_success': previous.get('last_success'), 'observed_at': previous.get('observed_at'), 'error': message[:300]}
            with storage.connect(path) as db:
                storage.failure(db, config.source, report['error'], now)
                _state(db, config.source, report)
        reports.append({key: value for key, value in report.items() if key != 'task_id'})
    return reports
