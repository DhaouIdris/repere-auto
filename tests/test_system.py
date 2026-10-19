import copy
from datetime import datetime,timezone,timedelta
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from repere import db
from repere.adapters import prepare,JsonAdapter
from repere.alerts import queue,drain,DeliveryError
from repere.config import Config
from repere.demo import payload
from repere.model import parse_listing,cents,norm,iso,fingerprint
from repere.valuation import estimate,rank,Rules,validate_filters
from repere.web import Application

NOW=datetime(2026,10,19,12,tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        clock=patch('repere.web.utcnow',return_value=NOW)
        clock.start();self.addCleanup(clock.stop)
        self.tmp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.tmp.name)/'test.sqlite')
        db.initialize(self.path,'demo')
        self.payload=payload(NOW)
        self.items,self.rights=prepare(self.payload,'demo',NOW)

    def tearDown(self): self.tmp.cleanup()

    def seed(self):
        with db.connect(self.path) as conn: return db.ingest(conn,self.items,self.rights,NOW)

    def rows(self):
        with db.connect(self.path) as conn:return db.records(conn)

    def request(self,method,path,body=None,cookie=None,csrf=None,bearer=True,origin=None):
        if not hasattr(self,'app'): self.app=Application(Config(self.path,access_token='T'*40,session_secret='S'*40))
        data=json.dumps(body).encode() if body is not None else b''
        route,_,query=path.partition('?')
        e={'REQUEST_METHOD':method,'PATH_INFO':route,'QUERY_STRING':query,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(data)),
           'wsgi.input':io.BytesIO(data),'REMOTE_ADDR':'127.0.0.1'}
        if bearer:e['HTTP_AUTHORIZATION']='Bearer '+'T'*40
        if cookie:e['HTTP_COOKIE']=cookie
        if csrf:e['HTTP_X_CSRF_TOKEN']=csrf
        if origin:e['HTTP_ORIGIN']=origin
        response={}
        def start(status,headers): response.update(status=int(status[:3]),headers=dict(headers))
        raw=b''.join(self.app(e,start))
        response['body']=json.loads(raw) if response['headers']['Content-Type'].startswith('application/json') else raw
        return response


class ModelTests(Base):
    def test_french_money(self):
        self.assertEqual(cents('9\u202f200,50 €'),920050)
        self.assertEqual(norm('ÉLECTRIQUE'),'electrique')

    def test_invalid_prices(self):
        for value in ['NaN','Infinity',True,-1,'12.345','9.200,00']:
            with self.subTest(value=value), self.assertRaises(ValueError): cents(value)

    def test_aliases_and_no_invented_critair(self):
        r=self.payload['listings'][0]|{'fuel':'petrol','gearbox':'BVM6','brand':'renault'}
        x=parse_listing(r,'demo','demo',NOW)
        self.assertEqual((x.brand,x.fuel,x.gearbox),('Renault','essence','manuelle'))
        self.assertIsNone(x.critair)

    def test_missing_values_preserved(self):
        r=self.payload['listings'][0]|{'price_eur':None,'engine':None}
        x=parse_listing(r,'demo','demo',NOW)
        self.assertIsNone(x.price_cents);self.assertIsNone(x.engine)

    def test_invalid_postal_codes(self):
        for value in ['7501','97100','00000','99999']:
            with self.subTest(value=value),self.assertRaises(ValueError):parse_listing(self.payload['listings'][0]|{'postal_code':value},'demo','demo',NOW)

    def test_personal_identifiers_forbidden(self):
        with self.assertRaises(ValueError):parse_listing(self.payload['listings'][0]|{'vin':'ABCDE'},'demo','demo',NOW)

    def test_personal_text_redacted(self):
        r=self.payload['listings'][0]|{'description':'Appelez le 06 12 34 56 78 ou abc@example.fr plaque AB-123-CD'}
        x=parse_listing(r,'demo','demo',NOW)
        self.assertNotIn('06 12',x.description);self.assertNotIn('@',x.description);self.assertNotIn('AB-123-CD',x.description)

    def test_future_and_naive_dates_refused(self):
        for value in ['2026-10-19T12:00:00','2099-01-01T00:00:00Z']:
            with self.assertRaises(ValueError):parse_listing(self.payload['listings'][0]|{'observed_at':value},'demo','demo',NOW)

    def test_unsafe_urls_refused(self):
        for url in ['javascript:alert(1)','http://example.fr','https://user:pass@example.fr','https://example.fr:90']:
            with self.assertRaises(ValueError):parse_listing(self.payload['listings'][0]|{'url':url},'export','import',NOW)

    def test_json_duplicate_keys_and_constants(self):
        for content in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{']:
            with self.assertRaises(ValueError):JsonAdapter().read(content)

    def test_unknown_schema(self):
        with self.assertRaisesRegex(ValueError,'schéma'):prepare(self.payload|{'schema_version':2},'demo',NOW)

    def test_import_requires_rights(self):
        with self.assertRaises(ValueError):prepare(self.payload|{'authorized':False},'demo',NOW)

    def test_demo_import_separation(self):
        with self.assertRaises(ValueError):prepare(self.payload,'import',NOW)
        with self.assertRaises(ValueError):db.initialize(self.path,'import')

    def test_csv_parser(self):
        p={'schema_version':1,'source':'export','authorized':True,'rights_reference':'CONTRAT-EXEMPLE','format':'csv','csv':'source_id;brand;model;price_eur\na1;Renault;Clio;9200,50\n'}
        rows,_=prepare(p,'import',NOW)
        self.assertEqual(rows[0].price_cents,920050)


class PersistenceTests(Base):
    def test_idempotent_ingestion_and_history(self):
        self.seed();self.seed()
        with db.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM listings').fetchone()[0],100)
            self.assertEqual(conn.execute('SELECT count(*) FROM price_history').fetchone()[0],99)

    def test_price_drop_and_older_input(self):
        self.seed()
        raw=copy.deepcopy(self.payload);raw['listings']=[raw['listings'][0]|{'price_eur':9000,'observed_at':iso(NOW+timedelta(minutes=1))}]
        items,rights=prepare(raw,'demo',NOW+timedelta(minutes=1))
        with db.connect(self.path) as conn:
            self.assertEqual(db.ingest(conn,items,rights,NOW+timedelta(minutes=1))['price_changes'],1)
            self.assertEqual(db.ingest(conn,self.items,self.rights,NOW+timedelta(minutes=2))['ignored_older'],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM price_history WHERE listing_id=?',(items[0].id,)).fetchone()[0],2)

    def test_adapter_rejects_duplicate_ids_before_writing(self):
        self.seed()
        with db.connect(self.path) as conn:
            before=conn.execute('SELECT count(*) FROM listings').fetchone()[0]
            # Valid adapter rejects duplicate source IDs before any transaction.
            bad=copy.deepcopy(self.payload);bad['listings'].append(bad['listings'][0])
            with self.assertRaises(ValueError):prepare(bad,'demo',NOW)
            self.assertEqual(conn.execute('SELECT count(*) FROM listings').fetchone()[0],before)

    def test_capacity_limit_rolls_back(self):
        self.seed()
        with db.connect(self.path) as conn:
            template=tuple(conn.execute('SELECT * FROM listings LIMIT 1').fetchone())
            for i in range(1900):
                row=list(template);row[0]=f'extra{i}';row[2]=f'extra{i}'
                conn.execute('INSERT INTO listings VALUES(?,?,?,?,?,?,?,?,?,?,?)',row)
            new=parse_listing(self.payload['listings'][0]|{'source_id':'over-capacity'},'demo','demo',NOW)
            with self.assertRaisesRegex(ValueError,'Capacité'):db.ingest(conn,[new],self.rights,NOW)
            self.assertEqual(conn.execute('SELECT count(*) FROM listings').fetchone()[0],2000)

    def test_probable_duplicate_conservative(self):
        self.seed();rows=self.rows()
        self.assertEqual(len({r['group_id'] for r in rows}),94)
        a=self.items[0]; b=parse_listing(self.payload['listings'][0]|{'source_id':'different','description':'Completely different legitimate vehicle and description, never a duplicate.'},'demo','demo',NOW)
        self.assertNotEqual(fingerprint(a)[0],fingerprint(b)[0])

    def test_backup_restore_integrity(self):
        self.seed();destination=str(Path(self.tmp.name)/'backup.sqlite');db.backup(self.path,destination)
        with db.connect(destination) as conn:self.assertEqual(len(db.records(conn)),100)
        with self.assertRaises(ValueError):db.backup(self.path,destination)

    def test_retention_cascade(self):
        self.seed()
        with db.connect(self.path) as conn:
            result=db.retention(conn,iso(NOW+timedelta(days=91)))
            self.assertEqual(result['listings_deleted'],100)
            self.assertEqual(conn.execute('SELECT count(*) FROM price_history').fetchone()[0],0)


class ValuationTests(Base):
    def setUp(self):
        super().setUp();self.seed();self.pool=self.rows();self.candidate=next(p for p in self.pool if p['source_id']=='synthetique-0-0')

    def test_nominal_discount(self):
        pool=[]
        for i in range(6):pool.append(self.candidate|{'id':str(i),'group_id':str(i),'price_cents':1100000})
        result=estimate(self.candidate|{'price_cents':920000},pool,now=NOW)
        self.assertEqual(result['discount_pct'],16.36);self.assertTrue(result['opportunity'])

    def test_candidate_and_reposts_excluded(self):
        result=estimate(self.candidate,self.pool,now=NOW)
        self.assertEqual(result['effective_comparables'],14)
        self.assertNotIn(self.candidate['group_id'],{p['group_id'] for p in result['comparables']})
        changed=self.candidate|{'price_cents':500000}
        self.assertEqual(result['market_price_cents'],estimate(changed,self.pool,now=NOW)['market_price_cents'])

    def test_no_double_count_missing_trim(self):
        candidate=self.candidate|{'trim':None}
        result=estimate(candidate,self.pool,now=NOW)
        self.assertIsNone(result['market_price_cents']);self.assertIn('trim',result['missing_fields'])

    def test_incompatible_engines_sellers_generations(self):
        for field in ['engine','seller','generation','fuel','gearbox','trim','region']:
            peers=[p|{field:'incompatible'} for p in self.pool]
            with self.subTest(field=field):self.assertEqual(estimate(self.candidate,peers,now=NOW)['effective_comparables'],0)

    def test_four_unique_peers_never_eight(self):
        peers=[self.candidate|{'id':f'c{i}','group_id':str(i),'price_cents':1100000} for i in range(4)]
        peers+= [p|{'id':'repost'+p['id']} for p in peers]
        result=estimate(self.candidate,peers,now=NOW)
        self.assertEqual(result['effective_comparables'],4);self.assertIsNone(result['market_price_cents'])

    def test_damage_financing_stale_are_not_opportunities(self):
        for sid in ['synthetique-dommage','synthetique-financement','synthetique-perime','synthetique-incomplet']:
            r=next(p for p in self.pool if p['source_id']==sid)
            with self.subTest(sid=sid): self.assertFalse(estimate(r,self.pool,now=NOW)['opportunity'])

    def test_future_peers_and_sparse_groups(self):
        peers=[p|{'observed_at':iso(NOW+timedelta(days=1))} for p in self.pool]
        self.assertIsNone(estimate(self.candidate,peers,now=NOW)['market_price_cents'])
        self.assertIsNone(estimate(self.candidate,[],now=NOW)['market_price_cents'])

    def test_dispersion_causes_abstention(self):
        peers=[self.candidate|{'id':f'p{i}','group_id':f'p{i}','price_cents':price*100} for i,price in enumerate([3000,4000,10000,20000,40000,60000])]
        result=estimate(self.candidate,peers,now=NOW)
        self.assertEqual(result['confidence'],'faible');self.assertFalse(result['opportunity'])

    def test_demo_has_six_opportunities(self):
        result=rank(self.pool,{'only_deals':True},now=NOW)
        self.assertEqual(len(result),6)
        self.assertTrue(all(r['valuation']['sensitivity_discount_range'] for r in result))

    def test_sensitivity_range_matches_exhaustive_deletions(self):
        from statistics import median
        for prices in [[10000,10000,11000,12000,12000,15000],[9000,10000,10100,10500,11000,12000,14000]]:
            peers=[self.candidate|{'id':f's{i}','group_id':f's{i}','price_cents':p*100} for i,p in enumerate(prices)]
            val=estimate(self.candidate,peers,now=NOW)
            discounts=[]
            for i in range(len(prices)):
                base=median(prices[:i]+prices[i+1:])*100
                discounts.append((base-self.candidate['price_cents'])/base*100)
            self.assertEqual(val['sensitivity_discount_range'],[round(min(discounts),2),round(max(discounts),2)])

    def test_geo_and_budget_filters(self):
        results=rank(self.pool,{'latitude':48.82,'longitude':2.36,'radius_km':1,'max_price_eur':15000},now=NOW)
        self.assertTrue(results);self.assertTrue(all(r['distance_km']<=1 and r['price_cents']<=1500000 for r in results))
        with self.assertRaises(ValueError):validate_filters({'radius_km':10})
        with self.assertRaises(ValueError):validate_filters({'sort':'injection'})


class FakeTransport:
    name='test'
    def __init__(self,fail=False):self.ids=[];self.fail=fail
    def send(self,p):
        if self.fail:raise DeliveryError('HTTP 429',retry_after=10)
        self.ids.append(p['listing_id']);return 'test livré'


class AlertTests(Base):
    def setUp(self):
        super().setUp();self.seed()
        with db.connect(self.path) as conn:conn.execute('INSERT INTO searches VALUES(?,?,?,?,?)',('s','owner','Test','{}',iso(NOW)))

    def test_queue_and_delivery_idempotent(self):
        with db.connect(self.path) as conn:
            self.assertEqual(queue(conn,db.records(conn),now=NOW),6)
            self.assertEqual(queue(conn,db.records(conn),now=NOW),0)
            transport=FakeTransport();self.assertEqual(drain(conn,transport,NOW)['sent'],6)
            self.assertEqual(drain(conn,transport,NOW)['sent'],0);self.assertEqual(len(transport.ids),6)

    def test_retry_and_per_message_status(self):
        with db.connect(self.path) as conn:
            queue(conn,db.records(conn),now=NOW)
            r=drain(conn,FakeTransport(True),NOW,limit=1)
            self.assertEqual(r['retry'],1)
            self.assertEqual(conn.execute("SELECT count(*) FROM outbox WHERE state='sent'").fetchone()[0],0)
            drain(conn,FakeTransport(),NOW,limit=2)
            self.assertEqual(conn.execute("SELECT count(*) FROM outbox WHERE state='sent'").fetchone()[0],2)
            r=drain(conn,FakeTransport(),NOW+timedelta(seconds=11))
            self.assertEqual(r['sent'],4)

    def test_concurrent_claims(self):
        with db.connect(self.path) as conn:queue(conn,db.records(conn),now=NOW)
        transports=[FakeTransport(),FakeTransport()];errors=[]
        def worker(t):
            try:
                with db.connect(self.path) as conn:drain(conn,t,NOW)
            except Exception as e: errors.append(e)
        threads=[threading.Thread(target=worker,args=(t,)) for t in transports]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertFalse(errors)
        ids=transports[0].ids+transports[1].ids
        self.assertEqual(len(ids),6);self.assertEqual(len(set(ids)),6)


class ApiTests(Base):
    def test_body_size_limit(self):
        self.assertEqual(self.request('POST','/api/import',{'oversize':'x'*1_048_576})['status'],413)

    def test_forged_and_expired_cookie(self):
        self.request('GET','/api/session')
        for token in ['fake','0.nonce.'+self.app.sign('0.nonce')]:
            self.assertEqual(self.request('GET','/api/summary',bearer=False,cookie='repere_session='+token)['status'],401)

    def test_auth_and_security_headers(self):
        r=self.request('GET','/api/summary',bearer=False);self.assertEqual(r['status'],401)
        self.assertEqual(r['headers']['X-Frame-Options'],'DENY')
        self.assertIn("script-src 'self'",r['headers']['Content-Security-Policy'])

    def test_login_cookie_csrf_and_logout(self):
        r=self.request('POST','/api/login',{'token':'T'*40},bearer=False)
        self.assertEqual(r['status'],200)
        cookie=r['headers']['Set-Cookie'].split(';')[0];csrf=r['body']['csrf']
        self.assertEqual(self.request('GET','/api/session',cookie=cookie,bearer=False)['body']['authenticated'],True)
        self.assertEqual(self.request('POST','/api/run-alerts',cookie=cookie,bearer=False)['status'],403)
        self.assertEqual(self.request('POST','/api/logout',cookie=cookie,csrf=csrf,bearer=False)['status'],200)

    def test_login_rate_limit(self):
        for _ in range(10):self.request('POST','/api/login',{'token':'bad'},bearer=False)
        self.assertEqual(self.request('POST','/api/login',{'token':'bad'},bearer=False)['status'],429)

    def test_cross_origin_refused(self):
        self.assertEqual(self.request('POST','/api/run-alerts',origin='https://evil.invalid')['status'],403)

    def test_empty_readiness_and_unknown_source(self):
        self.assertEqual(self.request('GET','/ready')['status'],200)
        self.assertEqual(self.request('GET','/api/listings')['body']['total'],0)
        sources=self.request('GET','/api/sources')['body']['sources']
        self.assertEqual(sum(x['live_status']=='blocked_permission' for x in sources),4)

    def test_end_to_end_ingest_rank_detail_search_alert(self):
        self.assertEqual(self.request('POST','/api/import',self.payload)['status'],200)
        result=self.request('GET','/api/listings?only_deals=true')['body']
        self.assertEqual(result['total'],6)
        detail=self.request('GET','/api/listings/'+result['listings'][0]['id'])
        self.assertTrue(detail['body']['price_history'])
        search=self.request('POST','/api/searches',{'name':'Mes Renault','filters':{'brand':'Renault'}})
        self.assertEqual(search['status'],201);self.assertEqual(search['body']['queued'],1)
        r=self.request('POST','/api/run-alerts')['body']
        self.assertEqual(r['delivery']['simulated'],1);self.assertEqual(r['delivery']['transport'],'simulation')
        self.assertEqual(self.request('POST','/api/run-alerts')['body']['delivery']['sent'],0)

    def test_import_validation_is_atomic(self):
        bad=copy.deepcopy(self.payload);bad['listings'][-1]['year']='nonsense'
        self.assertEqual(self.request('POST','/api/import',bad)['status'],400)
        self.assertEqual(self.request('GET','/api/listings')['body']['total'],0)
        self.assertEqual(self.request('GET','/api/sources')['body']['sources'][-1]['import']['failures'],1)

    def test_invalid_filters_and_pagination(self):
        for path in ['/api/listings?max_price_eur=NaN','/api/listings?limit=100000','/api/listings?brand=a&brand=b','/api/listings?unexpected=true']:
            with self.subTest(path=path):self.assertEqual(self.request('GET',path)['status'],400)

    def test_delete_vehicle_group_and_search(self):
        self.seed();r=self.rows()[0]
        self.assertEqual(self.request('DELETE','/api/listings/'+r['id'])['status'],200)
        self.assertEqual(self.request('GET','/api/listings/'+r['id'])['status'],404)
        s=self.request('POST','/api/searches',{'name':'Test','filters':{}})['body']
        self.assertEqual(self.request('DELETE','/api/searches/'+s['id'])['status'],200)
        self.assertEqual(self.request('GET','/api/alerts')['body']['alerts'],[])

    def test_production_config_requires_https_and_distinct_secrets(self):
        with self.assertRaises(ValueError):Config(self.path,environment='production',access_token='T'*40,session_secret='S'*40)
        with self.assertRaises(ValueError):Config(self.path,access_token='T'*40,session_secret='T'*40)


class TemporalTests(Base):
    def test_temporal_disjoint_groups_and_metrics(self):
        from repere.evaluation import evaluate
        self.seed();candidate=next(r for r in self.rows() if r['source_id']=='synthetique-0-0')
        train=[candidate|{'id':f'train{i}','group_id':f'g{i}','observed_at':iso(NOW-timedelta(days=1)),'price_cents':1100000} for i in range(6)]
        # The candidate's own previous appearance must not become training data.
        prior=candidate|{'observed_at':iso(NOW-timedelta(days=1))}
        target=candidate|{'price_cents':920000,'observed_at':iso(NOW)}
        report=evaluate(train+[prior,target],iso(NOW-timedelta(hours=12)),iso(NOW))
        self.assertEqual(report['training_vehicles'],6)
        self.assertEqual(report['holdout_vehicles'],1)
        self.assertEqual(report['metrics']['mae_eur'],1800)
        self.assertEqual(report['metrics']['rmse_eur'],1800)
        self.assertTrue(report['synthetic'])

    def test_sparse_holdout_abstains(self):
        from repere.evaluation import evaluate
        self.seed()
        report=evaluate(self.rows(),iso(NOW-timedelta(days=1)),iso(NOW))
        self.assertGreater(report['abstained'],0)
        self.assertIsNone(report['metrics']['mae_eur'])


class FailureTests(Base):
    def setUp(self):
        super().setUp();self.seed()
        with db.connect(self.path) as conn:conn.execute('INSERT INTO searches VALUES(?,?,?,?,?)',('s','owner','Test','{}',iso(NOW)))
    def test_expired_credentials_not_retried(self):
        class Expired(FakeTransport):
            def send(self,p):raise DeliveryError('Telegram HTTP 401',permanent=True)
        with db.connect(self.path) as conn:
            queue(conn,db.records(conn),now=NOW)
            result=drain(conn,Expired(),NOW,limit=1)
            self.assertEqual(result['failed'],1)
            self.assertEqual(conn.execute("SELECT count(*) FROM outbox WHERE state='failed'").fetchone()[0],1)

    def test_significant_price_drop_and_cooldown(self):
        with db.connect(self.path) as conn:
            queue(conn,db.records(conn),now=NOW);drain(conn,FakeTransport(),NOW)
            pool=db.records(conn)
            # Change all views of the selected probable vehicle; one event only.
            group=next(r['group_id'] for r in pool if r['source_id']=='synthetique-0-0')
            pool=[r|{'price_cents':800000} if r['group_id']==group else r for r in pool]
            self.assertEqual(queue(conn,pool,now=NOW+timedelta(minutes=1)),1)
            self.assertEqual(drain(conn,FakeTransport(),NOW+timedelta(minutes=2))['sent'],0)
            self.assertEqual(drain(conn,FakeTransport(),NOW+timedelta(hours=25))['sent'],1)


if __name__=='__main__':unittest.main()
