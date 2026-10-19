import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs
from . import __version__
from . import db as storage
from .adapters import JsonAdapter,prepare,source_registry
from .alerts import queue,drain
from .model import iso,utcnow,text
from .valuation import rank,estimate,validate_filters

STATIC=Path(__file__).resolve().parent.parent/'static'
MAX_BODY=1_048_576
LOGGER=logging.getLogger('repere')


class HttpError(Exception):
    def __init__(self,status,message): self.status,self.message=status,message


class Application:
    def __init__(self,config):
        self.config=config
        storage.initialize(config.db_path,config.mode)

    def sign(self,value):
        return hmac.new(self.config.session_secret.encode(),value.encode(),hashlib.sha256).hexdigest()

    def session(self,environ):
        try:
            jar=SimpleCookie();jar.load(environ.get('HTTP_COOKIE',''))
            token=jar['repere_session'].value
            issued,nonce,signature=token.split('.')
            if not (0<=time.time()-int(issued)<28800 and hmac.compare_digest(self.sign(f'{issued}.{nonce}'),signature)): return None
            return token
        except (KeyError,ValueError): return None

    def body(self,e):
        if e.get('CONTENT_TYPE','').split(';')[0]!='application/json': raise HttpError(415,'Content-Type application/json requis')
        try: size=int(e.get('CONTENT_LENGTH','0'))
        except ValueError: raise HttpError(400,'Longueur invalide') from None
        if not 0<size<=MAX_BODY: raise HttpError(413,'Corps requis, limité à 1 Mio')
        raw=e['wsgi.input'].read(size)
        if len(raw)!=size: raise HttpError(400,'Corps incomplet')
        return JsonAdapter().read(raw)

    def __call__(self,environ,start_response):
        request_id=secrets.token_hex(8)
        started=time.monotonic()
        try:
            status,result,extra=self.handle(environ)
        except HttpError as e: status,result,extra=e.status,{'error':e.message},[]
        except ValueError as e: status,result,extra=400,{'error':str(e)},[]
        except Exception:
            # Never echo SQL, request contents or credentials to the client/log.
            LOGGER.error(json.dumps({'event':'request_error','request_id':request_id}))
            status,result,extra=500,{'error':'Erreur interne ; consulter l’identifiant de requête','request_id':request_id},[]
        body=result if isinstance(result,bytes) else json.dumps(result,ensure_ascii=False,allow_nan=False).encode()
        headers=[('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(body))),('Cache-Control','no-store'),
            ('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),('X-Frame-Options','DENY'),
            ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
            ('X-Request-ID',request_id)]
        if self.config.environment!='development': headers.append(('Strict-Transport-Security','max-age=31536000'))
        for key,value in extra:
            headers=[(k,v) for k,v in headers if k.lower()!=key.lower()]
            headers.append((key,value))
        start_response(f'{status} {HTTPStatus(status).phrase}',headers)
        LOGGER.info(json.dumps({'event':'request','request_id':request_id,'method':environ.get('REQUEST_METHOD'),'status':status,'duration_ms':round((time.monotonic()-started)*1000)}))
        return [b'' if environ.get('REQUEST_METHOD')=='HEAD' else body]

    def handle(self,e):
        method,path=e.get('REQUEST_METHOD','GET'),e.get('PATH_INFO','/')
        if method in ('GET','HEAD') and path in ('/','/app.js','/style.css'):
            filename={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
            content_type={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path]
            return 200,(STATIC/filename).read_bytes(),[('Content-Type',content_type)]
        if method=='GET' and path=='/health': return 200,{'status':'ok','version':__version__},[]
        with storage.connect(self.config.db_path) as db:
            if method=='GET' and path=='/ready':
                okay=db.execute('PRAGMA user_version').fetchone()[0]==storage.SCHEMA_VERSION and db.execute("SELECT value FROM metadata WHERE key='mode'").fetchone()[0]==self.config.mode
                return (200 if okay else 503),{'ready':okay},[]
            mutating=method in ('POST','DELETE','PUT','PATCH')
            origin=e.get('HTTP_ORIGIN')
            if origin and origin.rstrip('/')!=self.config.origin: raise HttpError(403,'Origine refusée')
            if method=='POST' and path=='/api/login':
                client=hashlib.sha256(e.get('REMOTE_ADDR','unknown').encode()).hexdigest()
                window=int(time.time())//60*60
                db.execute('INSERT INTO login_attempts VALUES(?,?,1) ON CONFLICT(client) DO UPDATE SET count=CASE WHEN window=excluded.window THEN count+1 ELSE 1 END,window=excluded.window',(client,window))
                if db.execute('SELECT count FROM login_attempts WHERE client=?',(client,)).fetchone()[0]>10: raise HttpError(429,'Trop de tentatives ; réessayer dans une minute')
                body=self.body(e)
                if not isinstance(body,dict) or not isinstance(body.get('token'),str) or not hmac.compare_digest(body['token'].encode(),self.config.access_token.encode()): raise HttpError(401,'Code d’accès incorrect')
                payload=f'{int(time.time())}.{secrets.token_hex(16)}'
                token=f'{payload}.{self.sign(payload)}'
                cookie=f'repere_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if self.config.environment!='development' else '')
                return 200,{'authenticated':True,'csrf':self.sign('csrf:'+token)},[('Set-Cookie',cookie)]
            session=self.session(e)
            header=e.get('HTTP_AUTHORIZATION','')
            bearer=header.startswith('Bearer ') and hmac.compare_digest(header[7:].encode(),self.config.access_token.encode())
            if path=='/api/session' and method=='GET':
                return 200,{'authenticated':bool(session or bearer),'csrf':self.sign('csrf:'+session) if session else None,'mode':self.config.mode,'environment':self.config.environment},[]
            if not session and not bearer: raise HttpError(401,'Connexion requise')
            if mutating and not bearer and not hmac.compare_digest(e.get('HTTP_X_CSRF_TOKEN',''),self.sign('csrf:'+session)): raise HttpError(403,'Jeton de session invalide')
            if method=='POST' and path=='/api/logout':
                return 200,{'ok':True},[('Set-Cookie','repere_session=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/')]
            now=utcnow()
            if path=='/api/listings' and method=='GET':
                q=parse_qs(e.get('QUERY_STRING',''),keep_blank_values=True)
                if any(len(v)!=1 for v in q.values()): raise ValueError('Paramètre répété')
                raw={k:v[0] for k,v in q.items()}
                try: offset=int(raw.pop('offset','0'));limit=int(raw.pop('limit','60'))
                except ValueError: raise ValueError('Pagination invalide') from None
                if not 0<=offset<=2000 or not 1<=limit<=100: raise ValueError('Pagination hors limites')
                filters=validate_filters(raw)
                all_rows=rank(storage.records(db),filters,self.config.rules,now)
                return 200,{'listings':all_rows[offset:offset+limit],'total':len(all_rows),'mode':self.config.mode,'as_of':iso(now)},[]
            if path.startswith('/api/listings/') and method in ('GET','DELETE'):
                identifier=path.rsplit('/',1)[-1]
                pool=storage.records(db)
                row=next((p for p in pool if p['id']==identifier),None)
                if not row: raise HttpError(404,'Annonce introuvable')
                if method=='DELETE':
                    db.execute('BEGIN IMMEDIATE')
                    try:
                        db.execute('DELETE FROM outbox WHERE group_id=?',(row['group_id'],))
                        db.execute('DELETE FROM listings WHERE group_id=?',(row['group_id'],))
                        db.execute('COMMIT')
                    except Exception:
                        db.execute('ROLLBACK');raise
                    return 200,{'deleted_group':row['group_id']},[]
                row['valuation']=estimate(row,pool,self.config.rules,now)
                row['price_history']=[dict(r) for r in db.execute('SELECT observed_at,price_cents FROM price_history WHERE listing_id=? ORDER BY event_id',(identifier,))]
                row['group_price_history']=[dict(r) for r in db.execute('SELECT h.observed_at,h.price_cents,l.source,h.listing_id FROM price_history h JOIN listings l ON l.id=h.listing_id WHERE l.group_id=? ORDER BY h.observed_at,h.event_id',(row['group_id'],))]
                row['duplicates']=[{'id':p['id'],'source':p['source'],'source_id':p['source_id']} for p in pool if p['group_id']==row['group_id'] and p['id']!=identifier]
                return 200,row,[]
            if path=='/api/import' and method=='POST':
                body=self.body(e)
                try:
                    items,rights=prepare(body,self.config.mode,now)
                    result=storage.ingest(db,items,rights,now)
                except ValueError as exc:
                    source=body.get('source','inconnue') if isinstance(body,dict) else 'inconnue'
                    if source not in ['demo','leboncoin','lacentrale','autoscout24','paruvendu','export']: source='inconnue'
                    storage.failure(db,source,str(exc),now)
                    raise
                result['alerts_queued']=queue(db,storage.records(db),self.config.rules,now,self.config.cooldown_hours,self.config.price_drop_pct)
                return 200,result,[]
            if path=='/api/searches' and method=='GET':
                return 200,{'searches':[dict(r)|{'filters':json.loads(r['filters'])} for r in db.execute('SELECT * FROM searches WHERE owner=? ORDER BY created_at',('owner',))]},[]
            if path=='/api/searches' and method=='POST':
                body=self.body(e)
                if not isinstance(body,dict) or set(body)-{'name','filters'}: raise ValueError('Recherche invalide')
                name=text(body.get('name'),100)
                if not name: raise ValueError('Nom de recherche requis')
                if db.execute('SELECT count(*) FROM searches').fetchone()[0]>=20: raise ValueError('20 recherches maximum')
                filters=validate_filters(body.get('filters',{}))
                identifier=secrets.token_hex(12)
                db.execute('INSERT INTO searches VALUES(?,?,?,?,?)',(identifier,'owner',name,json.dumps(filters),iso(now)))
                return 201,{'id':identifier,'queued':queue(db,storage.records(db),self.config.rules,now,self.config.cooldown_hours,self.config.price_drop_pct)},[]
            if path.startswith('/api/searches/') and method=='DELETE':
                count=db.execute('DELETE FROM searches WHERE id=? AND owner=?',(path.rsplit('/',1)[-1],'owner')).rowcount
                if not count: raise HttpError(404,'Recherche introuvable')
                return 200,{'deleted':True},[]
            if path=='/api/alerts' and method=='GET':
                return 200,{'alerts':[dict(r)|{'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM outbox ORDER BY created_at DESC,id LIMIT 100')]},[]
            if path=='/api/run-alerts' and method=='POST':
                queued=queue(db,storage.records(db),self.config.rules,now,self.config.cooldown_hours,self.config.price_drop_pct)
                return 200,{'queued':queued,'delivery':drain(db,now=now,rules=self.config.rules)},[]
            if path=='/api/sources' and method=='GET': return 200,{'sources':source_registry(self.config.mode,db)},[]
            if path=='/api/summary' and method=='GET':
                rows=rank(storage.records(db),{},self.config.rules,now)
                good=[r for r in rows if r['valuation']['opportunity']]
                return 200,{'vehicles':len(rows),'raw_listings':db.execute('SELECT count(*) FROM listings').fetchone()[0],
                    'opportunities':len(good),'estimated':sum(r['valuation']['market_price_cents'] is not None for r in rows),
                    'best_discount':max((r['valuation']['discount_pct'] for r in good),default=None),
                    'pending_alerts':db.execute("SELECT count(*) FROM outbox WHERE state='pending'").fetchone()[0],
                    'mode':self.config.mode,'rules':vars(self.config.rules),'as_of':iso(now)},[]
            if path=='/api/metrics' and method=='GET':
                return 200,{'listings':db.execute('SELECT count(*) FROM listings').fetchone()[0],
                    'outbox':{r[0]:r[1] for r in db.execute('SELECT state,count(*) FROM outbox GROUP BY state')},
                    'schema_version':db.execute('PRAGMA user_version').fetchone()[0]},[]
            raise HttpError(404,'Route indisponible')


def create_app():
    from .config import from_env
    return Application(from_env())
