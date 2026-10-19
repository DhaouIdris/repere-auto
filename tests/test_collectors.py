"""Synthetic provider responses only; no marketplace, paid task or live token."""
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.message import Message
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from repere import db
from repere.__main__ import main
from repere.adapters import prepare, source_registry
from repere.collectors import ApifyClient, CollectionError, SourceConfig, collect, load_config, normalize
from repere.model import iso


NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


def config(source='leboncoin'):
    return SourceConfig(source, 'testuser~cars', 'AUTORISATION-TEST-FICTIVE')


def listing(source='leboncoin', **changes):
    host = {'leboncoin': 'www.leboncoin.fr', 'lacentrale': 'www.lacentrale.fr', 'autoscout24': 'www.autoscout24.fr', 'paruvendu': 'www.paruvendu.fr'}[source]
    return {'id': 'synthetic-unit-1', 'url': 'https://' + host + '/annonce-fictive-test',
            'brand': 'Renault', 'model': 'Clio', 'price': 12345, 'mileageKm': 45000,
            'year': 2021, 'fuel': 'essence', 'gearbox': 'manuelle', 'sellerType': 'Dealer',
            'countryCode': 'FR', 'postal_code': '75013', 'city': 'Paris', **changes}


def run(identifier='runSynthetic1', at=NOW):
    return {'id': identifier, 'status': 'SUCCEEDED', 'defaultDatasetId': 'datasetSynthetic1',
            'startedAt': iso(at - timedelta(minutes=2)), 'finishedAt': iso(at)}


class StubClient:
    def __init__(self, rows=None, result=None):
        self.rows = rows if rows is not None else [listing()]
        self.result = result or run()
        self.item_calls = 0

    def latest(self, task_id, now):
        return self.result

    def items(self, dataset_id, maximum):
        self.item_calls += 1
        return self.rows


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'real.sqlite')

    def rows(self):
        with db.connect(self.path) as conn:
            return db.records(conn)

    def test_three_source_formats_and_private_fields_excluded(self):
        cases = [
            ('leboncoin', listing(price=[12345], attributes=[{'key': 'fiscal_power', 'value': '5'}], telephone='NE-PAS-STOCKER', vin='NE-PAS-STOCKER', description='NE-PAS-STOCKER')),
            ('lacentrale', {'id': 'fictive-lc', 'url': 'https://www.lacentrale.fr/annonce-fictive-test', 'marque': 'Renault', 'modele': 'Clio', 'prix': '12 345 €', 'kilometrage': '45 000 km', 'annee': 2021, 'energie': 'ESSENCE', 'boite': 'MECANIQUE', 'type_vendeur': 'particulier', 'code_postal': 75013, 'nom_vendeur': 'NE-PAS-STOCKER'}),
            ('autoscout24', {'id': 'fictive-as', 'url': 'https://www.autoscout24.fr/offres/annonce-fictive-test', 'make': 'Renault', 'model': 'Clio', 'price': 12345, 'mileageKm': 45000, 'firstRegistration': '2021-04', 'transmission': 'Manual', 'fuelType': 'Gasoline', 'sellerType': 'Dealer', 'powerHp': 90}),
        ]
        for source, row in cases:
            with self.subTest(source=source):
                report = collect(self.path, [config(source)], StubClient([row]), now=NOW)[0]
                self.assertEqual(report['status'], 'synced', report)
        rows = self.rows()
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row['price_cents'], 1234500)
            self.assertEqual(row['mileage_km'], 45000)
            self.assertEqual(row['year'], 2021)
            self.assertIsNone(row['condition'])
            self.assertIsNone(row['engine'])
            self.assertNotIn('NE-PAS-STOCKER', json.dumps(row))
        autoscout = next(r for r in rows if r['source'] == 'autoscout24')
        self.assertIsNone(autoscout['fiscal_hp'])  # DIN horsepower is not fiscal HP.

    def test_attribute_array_maps_lbc_structured_vehicle(self):
        raw = {'list_id': 123456789, 'url': 'https://www.leboncoin.fr/ad/voitures/123456789', 'price': [9000],
               'attributes': [{'key': 'brand', 'value': 'Renault'}, {'key': 'model', 'values': ['Clio']},
                              {'key': 'regdate', 'value': '2020'}, {'key': 'mileage', 'value': '82000'}]}
        rows, _ = prepare({'schema_version': 1, 'source': 'leboncoin', 'authorized': True, 'rights_reference': 'TEST-AUTORISE',
                           'listings': [normalize(raw, config(), iso(NOW))]}, 'import', NOW)
        self.assertEqual((rows[0].source_id, rows[0].brand, rows[0].year, rows[0].mileage_km), ('123456789', 'Renault', 2020, 82000))

    def test_same_run_is_not_downloaded_or_rejuvenated(self):
        client = StubClient()
        collect(self.path, [config()], client, now=NOW)
        before = self.rows()[0]
        result = collect(self.path, [config()], client, now=NOW + timedelta(days=15))[0]
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(client.item_calls, 1)
        after = self.rows()[0]
        self.assertEqual((before['observed_at'], before['last_seen']), (after['observed_at'], after['last_seen']))
        with db.connect(self.path) as conn, patch('repere.adapters.utcnow', return_value=NOW + timedelta(days=15)):
            source = source_registry('import', conn)[0]
        self.assertEqual(source['collector']['freshness'], 'perime')
        self.assertNotIn('task_id', source['collector'])

    def test_force_replay_still_preserves_observation_and_history(self):
        client = StubClient()
        collect(self.path, [config()], client, now=NOW)
        result = collect(self.path, [config()], client, now=NOW + timedelta(hours=1), force=True)[0]
        self.assertEqual(result['counts']['ignored_identical'], 1)
        self.assertEqual(client.item_calls, 2)
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM price_history').fetchone()[0], 1)
        self.assertEqual(self.rows()[0]['observed_at'], iso(NOW))

    def test_new_run_tracks_real_price_change(self):
        collect(self.path, [config()], StubClient(), now=NOW)
        later = NOW + timedelta(hours=1)
        result = collect(self.path, [config()], StubClient([listing(price=11000)], run('runSynthetic2', later)), now=later)[0]
        self.assertEqual(result['counts']['price_changes'], 1)
        with db.connect(self.path) as conn:
            self.assertEqual([r[0] for r in conn.execute('SELECT price_cents FROM price_history ORDER BY event_id')], [1234500, 1100000])

    def test_one_invalid_row_rejects_entire_source(self):
        report = collect(self.path, [config()], StubClient([listing(), listing(id='bad', price=-10)]), now=NOW)[0]
        self.assertEqual(report['status'], 'error')
        self.assertEqual(self.rows(), [])

    def test_foreign_country_and_foreign_currency_are_rejected(self):
        for changes in ({'countryCode': 'DE'}, {'currency': 'USD'}):
            with self.subTest(changes=changes):
                result = collect(self.path, [config()], StubClient([listing(**changes)]), now=NOW)[0]
                self.assertEqual(result['status'], 'error')
        self.assertEqual(self.rows(), [])

    def test_autoscout_com_requires_explicit_france(self):
        raw = listing('autoscout24', url='https://www.autoscout24.com/offers/synthetic')
        collect(self.path, [config('autoscout24')], StubClient([raw]), now=NOW)
        self.assertEqual(len(self.rows()), 1)
        raw.pop('countryCode')
        self.assertEqual(collect(self.path, [config('autoscout24')], StubClient([raw], run('runSynthetic2')), now=NOW)[0]['status'], 'error')

    def test_publication_display_text_is_not_today(self):
        collect(self.path, [config()], StubClient([listing(date_publication="Publiée aujourd'hui")]), now=NOW)
        self.assertIsNone(self.rows()[0]['published_at'])
        self.assertEqual(self.rows()[0]['observed_at'], iso(NOW))

    def test_duplicate_ids_reject_entire_source(self):
        self.assertEqual(collect(self.path, [config()], StubClient([listing(), listing()]), now=NOW)[0]['status'], 'error')
        self.assertEqual(self.rows(), [])

    def test_source_failures_are_isolated(self):
        class Client(StubClient):
            def __init__(self):
                self.index = 0
            def latest(self, task_id, now):
                self.index += 1
                if self.index == 1:
                    raise CollectionError('Apify : quota atteint')
                return run()
            def items(self, dataset_id, maximum):
                return [listing('lacentrale')]
        reports = collect(self.path, [config(), config('lacentrale')], Client(), now=NOW)
        self.assertEqual([r['status'] for r in reports], ['error', 'synced'])
        self.assertEqual([r['source'] for r in self.rows()], ['lacentrale'])

    def test_alert_failure_rolls_back_listings_history_and_checkpoint(self):
        with patch('repere.collectors.queue', side_effect=sqlite3.OperationalError('synthetic failure')):
            result = collect(self.path, [config()], StubClient(), now=NOW)[0]
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self.rows(), [])
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM price_history').fetchone()[0], 0)
            stored = json.loads(conn.execute("SELECT value FROM metadata WHERE key='collector:leboncoin'").fetchone()[0])
        self.assertEqual(stored['status'], 'error')
        self.assertNotIn('run_id', stored)

    def test_empty_dataset_is_a_success_without_erasing_existing_listings(self):
        collect(self.path, [config()], StubClient(), now=NOW)
        result = collect(self.path, [config()], StubClient([], run('runSynthetic2')), now=NOW)[0]
        self.assertEqual((result['status'], result['rows']), ('synced', 0))
        self.assertEqual(len(self.rows()), 1)

    def test_demo_database_is_never_used_for_real_data(self):
        db.initialize(self.path, 'demo')
        with self.assertRaisesRegex(ValueError, 'autre mode'):
            collect(self.path, [config()], StubClient(), now=NOW)

    def test_config_and_check_require_rights_but_not_network_or_token(self):
        path = Path(self.temp.name) / 'collectors.json'
        entry = {'source': 'leboncoin', 'enabled': True, 'task_id': 'testuser~cars', 'authorized': True, 'rights_reference': 'TEST-AUTORISE',
                 'field_map': {'price_eur': 'vehicle.cashPrice'}}
        path.write_text(json.dumps({'schema_version': 1, 'sources': [entry]}))
        self.assertEqual(load_config(path)[0].field_map['price_eur'], 'vehicle.cashPrice')
        with patch.dict(os.environ, {'APIFY_TOKEN': ''}), patch.object(sys, 'argv', ['repere', '--db', self.path, 'collect', '--config', str(path), '--check']), redirect_stdout(io.StringIO()):
            main()
        self.assertFalse(Path(self.path).exists())
        for change in ({'authorized': False}, {'token': 'NEVER-IN-CONFIG'}, {'task_id': '../../secret'}, {'field_map': {'telephone': 'phone'}}):
            path.write_text(json.dumps({'schema_version': 1, 'sources': [entry | change]}))
            with self.subTest(change=change), self.assertRaises(ValueError):
                load_config(path)

    def test_custom_paths_and_price_amounts(self):
        cfg = SourceConfig('leboncoin', 'test', 'TEST-AUTORISE', field_map={'price_eur': 'vehicle.cash.0'})
        raw = normalize(listing(vehicle={'cash': [8200]}), cfg, iso(NOW))
        self.assertEqual(raw['price_eur'], 8200)

    def test_live_cli_collects_in_background_and_keeps_demo_separate(self):
        path = Path(self.temp.name) / 'collectors.json'
        path.write_text(json.dumps({'schema_version': 1, 'sources': [{'source': 'leboncoin', 'enabled': True, 'task_id': 'test', 'authorized': True, 'rights_reference': 'TEST-AUTORISE'}]}))
        completed = threading.Event()
        real_collect = collect
        def wrapped(*args, **kwargs):
            result = real_collect(*args, **kwargs)
            completed.set()
            return result
        class Server:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def serve_forever(self):
                if not completed.wait(3): raise AssertionError('Background collection did not complete')
                raise KeyboardInterrupt()
        with patch('repere.collectors.ApifyClient', return_value=StubClient()), patch('repere.collectors.collect', side_effect=wrapped), patch('repere.__main__.make_server', return_value=Server()), patch.object(sys, 'argv', ['repere', '--db', self.path, 'live', '--config', str(path)]), redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(len(self.rows()), 1)
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT value FROM metadata WHERE key='mode'").fetchone()[0], 'import')


class TransportTests(unittest.TestCase):
    def response(self, content, **headers):
        body = json.dumps(content).encode() if not isinstance(content, bytes) else content
        response = io.BytesIO(body)
        response.headers = Message()
        response.headers['Content-Type'] = 'application/json'
        for key, value in headers.items(): response.headers[key.replace('_', '-')] = str(value)
        return response

    def test_client_uses_get_bearer_and_fixed_api_host(self):
        client = ApifyClient('synthetic-token')
        with patch.object(client.opener, 'open', return_value=self.response({'data': run()})) as request:
            self.assertEqual(client.latest('testuser~cars', NOW)['id'], 'runSynthetic1')
        req = request.call_args.args[0]
        self.assertEqual(req.get_method(), 'GET')
        self.assertTrue(req.full_url.startswith('https://api.apify.com/v2/actor-tasks/'))
        self.assertNotIn('synthetic-token', req.full_url)
        self.assertEqual(req.headers['Authorization'], 'Bearer synthetic-token')

    def test_auth_quota_and_network_failures_never_leak_upstream_messages(self):
        client = ApifyClient('synthetic-token')
        for failure in [HTTPError('https://api.apify.com/?token=synthetic-token', status, 'synthetic-token', {}, None) for status in (301, 401, 403, 404, 429, 500)] + [URLError('synthetic-token')]:
            with self.subTest(failure=type(failure).__name__), patch.object(client.opener, 'open', side_effect=failure):
                with self.assertRaises(CollectionError) as caught: client.get('actor-tasks/test/runs/last')
                self.assertNotIn('synthetic-token', str(caught.exception))

    def test_redirect_handler_does_not_forward_credentials(self):
        from repere.collectors import NoRedirect
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.org'))

    def test_future_or_unsuccessful_run_is_rejected(self):
        client = ApifyClient('synthetic-token')
        for value in (run(at=NOW + timedelta(days=1)), run() | {'status': 'RUNNING'}, run() | {'defaultDatasetId': '../../other'}):
            with patch.object(client, 'get', return_value=({'data': value}, {})), self.assertRaises(CollectionError):
                client.latest('test', NOW)

    def test_pagination_is_complete_and_consistent(self):
        client = ApifyClient('synthetic-token')
        pages = [([{'id': 1}, {'id': 2}], {'X-Apify-Pagination-Total': '3', 'X-Apify-Pagination-Offset': '0'}),
                 ([{'id': 3}], {'X-Apify-Pagination-Total': '3', 'X-Apify-Pagination-Offset': '2'})]
        with patch('repere.collectors.PAGE_SIZE', 2), patch.object(client, 'get', side_effect=pages):
            self.assertEqual([r['id'] for r in client.items('datasetTest', 5)], [1, 2, 3])

    def test_oversized_incomplete_or_changing_dataset_is_rejected(self):
        client = ApifyClient('synthetic-token')
        for pages in [
            [([], {'X-Apify-Pagination-Total': '6', 'X-Apify-Pagination-Offset': '0'})],
            [([], {'X-Apify-Pagination-Total': '1', 'X-Apify-Pagination-Offset': '0'})],
            [([{}], {'X-Apify-Pagination-Total': '2', 'X-Apify-Pagination-Offset': '0'}), ([{}], {'X-Apify-Pagination-Total': '3', 'X-Apify-Pagination-Offset': '1'})],
            [([], {})],
        ]:
            with patch.object(client, 'get', side_effect=pages), self.assertRaises(CollectionError):
                client.items('datasetTest', 5)

    def test_invalid_json_and_oversized_body_are_rejected(self):
        client = ApifyClient('synthetic-token')
        for body in (b'{', b'{"x":1,"x":2}', b'{"x":NaN}', b'x' * 2_097_153):
            with patch.object(client.opener, 'open', return_value=self.response(body)), self.assertRaises(CollectionError):
                client.get('datasets/test/items')


if __name__ == '__main__':
    unittest.main()
