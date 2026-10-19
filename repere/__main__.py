import argparse
from datetime import timedelta
import json
import logging
import os
from pathlib import Path
import secrets
import threading
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
    parser.add_argument('--db')
    parser.add_argument('--mode',choices=['demo','import'])
    commands=parser.add_subparsers(dest='command',required=True)
    demo=commands.add_parser('demo',help='Initialiser une démo synthétique et démarrer en local')
    demo.add_argument('--port',type=int,default=8080)
    commands.add_parser('seed-demo',help='Charger les données synthétiques sans démarrer de serveur')
    imp=commands.add_parser('import',help='Importer une enveloppe JSON autorisée (ou CSV encapsulé)')
    imp.add_argument('file')
    commands.add_parser('init')
    commands.add_parser('serve',help='Serveur de développement local ; production via Gunicorn')
    for name,help_text in [('collect','Importer les résultats de tâches Apify terminées'),('live','Collecter périodiquement et ouvrir le serveur local de données réelles')]:
        command=commands.add_parser(name,help=help_text)
        command.add_argument('--config',default='collectors.local.json')
        command.add_argument('--force',action='store_true',help='Relire un résultat déjà importé, sans rafraîchir ses observations')
        if name=='collect': command.add_argument('--check',action='store_true',help='Valider la configuration sans réseau ni écriture SQLite')
        else:
            command.add_argument('--port',type=int,default=8080)
            command.add_argument('--interval',type=int,default=900,help='Intervalle de lecture Apify en secondes (300 à 86400)')
    alerts=commands.add_parser('alerts');alerts.add_argument('--transport',choices=['simulation','telegram'],default='simulation')
    back=commands.add_parser('backup');back.add_argument('destination')
    prune=commands.add_parser('prune');prune.add_argument('--days',type=int,default=90)
    evaluate=commands.add_parser('evaluate');evaluate.add_argument('--cutoff',required=True);evaluate.add_argument('--as-of',required=True)
    args=parser.parse_args()
    collector_mode=args.command in ('collect','live')
    if collector_mode:
        from .collectors import ApifyClient,collect,load_config
        if args.mode not in (None,'import'): parser.error('Les collecteurs exigent une base en mode import')
        args.mode='import'
        # A .env intended for the demo must never select the synthetic database.
        args.db=args.db or 'data/repere-import.sqlite'
        try:
            configs=load_config(args.config)
            if not configs: raise ValueError('Aucune source activée ; configurer collectors.local.json')
            if args.command=='collect' and args.check:
                print(json.dumps({'configuration':'ok','sources':[c.source for c in configs]},ensure_ascii=False))
                return
            client=ApifyClient()
        except (ValueError,OSError) as exc:
            parser.error(str(exc) if isinstance(exc,ValueError) else 'Fichier de configuration absent ou illisible')
        if args.command=='live' and not 300<=args.interval<=86400: parser.error('Intervalle : 300 à 86400 secondes')
    else:
        args.mode=args.mode or os.environ.get('DATA_MODE','demo')
        args.db=args.db or os.environ.get('DATABASE_PATH','data/repere-demo.sqlite')
    if args.command in ('demo','live') and not 1<=args.port<=65535: parser.error('Port : 1 à 65535')
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
    if args.command=='collect':
        reports=collect(args.db,configs,client,force=args.force)
        print(json.dumps({'collection':reports},ensure_ascii=False))
        if any(r['status']=='error' for r in reports): raise SystemExit(1)
    if args.command in ('demo','serve','live'):
        logging.basicConfig(level=logging.INFO,format='%(message)s')
        if args.command in ('demo','live'):
            token=secrets.token_urlsafe(32)
            config=Config(args.db,args.mode,access_token=token,session_secret=secrets.token_urlsafe(32),origin=f'http://127.0.0.1:{args.port}')
            label='Démo locale' if args.command=='demo' else 'Annonces réelles — serveur local'
            print(f'\n{label} : {config.origin}\nCode d’accès temporaire : {token}\n',flush=True)
        else:
            config=replace(from_env(),db_path=args.db,mode=args.mode)
            if config.environment!='development': parser.error('Utiliser Gunicorn pour staging/production')
        from urllib.parse import urlsplit
        u=urlsplit(config.origin)
        app=Application(config)
        stop=threading.Event()
        worker=None
        if args.command=='live':
            def synchronize():
                while not stop.is_set():
                    try:
                        reports=collect(args.db,configs,client,force=args.force)
                        print(json.dumps({'collection':reports},ensure_ascii=False),flush=True)
                    except Exception:
                        logging.getLogger('repere').error('Collecte interrompue ; vérifier la configuration et la base')
                    if stop.wait(args.interval): break
            worker=threading.Thread(target=synchronize,name='repere-collector',daemon=True)
        try:
            # Bind before starting any network read; an occupied port must not
            # leave a background collector running without its UI.
            with make_server(u.hostname,u.port or 8080,app) as server:
                if worker: worker.start()
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            if worker and worker.is_alive(): worker.join(timeout=1)


if __name__=='__main__': main()
