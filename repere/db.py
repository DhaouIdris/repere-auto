import json
import sqlite3
from pathlib import Path
from .model import Listing, fingerprint, iso, date

ROOT=Path(__file__).resolve().parent.parent
SCHEMA_VERSION=2


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()


def connect(path):
    db=sqlite3.connect(path,timeout=10,isolation_level=None,factory=Connection)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    return db


def _script(db,path):
    # executescript implicitly commits an existing transaction. Execute complete
    # statements instead so schema changes and regrouping roll back together.
    statement=''
    for line in path.read_text().splitlines(keepends=True):
        statement+=line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement=''
    if statement.strip(): raise ValueError('Migration SQL incomplète')


def _normalize_groups(db):
    mapping={}
    for row in db.execute('SELECT id,group_id,payload FROM listings ORDER BY id').fetchall():
        item=Listing(**json.loads(row['payload']))
        group,basis=fingerprint(item)
        mapping.setdefault(row['group_id'],set()).add(group)
        db.execute('UPDATE listings SET group_id=?,duplicate_basis=? WHERE id=?',(group,basis,row['id']))
    alerts=db.execute('SELECT * FROM outbox ORDER BY created_at,id').fetchall()
    # Free all unique event keys first, then reconcile aliases. Keep every
    # historical message; duplicate legacy keys stay inactive and auditable.
    for row in alerts:
        db.execute('UPDATE outbox SET event_key=? WHERE id=?',('migration:'+row['id'],row['id']))
    priority={'sent':0,'failed':1,'pending':2,'cancelled':3}
    seen=set()
    for row in sorted(alerts,key=lambda r:(priority.get(r['state'],1),r['created_at'],r['id'])):
        groups=mapping.get(row['group_id'],set())
        if len(groups)!=1:
            state='cancelled' if row['state']=='pending' else row['state']
            db.execute('UPDATE outbox SET state=?,last_error=? WHERE id=?',(state,'Migration : rapprochement ambigu, événement non réarmé',row['id']))
            continue
        group=next(iter(groups)); key=(row['search_id'],group,row['event_key'])
        duplicate=key in seen;seen.add(key)
        state='cancelled' if duplicate and row['state']=='pending' else row['state']
        db.execute('UPDATE outbox SET group_id=?,event_key=?,state=?,last_error=? WHERE id=?',
            (group,'migration:'+row['id'] if duplicate else row['event_key'],state,
             'Migration : doublon regroupé, aucun nouvel envoi' if duplicate else row['last_error'],row['id']))


def initialize(path,mode):
    if mode not in ['demo','import']: raise ValueError('Mode demo ou import requis')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with connect(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        current=db.execute('PRAGMA user_version').fetchone()[0]
        if current>SCHEMA_VERSION: raise ValueError('Version de base plus récente que le logiciel')
        if current and db.execute("SELECT value FROM metadata WHERE key='mode'").fetchone()[0]!=mode:
            raise ValueError('Cette base appartient à un autre mode ; créer une base distincte')
        db.execute('BEGIN IMMEDIATE')
        try:
            # Re-read after acquiring the migration lock (concurrent startups).
            current=db.execute('PRAGMA user_version').fetchone()[0]
            if current>SCHEMA_VERSION: raise ValueError('Version de base plus récente que le logiciel')
            if current==0:
                _script(db,ROOT/'migrations/001_core.sql')
                db.execute('INSERT INTO metadata VALUES(?,?)',('mode',mode))
                current=1
            if db.execute("SELECT value FROM metadata WHERE key='mode'").fetchone()[0]!=mode:
                raise ValueError('Cette base appartient à un autre mode ; créer une base distincte')
            if current==1:
                _script(db,ROOT/'migrations/002_alert_claims.sql')
                _normalize_groups(db)
            db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            raise


def records(db):
    rows=[]
    for r in db.execute('SELECT * FROM listings ORDER BY id'):
        d=json.loads(r['payload'])
        d.update({k:r[k] for k in ['id','group_id','duplicate_basis','rights_reference','first_seen','last_seen','last_price_change']})
        rows.append(d)
    return rows


def ingest(db, items, rights, now):
    counts={'inserted':0,'updated':0,'price_changes':0,'ignored_older':0,'ignored_identical':0,'probable_duplicates':0}
    owns_transaction=not db.in_transaction
    if owns_transaction: db.execute('BEGIN IMMEDIATE')
    try:
        total=db.execute('SELECT count(*) FROM listings').fetchone()[0]
        added=sum(db.execute('SELECT 1 FROM listings WHERE id=?',(x.id,)).fetchone() is None for x in items)
        if total+added>2000: raise ValueError('Capacité locale : 2 000 annonces ; appliquer la rétention avant import')
        for item in items:
            old=db.execute('SELECT * FROM listings WHERE id=?',(item.id,)).fetchone()
            serialized=json.dumps(item.to_dict(),ensure_ascii=False,sort_keys=True,separators=(',',':'))
            if old:
                previous=json.loads(old['payload'])
                ordering=(date(item.observed_at)>date(previous['observed_at']))-(date(item.observed_at)<date(previous['observed_at']))
                if ordering<0:
                    counts['ignored_older']+=1
                    continue
                if ordering==0:
                    if serialized!=json.dumps(previous,ensure_ascii=False,sort_keys=True,separators=(',',':')):
                        raise ValueError('Conflit : contenus divergents pour la même annonce et date d’observation')
                    counts['ignored_identical']+=1
                    continue
            group,basis=fingerprint(item)
            if old: group,basis=old['group_id'],old['duplicate_basis']
            if not old and db.execute('SELECT 1 FROM listings WHERE group_id=?',(group,)).fetchone(): counts['probable_duplicates']+=1
            changed=bool(old and item.price_cents is not None and old['price_cents']!=item.price_cents)
            if changed: counts['price_changes']+=1
            last_change=item.observed_at if changed else (old['last_price_change'] if old else None)
            if not old:
                db.execute('INSERT INTO listings VALUES(?,?,?,?,?,?,?,?,?,?,?)',(item.id,item.source,item.source_id,group,basis,item.price_cents,serialized,rights,iso(now),iso(now),last_change))
                counts['inserted']+=1
            else:
                db.execute('UPDATE listings SET price_cents=?,payload=?,rights_reference=?,last_seen=?,last_price_change=? WHERE id=?',(item.price_cents,serialized,rights,iso(now),last_change,item.id))
                counts['updated']+=1
            if item.price_cents is not None and (not old or changed):
                db.execute('INSERT INTO price_history(listing_id,observed_at,price_cents) VALUES(?,?,?)',(item.id,item.observed_at,item.price_cents))
            db.execute('INSERT INTO source_status(source,last_attempt,last_success,imported) VALUES(?,?,?,1) ON CONFLICT(source) DO UPDATE SET last_attempt=excluded.last_attempt,last_success=excluded.last_success,imported=source_status.imported+1,last_error=NULL',(item.source,iso(now),iso(now)))
        if owns_transaction: db.execute('COMMIT')
    except Exception:
        if owns_transaction: db.execute('ROLLBACK')
        raise
    return counts


def failure(db,source,message,now):
    db.execute('INSERT INTO source_status(source,last_attempt,failures,last_error) VALUES(?,?,1,?) ON CONFLICT(source) DO UPDATE SET last_attempt=excluded.last_attempt,failures=source_status.failures+1,last_error=excluded.last_error',(source,iso(now),message[:300]))


def backup(path,destination):
    target=Path(destination)
    if target.exists(): raise ValueError('La destination existe déjà')
    target.parent.mkdir(parents=True,exist_ok=True)
    with connect(path) as source,sqlite3.connect(target) as dest:
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Sauvegarde invalide')


def retention(db, before):
    db.execute('BEGIN IMMEDIATE')
    try:
        listings=db.execute('DELETE FROM listings WHERE last_seen<?',(before,)).rowcount
        alerts=db.execute('DELETE FROM outbox WHERE created_at<?',(before,)).rowcount
        db.execute('DELETE FROM login_attempts WHERE window<?',(int(date(before).timestamp()),))
        db.execute('COMMIT')
        return {'listings_deleted':listings,'alerts_deleted':alerts}
    except Exception:
        db.execute('ROLLBACK')
        raise
