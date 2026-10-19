import argparse
from datetime import timedelta
import json
import logging
import os
from pathlib import Path
import secrets
from dataclasses import replace
from wsgiref.simple_server import make_server
from .adapters import JsonAdapter,prepare
from .alerts import queue,drain,DryRun,Telegram
from .config import Config,from_env
from .db import initialize,connect,ingest,records,backup,retention
from .demo import payload
from .model import utcnow,iso
from .web import Application


def main():
    parser=argparse.ArgumentParser(description='Repère Auto — annonces françaises, démo/import autorisé')
    parser.add_argument('--db',default=os.environ.get('DATABASE_PATH','data/repere-demo.sqlite'))
    parser.add_argument('--mode',choices=['demo','import'],default=os.environ.get('DATA_MODE','demo'))
    commands=parser.add_subparsers(dest='command',required=True)
    demo=commands.add_parser('demo',help='Initialiser une démo synthétique et démarrer en local')
    demo.add_argument('--port',type=int,default=8080)
    commands.add_parser('seed-demo',help='Charger les données synthétiques sans démarrer de serveur')
    imp=commands.add_parser('import',help='Importer une enveloppe JSON autorisée (ou CSV encapsulé)')
    imp.add_argument('file')
    commands.add_parser('init')
    commands.add_parser('serve',help='Serveur de développement local ; production via Gunicorn')
    alerts=commands.add_parser('alerts');alerts.add_argument('--transport',choices=['simulation','telegram'],default='simulation')
    back=commands.add_parser('backup');back.add_argument('destination')
    prune=commands.add_parser('prune');prune.add_argument('--days',type=int,default=90)
    evaluate=commands.add_parser('evaluate');evaluate.add_argument('--cutoff',required=True);evaluate.add_argument('--as-of',required=True)
    args=parser.parse_args()
    initialize(args.db,args.mode)
    now=utcnow()
    if args.command in ('seed-demo','demo'):
        if args.mode!='demo': parser.error('Données synthétiques réservées au mode demo')
        with connect(args.db) as db:
            items,rights=prepare(payload(now),'demo',now)
            print(json.dumps(ingest(db,items,rights,now)))
    if args.command=='import':
        path=Path(args.file)
        if path.stat().st_size>1_048_576: parser.error('Fichier limité à 1 Mio')
        items,rights=prepare(JsonAdapter().read(path.read_bytes()),args.mode,now)
        with connect(args.db) as db:
            print(json.dumps(ingest(db,items,rights,now)))
    if args.command=='backup':
        backup(args.db,args.destination)
        print('Sauvegarde SQLite créée et vérifiée')
    if args.command=='evaluate':
        from .evaluation import evaluate
        with connect(args.db) as db: print(json.dumps(evaluate(records(db),args.cutoff,args.as_of),ensure_ascii=False,indent=2))
    if args.command=='prune':
        if not 1<=args.days<=3650: parser.error('Rétention : 1 à 3650 jours')
        with connect(args.db) as db: print(json.dumps(retention(db,iso(now-timedelta(days=args.days)))))
    if args.command=='alerts':
        config=from_env()
        transport=Telegram() if args.transport=='telegram' else DryRun()
        with connect(args.db) as db:
            n=queue(db,records(db),config.rules,now,config.cooldown_hours,config.price_drop_pct)
            print(json.dumps({'queued':n,'delivery':drain(db,transport,rules=config.rules)},ensure_ascii=False))
    if args.command in ('demo','serve'):
        logging.basicConfig(level=logging.INFO,format='%(message)s')
        if args.command=='demo':
            token=secrets.token_urlsafe(32)
            config=Config(args.db,'demo',access_token=token,session_secret=secrets.token_urlsafe(32),origin=f'http://127.0.0.1:{args.port}')
            print(f'\nDémo locale : {config.origin}\nCode d’accès temporaire : {token}\n',flush=True)
        else:
            config=replace(from_env(),db_path=args.db,mode=args.mode)
            if config.environment!='development': parser.error('Utiliser Gunicorn pour staging/production')
        from urllib.parse import urlsplit
        u=urlsplit(config.origin)
        app=Application(config)
        with make_server(u.hostname,u.port or 8080,app) as server: server.serve_forever()


if __name__=='__main__': main()
