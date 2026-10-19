"""Regression scenarios from the phase-one audit; synthetic data only."""
import copy
import json
import sqlite3
from pathlib import Path
from datetime import timedelta
from tests.test_system import Base, NOW, FakeTransport
from repere import db
from repere.adapters import prepare
from repere.alerts import queue, drain
from repere.model import date, fingerprint, iso, parse_listing
from repere.valuation import estimate


class DuplicateRegressions(Base):
    def test_case_variants_are_one_reference(self):
        raw=self.payload['listings'][0]|{'price_eur':11000}
        peers=[]
        for i,(model,trim) in enumerate((m,t) for m in ['Clio','CLIO','clio'] for t in ['Evolution','EVOLUTION']):
            item=parse_listing(raw|{'source_id':f'repost-{i}','model':model,'trim':trim},'demo','demo',NOW)
            peers.append(item.to_dict()|{'id':item.id,'group_id':fingerprint(item)[0]})
        candidate=peers[0]|{'id':'candidate','group_id':'candidate','price_cents':880000}
        result=estimate(candidate,peers,now=NOW)
        self.assertEqual(result['effective_comparables'],1)
        self.assertFalse(result['opportunity'])

    def test_normalization_preserves_mechanical_and_location_differences(self):
        raw=self.payload['listings'][0]
        original=parse_listing(raw,'demo','demo',NOW)
        variants=[{'engine':'TCe 100'},{'month':2},{'postal_code':'75014'},{'mileage_km':99000},
                  {'description':'Un autre véhicule distinct dont le vendeur fournit une description différente.'}]
        for change in variants:
            with self.subTest(change=change):
                item=parse_listing(raw|{'source_id':'other'}|change,'demo','demo',NOW)
                self.assertNotEqual(fingerprint(original)[0],fingerprint(item)[0])


class ObservationRegressions(Base):
    def test_equal_timestamp_non_price_conflict_is_rejected(self):
        self.seed()
        changed=parse_listing(self.payload['listings'][0]|{'warranty':'Autre déclaration'},'demo','demo',NOW)
        with db.connect(self.path) as conn:
            with self.assertRaisesRegex(ValueError,'Conflit'):db.ingest(conn,[changed],self.rights,NOW)

    def test_same_timestamp_conflict_cannot_change_price(self):
        self.seed()
        original=self.items[0]
        changed=parse_listing(self.payload['listings'][0]|{'price_eur':9000},'demo','demo',NOW)
        with db.connect(self.path) as conn:
            before=conn.execute('SELECT count(*) FROM price_history').fetchone()[0]
            with self.assertRaisesRegex(ValueError,'Conflit'):
                db.ingest(conn,[changed],self.rights,NOW+timedelta(minutes=1))
            db.ingest(conn,[original],self.rights,NOW+timedelta(minutes=2))
            self.assertEqual(conn.execute('SELECT price_cents FROM listings WHERE id=?',(original.id,)).fetchone()[0],original.price_cents)
            self.assertEqual(conn.execute('SELECT count(*) FROM price_history').fetchone()[0],before)

    def test_conflict_rolls_back_entire_batch(self):
        self.seed()
        new=parse_listing(self.payload['listings'][0]|{'source_id':'new-first'},'demo','demo',NOW)
        conflict=parse_listing(self.payload['listings'][1]|{'price_eur':12345},'demo','demo',NOW)
        with db.connect(self.path) as conn:
            with self.assertRaises(ValueError):db.ingest(conn,[new,conflict],self.rights,NOW)
            self.assertIsNone(conn.execute('SELECT id FROM listings WHERE id=?',(new.id,)).fetchone())


class StaleAlertRegressions(Base):
    def setUp(self):
        super().setUp();self.seed()
        with db.connect(self.path) as conn:
            conn.execute('INSERT INTO searches VALUES(?,?,?,?,?)',('s','owner','Renault','{"brand":"Renault"}',iso(NOW)))
            queue(conn,db.records(conn),now=NOW)

    def test_higher_price_before_delivery_cancels_event(self):
        raw=copy.deepcopy(self.payload)
        raw['listings']=[r|{'price_eur':16000,'observed_at':iso(NOW+timedelta(minutes=1))}
                         for r in raw['listings'] if r['source_id'].startswith('synthetique-0-0')]
        items,rights=prepare(raw,'demo',NOW+timedelta(minutes=1))
        with db.connect(self.path) as conn:
            db.ingest(conn,items,rights,NOW+timedelta(minutes=1))
            transport=FakeTransport()
            result=drain(conn,transport,NOW+timedelta(minutes=2))
            self.assertEqual(transport.ids,[])
            self.assertEqual(result['sent'],0)
            self.assertEqual(conn.execute('SELECT state FROM outbox').fetchone()[0],'cancelled')

    def test_stale_observation_before_delivery_is_not_sent(self):
        with db.connect(self.path) as conn:
            transport=FakeTransport()
            self.assertEqual(drain(conn,transport,NOW+timedelta(days=15))['sent'],0)
            self.assertEqual(transport.ids,[])

    def test_damage_after_queue_is_not_sent(self):
        with db.connect(self.path) as conn:
            for row in conn.execute("SELECT * FROM listings WHERE group_id=(SELECT group_id FROM outbox LIMIT 1)").fetchall():
                data=json.loads(row['payload'])|{'condition':'endommage'}
                conn.execute('UPDATE listings SET payload=? WHERE id=?',(json.dumps(data),row['id']))
            transport=FakeTransport()
            self.assertEqual(drain(conn,transport,NOW)['sent'],0)
            self.assertEqual(transport.ids,[])

    def test_custom_rules_are_revalidated(self):
        from repere.valuation import Rules
        with db.connect(self.path) as conn:
            transport=FakeTransport()
            self.assertEqual(drain(conn,transport,NOW,rules=Rules(min_discount=50))['sent'],0)

    def test_queue_cancels_a_signal_invalidated_by_comparables(self):
        raw=copy.deepcopy(self.payload)
        raw['listings']=[r|{'price_eur':9000,'observed_at':iso(NOW+timedelta(minutes=1))}
                         for r in raw['listings'] if r.get('brand')=='Renault' and not r['source_id'].startswith('synthetique-0-0')]
        items,rights=prepare(raw,'demo',NOW+timedelta(minutes=1))
        with db.connect(self.path) as conn:
            db.ingest(conn,items,rights,NOW+timedelta(minutes=1))
            self.assertEqual(queue(conn,db.records(conn),now=NOW+timedelta(minutes=2)),0)
            self.assertEqual(conn.execute('SELECT state FROM outbox').fetchone()[0],'cancelled')

    def test_cancelled_undelivered_event_can_become_eligible_again(self):
        from repere.valuation import Rules
        with db.connect(self.path) as conn:
            drain(conn,FakeTransport(),NOW,rules=Rules(min_discount=50))
            self.assertEqual(queue(conn,db.records(conn),now=NOW+timedelta(minutes=1)),1)
            transport=FakeTransport()
            self.assertEqual(drain(conn,transport,NOW+timedelta(minutes=1))['sent'],1)
            self.assertEqual(len(transport.ids),1)


class LeaseRegressions(Base):
    def setUp(self):
        super().setUp();self.seed()
        with db.connect(self.path) as conn:
            conn.execute('INSERT INTO searches VALUES(?,?,?,?,?)',('s','owner','Test','{}',iso(NOW)))
            queue(conn,db.records(conn),now=NOW)

    def test_long_batch_refreshes_each_lease(self):
        at=[NOW]; other=FakeTransport(); starts=[]; owner=self
        class Slow(FakeTransport):
            def send(self,p):
                with db.connect(owner.path) as second:
                    lease=second.execute("SELECT lease_until FROM outbox WHERE state='inflight'").fetchone()[0]
                    starts.append((date(lease)-at[0]).total_seconds())
                    # After two slow sends the old batch clock would already
                    # have made this message reclaimable by another worker.
                    drain(second,other,clock=lambda:at[0],limit=1)
                self.ids.append(p['listing_id'])
                at[0]+=timedelta(seconds=65)
                return 'test livré'
        slow=Slow()
        with db.connect(self.path) as conn:result=drain(conn,slow,clock=lambda:at[0])
        ids=slow.ids+other.ids
        self.assertEqual(len(ids),6);self.assertEqual(len(set(ids)),6)
        self.assertTrue(all(seconds==120 for seconds in starts))
        self.assertGreater((at[0]-NOW).total_seconds(),120)
        self.assertEqual(result['lease_lost'],0)

    def test_expired_inflight_is_quarantined_and_old_ack_is_fenced(self):
        at=[NOW]; other=FakeTransport(); owner=self
        class Expired(FakeTransport):
            def send(self,p):
                self.ids.append(p['listing_id']);at[0]+=timedelta(seconds=121)
                with db.connect(owner.path) as second:
                    drain(second,other,clock=lambda:at[0],limit=1)
                return 'ancien worker terminé'
        old=Expired()
        with db.connect(self.path) as conn:
            result=drain(conn,old,clock=lambda:at[0],limit=1)
            row=conn.execute('SELECT state,last_error,lease_token FROM outbox WHERE json_extract(payload,\'$.listing_id\')=?',(old.ids[0],)).fetchone()
            self.assertEqual(row['state'],'failed')
            self.assertIn('ambigu',row['last_error']);self.assertIsNone(row['lease_token'])
            self.assertEqual(result['lease_lost'],1)
            self.assertNotIn(old.ids[0],other.ids)
            drain(conn,other,clock=lambda:at[0])
            self.assertNotIn(old.ids[0],other.ids)

    def test_stale_owner_cannot_retry_another_claim(self):
        from repere.alerts import DeliveryError
        class Replaced(FakeTransport):
            def send(inner,p):
                conn.execute("UPDATE outbox SET lease_token='new-owner' WHERE state='inflight'")
                raise DeliveryError('HTTP 429',retry_after=10)
        with db.connect(self.path) as conn:
            result=drain(conn,Replaced(),NOW,limit=1)
            self.assertEqual(result['lease_lost'],1)
            row=conn.execute("SELECT state,lease_token FROM outbox WHERE lease_token='new-owner'").fetchone()
            self.assertEqual(row['state'],'inflight')


class MigrationRegressions(Base):
    def legacy(self):
        path=str(Path(self.tmp.name)/'legacy.sqlite')
        with db.connect(path) as conn:
            conn.executescript((db.ROOT/'migrations/001_core.sql').read_text())
            conn.execute("INSERT INTO metadata VALUES('mode','demo')")
            conn.execute('PRAGMA user_version=1')
            raw=self.payload['listings'][0]
            variants=[parse_listing(raw|{'source_id':str(i),'model':m},'demo','demo',NOW) for i,m in enumerate(['Clio','CLIO'])]
            db.ingest(conn,variants,self.rights,NOW)
            conn.execute('INSERT INTO searches VALUES(?,?,?,?,?)',('s','owner','Test','{}',iso(NOW)))
            for i,item in enumerate(variants):
                group='legacy-'+str(i)
                conn.execute('UPDATE listings SET group_id=? WHERE id=?',(group,item.id))
                data=json.dumps({'listing_id':item.id,'price_cents':item.price_cents})
                conn.execute('INSERT INTO outbox(id,search_id,group_id,event_key,payload,state,due_at,created_at) VALUES(?,?,?,?,?,?,?,?)',
                    ('alert-'+str(i),'s',group,'prix:'+str(item.price_cents),data,'sent' if i==0 else 'pending',iso(NOW),iso(NOW)))
        return path

    def test_v1_groups_and_alerts_migrate_without_replay_or_loss(self):
        path=self.legacy();db.initialize(path,'demo');db.initialize(path,'demo')
        with db.connect(path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertEqual(conn.execute('SELECT count(DISTINCT group_id) FROM listings').fetchone()[0],1)
            states=[r[0] for r in conn.execute('SELECT state FROM outbox')]
            self.assertCountEqual(states,['sent','cancelled'])
            self.assertEqual(conn.execute('SELECT count(*) FROM price_history').fetchone()[0],2)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_failed_migration_is_atomic(self):
        from unittest.mock import patch
        path=self.legacy()
        with patch('repere.db._normalize_groups',side_effect=RuntimeError('test interruption')):
            with self.assertRaises(RuntimeError):db.initialize(path,'demo')
        with db.connect(path) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertNotIn('lease_token',[r['name'] for r in conn.execute('PRAGMA table_info(outbox)')])
            self.assertEqual(conn.execute('SELECT count(*) FROM outbox').fetchone()[0],2)
        db.initialize(path,'demo')

    def test_old_inflight_is_not_automatically_replayed(self):
        path=self.legacy()
        with db.connect(path) as conn:conn.execute("UPDATE outbox SET state='inflight' WHERE id='alert-0'")
        db.initialize(path,'demo')
        with db.connect(path) as conn:
            row=conn.execute("SELECT state,last_error,lease_token FROM outbox WHERE id='alert-0'").fetchone()
            self.assertEqual(row['state'],'failed');self.assertIn('ambigu',row['last_error'])
            self.assertIsNone(row['lease_token'])
