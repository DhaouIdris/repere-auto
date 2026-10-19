import json
import sqlite3
from pathlib import Path
from .model import fingerprint, iso, date

ROOT=Path(__file__).resolve().parent.parent


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


def initialize(path,mode):
    if mode not in ['demo','import']: raise ValueError('Mode demo ou import requis')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with connect(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        current=db.execute('PRAGMA user_version').fetchone()[0]
        if current>1: raise ValueError('Version de base plus récente que le logiciel')
        if current==0:
            sql=(ROOT/'migrations/001_core.sql').read_text()
            db.executescript('BEGIN IMMEDIATE;\n'+sql+f"\nINSERT INTO metadata VALUES('mode','{mode}');\nPRAGMA user_version=1;\nCOMMIT;")
        saved=db.execute("SELECT value FROM metadata WHERE key='mode'").fetchone()[0]
        if saved!=mode: raise ValueError('Cette base appartient à un autre mode ; créer une base distincte')


def records(db):
    rows=[]
    for r in db.execute('SELECT * FROM listings ORDER BY id'):
        d=json.loads(r['payload'])
        d.update({k:r[k] for k in ['id','group_id','duplicate_basis','rights_reference','first_seen','last_seen','last_price_change']})
        rows.append(d)
    return rows


def ingest(db, items, rights, now):
    counts={'inserted':0,'updated':0,'price_changes':0,'ignored_older':0,'probable_duplicates':0}
    db.execute('BEGIN IMMEDIATE')
    try:
        total=db.execute('SELECT count(*) FROM listings').fetchone()[0]
        added=sum(db.execute('SELECT 1 FROM listings WHERE id=?',(x.id,)).fetchone() is None for x in items)
        if total+added>2000: raise ValueError('Capacité locale : 2 000 annonces ; appliquer la rétention avant import')
        for item in items:
            old=db.execute('SELECT * FROM listings WHERE id=?',(item.id,)).fetchone()
            if old and date(item.observed_at)<date(json.loads(old['payload'])['observed_at']):
                counts['ignored_older']+=1
                continue
            group,basis=fingerprint(item)
            if old: group,basis=old['group_id'],old['duplicate_basis']
            if not old and db.execute('SELECT 1 FROM listings WHERE group_id=?',(group,)).fetchone(): counts['probable_duplicates']+=1
            changed=bool(old and item.price_cents is not None and old['price_cents']!=item.price_cents)
            if changed: counts['price_changes']+=1
            last_change=item.observed_at if changed else (old['last_price_change'] if old else None)
            if not old:
                db.execute('INSERT INTO listings VALUES(?,?,?,?,?,?,?,?,?,?,?)',(item.id,item.source,item.source_id,group,basis,item.price_cents,json.dumps(item.to_dict(),ensure_ascii=False),rights,iso(now),iso(now),last_change))
                counts['inserted']+=1
            else:
                db.execute('UPDATE listings SET price_cents=?,payload=?,rights_reference=?,last_seen=?,last_price_change=? WHERE id=?',(item.price_cents,json.dumps(item.to_dict(),ensure_ascii=False),rights,iso(now),last_change,item.id))
                counts['updated']+=1
            if item.price_cents is not None and (not old or changed):
                db.execute('INSERT INTO price_history(listing_id,observed_at,price_cents) VALUES(?,?,?)',(item.id,item.observed_at,item.price_cents))
            db.execute('INSERT INTO source_status(source,last_attempt,last_success,imported) VALUES(?,?,?,1) ON CONFLICT(source) DO UPDATE SET last_attempt=excluded.last_attempt,last_success=excluded.last_success,imported=source_status.imported+1,last_error=NULL',(item.source,iso(now),iso(now)))
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
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
