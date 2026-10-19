import hashlib
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from datetime import timedelta
from .model import date,iso,utcnow
from .valuation import rank, validate_filters
from .db import records


def _payload(row,search_name,event,now):
    return {'vehicle':f'{row["brand"]} {row["model"]} {row["engine"]}', 'listing_id':row['id'],
        'price_cents':row['price_cents'],'market_price_cents':row['valuation']['market_price_cents'],
        'discount_pct':row['valuation']['discount_pct'],'confidence':row['valuation']['confidence'],
        'source':row['source'],'city':row['city'],'url':row['url'],'search_name':search_name,
        'event':event,'synthetic':row['source']=='demo','valuation_at':iso(now),'observed_at':row['observed_at']}


def _current(db,event,rules,now):
    search=db.execute('SELECT * FROM searches WHERE id=?',(event['search_id'],)).fetchone()
    if not search:return None
    filters=validate_filters(json.loads(search['filters']))|{'only_deals':True}
    rows=rank(records(db),filters,rules,now,group_id=event['group_id'])
    if not rows:return None
    previous=json.loads(event['payload'])
    if rows[0]['price_cents']!=previous['price_cents']:return None
    return _payload(rows[0],search['name'],previous['event'],now)


def queue(db,pool,rules=None,now=None,cooldown_hours=24,price_drop_pct=3):
    now=now or utcnow()
    count=0
    # Also serialize search deletion and competing scheduler/import jobs.
    owns_transaction=not db.in_transaction
    if owns_transaction: db.execute('BEGIN IMMEDIATE')
    try:
        for search in db.execute('SELECT * FROM searches').fetchall():
            filters=validate_filters(json.loads(search['filters']))
            filters['only_deals']=True
            eligible={r['group_id']:r for r in rank(pool,filters,rules,now)}
            for pending in db.execute("SELECT * FROM outbox WHERE search_id=? AND state='pending'",(search['id'],)).fetchall():
                current=eligible.get(pending['group_id'])
                if current is None or current['price_cents']!=json.loads(pending['payload'])['price_cents']:
                    db.execute("UPDATE outbox SET state='cancelled',last_error=? WHERE id=? AND state='pending'",('Signal dépassé ou critères non réunis',pending['id']))
            for row in eligible.values():
                group=row['group_id']
                old=db.execute("SELECT payload,created_at FROM outbox WHERE search_id=? AND group_id=? AND state!='cancelled' ORDER BY created_at DESC,rowid DESC LIMIT 1",(search['id'],group)).fetchone()
                due=now
                if old:
                    prior=json.loads(old['payload'])
                    if row['price_cents']>=prior['price_cents']*(1-price_drop_pct/100): continue
                    due=max(now,date(old['created_at'])+timedelta(hours=cooldown_hours))
                event=f'prix:{row["price_cents"]}'
                key=hashlib.sha256(f'{search["id"]}:{group}:{event}'.encode()).hexdigest()[:32]
                message=_payload(row,search['name'],'baisse significative' if old else 'première correspondance',now)
                count+=db.execute("""INSERT INTO outbox(id,search_id,group_id,event_key,payload,state,due_at,created_at)
                    VALUES(?,?,?,?,?,'pending',?,?) ON CONFLICT(search_id,group_id,event_key) DO UPDATE SET
                    payload=excluded.payload,state='pending',due_at=excluded.due_at,created_at=excluded.created_at,
                    attempts=0,last_error=NULL,lease_until=NULL,lease_token=NULL WHERE outbox.state='cancelled'""",
                    (key,search['id'],group,event,json.dumps(message,ensure_ascii=False),iso(due),iso(now))).rowcount
        if owns_transaction: db.execute('COMMIT')
    except Exception:
        if owns_transaction: db.execute('ROLLBACK')
        raise
    return count


class DeliveryError(Exception):
    def __init__(self,message,permanent=False,retry_after=None):
        super().__init__(message)
        self.permanent,self.retry_after=permanent,retry_after


def message(payload):
    p=payload
    money=lambda x: f'{x/100:,.0f} €'.replace(',',' ')
    return '\n'.join(filter(None,[('[DÉMO — SIMULATION] ' if p['synthetic'] else '')+'Repère Auto · '+p['event'],
        p['vehicle'],f"Demandé : {money(p['price_cents'])} · Référence annonces : {money(p['market_price_cents'])}",
        f"Écart : {p['discount_pct']} % · Confiance descriptive : {p['confidence']}",f"{p['source']} · {p['city'] or 'Lieu non renseigné'}",p.get('url'),
        'Calcul : '+p['valuation_at'] if p.get('valuation_at') else None,
        'Prix demandés observés ; état et coûts à vérifier.']))


class DryRun:
    name='simulation'
    def send(self,payload):
        # No external delivery; outcome is explicitly labeled in the outbox.
        return 'simulation locale, aucun message envoyé'


class Telegram:
    name='telegram'
    def __init__(self,token=None,chat_id=None):
        self.token=token or os.environ.get('TELEGRAM_BOT_TOKEN','')
        self.chat_id=chat_id or os.environ.get('TELEGRAM_CHAT_ID','')
        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}',self.token) or not re.fullmatch(r'-?\d+',self.chat_id):
            raise ValueError('Identifiants Telegram manquants ou invalides')

    def send(self,payload):
        if payload['synthetic']: raise DeliveryError('Envoi externe des annonces synthétiques désactivé',True)
        body=json.dumps({'chat_id':self.chat_id,'text':message(payload),'link_preview_options':{'is_disabled':True}}).encode()
        req=urllib.request.Request(f'https://api.telegram.org/bot{self.token}/sendMessage',body,{'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=12) as response:
                result=json.loads(response.read(100000))
                if result.get('ok') is not True: raise DeliveryError('Telegram a refusé le message')
        except urllib.error.HTTPError as e:
            retry=e.headers.get('Retry-After','')
            raise DeliveryError(f'Telegram HTTP {e.code}',e.code in (400,401,403,404),min(86400,max(1,int(retry))) if retry.isdigit() else None) from None
        except (TimeoutError,urllib.error.URLError):
            # Delivery may have happened: stop rather than silently claiming exactly-once.
            raise DeliveryError('Résultat réseau ambigu : contrôle manuel requis',True) from None
        except (ValueError,KeyError): raise DeliveryError('Réponse Telegram invalide') from None
        return 'livré via Telegram'


def drain(db,transport=None,now=None,limit=20,*,rules=None,clock=None,lease_seconds=120):
    transport=transport or DryRun()
    if lease_seconds<=0:raise ValueError('Durée du bail positive requise')
    # Explicit now anchors a progressing clock too; it must never freeze a batch.
    if clock is None:
        anchor,started=now or utcnow(),time.monotonic()
        clock=lambda:anchor+timedelta(seconds=time.monotonic()-started)
    stats={'sent':0,'retry':0,'failed':0,'cancelled':0,'lease_lost':0,'transport':transport.name}
    if isinstance(transport,DryRun):
        # A preview must never consume events intended for a real transport.
        at=clock()
        pending=db.execute("SELECT * FROM outbox WHERE state='pending' AND julianday(due_at)<=julianday(?) ORDER BY julianday(due_at),id LIMIT ?",(iso(at),max(0,min(limit,100)))).fetchall()
        stats['simulated']=sum(_current(db,row,rules,at) is not None for row in pending)
        return stats
    # Claim one message at a time; never mark a batch on partial success.
    for _ in range(max(0,min(limit,100))):
        db.execute('BEGIN IMMEDIATE')
        try:
            at=clock()
            # An expired in-flight message may already have reached Telegram.
            # Quarantine it rather than automatically creating another effect.
            expired=db.execute("UPDATE outbox SET state='failed',lease_until=NULL,lease_token=NULL,last_error=? WHERE state='inflight' AND julianday(lease_until)<=julianday(?)",
                ('Bail expiré : résultat de livraison ambigu, contrôle manuel requis',iso(at))).rowcount
            stats['failed']+=expired
            row=db.execute("SELECT * FROM outbox WHERE state='pending' AND julianday(due_at)<=julianday(?) ORDER BY julianday(due_at),id LIMIT 1",(iso(at),)).fetchone()
            payload=None
            if row:
                payload=_current(db,row,rules,at)
                if payload is None:
                    db.execute("UPDATE outbox SET state='cancelled',last_error=? WHERE id=?",('Signal dépassé ou critères non réunis',row['id']))
                    stats['cancelled']+=1
                else:
                    token=secrets.token_hex(16)
                    claimed_at=clock()
                    db.execute("UPDATE outbox SET state='inflight',attempts=attempts+1,lease_until=?,lease_token=?,payload=? WHERE id=?",
                        (iso(claimed_at+timedelta(seconds=lease_seconds)),token,json.dumps(payload,ensure_ascii=False),row['id']))
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            raise
        if not row: break
        if payload is None:continue
        try:
            outcome=transport.send(payload)
            count=db.execute("UPDATE outbox SET state='sent',sent_at=?,lease_until=NULL,lease_token=NULL,last_error=? WHERE id=? AND state='inflight' AND lease_token=?",
                (iso(clock()),outcome,row['id'],token)).rowcount
            stats['sent' if count else 'lease_lost']+=1
        except Exception as exc:
            permanent=not isinstance(exc,DeliveryError) or exc.permanent or row['attempts']+1>=6
            wait=getattr(exc,'retry_after',None) or min(3600,30*2**row['attempts'])
            # Do not log arbitrary transport exceptions, which might contain secrets.
            error=str(exc)[:160] if isinstance(exc,DeliveryError) else 'Échec interne du transport'
            count=db.execute("UPDATE outbox SET state=?,due_at=?,lease_until=NULL,lease_token=NULL,last_error=? WHERE id=? AND state='inflight' AND lease_token=?",
                ('failed' if permanent else 'pending',iso(clock()+timedelta(seconds=wait)),error,row['id'],token)).rowcount
            stats[('failed' if permanent else 'retry') if count else 'lease_lost']+=1
    return stats
