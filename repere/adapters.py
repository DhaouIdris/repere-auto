"""Only original synthetic data or user-authorized local exports; no scrapers."""
import csv
import io
import json
from abc import ABC, abstractmethod
from .model import parse_listing,date,utcnow
from datetime import timedelta

SOURCES = ('leboncoin','lacentrale','autoscout24','paruvendu','export')


class Adapter(ABC):
    @abstractmethod
    def read(self, body): ...


class JsonAdapter(Adapter):
    def read(self, body):
        try:
            def unique(pairs):
                out={}
                for k,v in pairs:
                    if k in out: raise ValueError('Clé JSON dupliquée')
                    out[k]=v
                return out
            return json.loads(body, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nombre non fini')))
        except (json.JSONDecodeError,UnicodeDecodeError):
            raise ValueError('JSON invalide') from None


class CsvAdapter(Adapter):
    def read(self, body):
        try:
            reader=csv.DictReader(io.StringIO(body.decode('utf-8-sig')), delimiter=';')
            if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames): raise ValueError('En-tête CSV invalide')
            return list(reader)
        except (UnicodeDecodeError,csv.Error): raise ValueError('CSV UTF-8 séparateur ; attendu') from None


def prepare(payload, mode, now=None):
    if not isinstance(payload,dict) or set(payload)-{'schema_version','source','rights_reference','authorized','format','listings','csv'}:
        raise ValueError('Enveloppe import invalide')
    if type(payload.get('schema_version')) is not int or payload['schema_version']!=1:
        raise ValueError('schema_version 1 requis : schéma non reconnu')
    source=payload.get('source')
    if source not in SOURCES + ('demo',): raise ValueError('Source inconnue')
    if (source=='demo')!=(mode=='demo'): raise ValueError('Données démo et réelles séparées : choisir la base et le mode appropriés')
    rights=payload.get('rights_reference')
    if payload.get('authorized') is not True or not isinstance(rights,str) or not 8<=len(rights)<=300:
        raise ValueError('Autorisation explicite et référence de provenance requises')
    rows=payload.get('listings')
    if payload.get('format')=='csv':
        if not isinstance(payload.get('csv'),str): raise ValueError('Contenu CSV requis')
        rows=CsvAdapter().read(payload['csv'].encode())
    elif payload.get('format','json')!='json': raise ValueError('Format non reconnu')
    if not isinstance(rows,list) or not 1<=len(rows)<=500: raise ValueError('Un lot doit contenir entre 1 et 500 annonces')
    result=[]
    ids=set()
    for index,raw in enumerate(rows,1):
        try: item=parse_listing(raw,source,mode,now)
        except ValueError as exc: raise ValueError(f'Ligne {index}: {exc}') from None
        if item.id in ids: raise ValueError(f'Ligne {index}: identifiant source dupliqué dans le lot')
        ids.add(item.id)
        result.append(item)
    return result,rights


def source_registry(mode, db):
    statuses={r['source']:dict(r) for r in db.execute('SELECT * FROM source_status')}
    for status in statuses.values():
        status['freshness']='jamais_importe' if not status['last_success'] else ('perime' if date(status['last_success'])<utcnow()-timedelta(days=14) else 'recent')
        status['health']='erreur_import' if status['last_error'] else 'ok'
    return [{'source':name,'live_status':'blocked_permission','message':'Aucun accès automatisé autorisé configuré ; import de données autorisées uniquement.', 'import':statuses.get(name)} for name in SOURCES[:-1]] + [{'source':'demo' if mode=='demo' else 'export','live_status':'synthetic' if mode=='demo' else 'local_import','message':'Données entièrement synthétiques' if mode=='demo' else 'Fichiers locaux avec provenance déclarée','import':statuses.get('demo' if mode=='demo' else 'export')}]
