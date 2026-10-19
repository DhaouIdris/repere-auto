"""Transparent leave-vehicle-out asking-price baseline. No transaction-price claim."""
from dataclasses import dataclass
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt, isfinite
from statistics import median, quantiles
from collections import Counter
from functools import lru_cache
from .model import date, norm, utcnow


@dataclass(frozen=True)
class Rules:
    min_comps: int = 6
    min_discount: float = 15.0
    max_iqr_ratio: float = 0.25
    max_observation_days: int = 14
    max_listing_days: int = 30
    year_gap: int = 1
    km_gap: int = 20000

    def __post_init__(self):
        if not 3<=self.min_comps<=100 or not 0<=self.min_discount<=80 or not 0.01<=self.max_iqr_ratio<=1:
            raise ValueError('Règles de valorisation invalides')
        if not 1<=self.max_observation_days<=90 or not 1<=self.max_listing_days<=365 or not 0<=self.year_gap<=2 or not 1000<=self.km_gap<=100000:
            raise ValueError('Fenêtres de valorisation invalides')


SIGNATURE=('brand','model','generation','trim','engine','fuel','gearbox','seller','region')
ESSENTIAL=SIGNATURE+('year','mileage_km','price_cents')


@lru_cache(maxsize=8192)
def signature_values(values):
    return tuple(norm(str(v or '')) for v in values)


def signature(row):
    return signature_values(tuple(row.get(k) for k in SIGNATURE))


def fresh(row,now,rules):
    return row.get('observed_at') and now-timedelta(days=rules.max_observation_days)<=date(row['observed_at'])<=now


def risks(row):
    found=[]
    if row.get('financing_only') or 'prix_financement_possible' in row.get('flags',[]): found.append('Prix lié ou possiblement lié à un financement')
    if row.get('condition') in ('endommage','pieces') or 'dommages_declares' in row.get('flags',[]): found.append('Dommages déclarés ou vente pour pièces')
    if row.get('condition')!='normal': found.append('État non renseigné ou incompatible')
    return found


def estimate(candidate,pool,rules=None,now=None,include_comparables=True):
    rules,now=rules or Rules(),now or utcnow()
    missing=[k for k in ESSENTIAL if candidate.get(k) is None or candidate.get(k)=='']
    out={'market_price_cents':None,'saving_cents':None,'discount_pct':None,'effective_comparables':0,'comparables':[],
         'q25_cents':None,'q75_cents':None,'iqr_ratio':None,'confidence':'insuffisante','opportunity':False,
         'reasons':[],'missing_fields':missing,'method':'Médiane des prix demandés, candidat et doublons exclus',
         'interval_label':'Quartiles observés ; pas un intervalle de confiance','valuation_at':now.isoformat(),
         'sensitivity_discount_range':None}
    if missing:
        out['reasons']=['Comparabilité incomplète : '+', '.join(missing)]
        return out
    # Reject garbage placeholder prices for both candidates and peers.
    if candidate['price_cents']<100000:
        out['reasons']=['Prix inférieur au seuil de plausibilité de 1 000 €']
        return out
    groups={}
    candidate_signature=signature(candidate)
    for peer in pool:
        if peer['group_id']==candidate['group_id'] or peer.get('id')==candidate.get('id'): continue
        if any(peer.get(k) is None or peer.get(k)=='' for k in ESSENTIAL): continue
        if signature(peer)!=candidate_signature: continue
        if abs(peer['year']-candidate['year'])>rules.year_gap or abs(peer['mileage_km']-candidate['mileage_km'])>rules.km_gap: continue
        if not fresh(peer,now,rules) or risks(peer) or peer['price_cents']<100000: continue
        group=peer['group_id']
        # Most recent observation per probable vehicle, stable tie-break; never cheapest selection.
        if group not in groups or (peer['observed_at'],peer['id'])>(groups[group]['observed_at'],groups[group]['id']): groups[group]=peer
    comparable=list(groups.values())
    out['effective_comparables']=len(comparable)
    if include_comparables:
        out['comparables']=[{'id':p['id'],'group_id':p['group_id'],'price_cents':p['price_cents'],'year':p['year'],'mileage_km':p['mileage_km'],'source':p['source'],'observed_at':p['observed_at']} for p in sorted(comparable,key=lambda r:r['price_cents'])]
    if len(comparable)<rules.min_comps:
        out['reasons']=[f'Références insuffisantes : {len(comparable)} / {rules.min_comps} requises']
        return out
    prices=[p['price_cents'] for p in comparable]
    base=round(median(prices))
    q25,_,q75=quantiles(prices,n=4,method='inclusive')
    spread=(q75-q25)/base
    pct=(base-candidate['price_cents'])/base*100
    reasons=risks(candidate)
    if not fresh(candidate,now,rules): reasons.append('Observation périmée ou dans le futur')
    if not candidate.get('published_at'): reasons.append('Date de publication inconnue')
    elif not now-timedelta(days=rules.max_listing_days)<=date(candidate['published_at'])<=now: reasons.append('Annonce trop ancienne ou date future')
    if spread>rules.max_iqr_ratio: reasons.append('Dispersion trop élevée des références')
    if pct>60: reasons.append('Écart extrême : prix ou informations à vérifier')
    if pct<rules.min_discount: reasons.append(f'Remise inférieure à {rules.min_discount:g} %')
    reliable=spread<=rules.max_iqr_ratio
    out.update(market_price_cents=base,saving_cents=base-candidate['price_cents'],discount_pct=round(pct,2),
        q25_cents=round(q25),q75_cents=round(q75),iqr_ratio=round(spread,4),
        confidence=('élevée' if len(comparable)>=12 and spread<=0.12 else 'modérée') if reliable else 'faible',
        opportunity=not reasons,reasons=reasons or ['Prix demandé inhabituellement bas face à des annonces comparables ; vérifications du véhicule nécessaires'])
    # Sensitivity to deleting any one reference; not a calibrated prediction interval.
    ordered=sorted(prices)
    # Deleting an interior observation cannot exceed the medians obtained by
    # deleting the lowest or highest value. Exact range, two medians only.
    bases=[median(ordered[1:]),median(ordered[:-1])]
    discounts=[100*(b-candidate['price_cents'])/b for b in bases]
    out['sensitivity_discount_range']=[round(min(discounts),2),round(max(discounts),2)]
    return out


FILTER_TEXT={'brand','model','fuel','gearbox','seller','region'}
FILTER_NUM={'max_price_eur':(0,2_000_000),'max_mileage':(0,2_000_000),'min_year':(1950,2100),
            'min_discount':(0,80),'radius_km':(1,2000),'latitude':(41,52),'longitude':(-6,10)}


def validate_filters(raw):
    if not isinstance(raw,dict) or set(raw)-(FILTER_TEXT|set(FILTER_NUM)|{'sort','only_deals'}): raise ValueError('Filtre inconnu')
    out={}
    for key,value in raw.items():
        if value in (None,''): continue
        if key in FILTER_TEXT:
            if not isinstance(value,str) or len(value)>100: raise ValueError('Filtre texte invalide')
            out[key]=value.strip()
        elif key in FILTER_NUM:
            if isinstance(value,bool): raise ValueError('Filtre numérique invalide')
            try: value=float(value)
            except (ValueError,TypeError): raise ValueError('Filtre numérique invalide') from None
            lo,hi=FILTER_NUM[key]
            if not isfinite(value) or not lo<=value<=hi: raise ValueError(f'{key}: hors limites')
            out[key]=value
        elif key=='sort':
            if value not in ['discount','saving','confidence','freshness','distance','price']: raise ValueError('Tri inconnu')
            out[key]=value
        elif key=='only_deals':
            if value not in (True,False,'true','false'): raise ValueError('Booléen attendu')
            out[key]=value in (True,'true')
    coords=('latitude' in out,'longitude' in out)
    if any(coords) and not all(coords): raise ValueError('Origine géographique incomplète')
    if ('radius_km' in out or out.get('sort')=='distance') and not all(coords): raise ValueError('Latitude et longitude requises pour le rayon ou la distance')
    return out


def distance(a,b,c,d):
    a,b,c,d=map(radians,[a,b,c,d])
    return 6371*2*asin(min(1,sqrt(sin((c-a)/2)**2+cos(a)*cos(c)*sin((d-b)/2)**2)))


def match(row,f):
    if any(norm(str(row.get(k) or ''))!=norm(str(f[k])) for k in FILTER_TEXT if k in f): return False
    for key,column,scale,operator in [('max_price_eur','price_cents',100,'max'),('max_mileage','mileage_km',1,'max'),('min_year','year',1,'min')]:
        if key in f and (row.get(column) is None or (row[column]>f[key]*scale if operator=='max' else row[column]<f[key])): return False
    if 'radius_km' in f and (row.get('distance_km') is None or row['distance_km']>f['radius_km']): return False
    if f.get('only_deals') and not row['valuation']['opportunity']: return False
    if 'min_discount' in f and (row['valuation']['discount_pct'] is None or row['valuation']['discount_pct']<f['min_discount']): return False
    return True


def rank(pool,filters=None,rules=None,now=None,*,group_id=None):
    filters=validate_filters(filters or {})
    groups={}
    counts=Counter(p['group_id'] for p in pool)
    index={}
    for row in pool:
        index.setdefault(signature(row),[]).append(row)
        key=row['group_id']
        if key not in groups or (row['observed_at'],row['id'])>(groups[key]['observed_at'],groups[key]['id']): groups[key]=row
    out=[]
    for row in groups.values():
        if group_id is not None and row['group_id']!=group_id: continue
        # Cheap characteristics filters before valuation; full pool remains the reference.
        if any(norm(str(row.get(k) or ''))!=norm(str(filters[k])) for k in FILTER_TEXT if k in filters): continue
        item=dict(row)
        item['valuation']=estimate(row,index.get(signature(row),[]),rules,now,include_comparables=False)
        item['duplicate_count']=counts[row['group_id']]-1
        item['missing_fields']=item['valuation']['missing_fields']
        item['completeness_pct']=round(100*sum(row.get(k) is not None for k in ESSENTIAL)/len(ESSENTIAL))
        item['distance_km']=round(distance(filters['latitude'],filters['longitude'],row['latitude'],row['longitude']),1) if 'latitude' in filters and row.get('latitude') is not None else None
        if match(item,filters): out.append(item)
    kind=filters.get('sort','discount')
    def key(r):
        v=r['valuation']
        value={'discount':v['discount_pct'],'saving':v['saving_cents'],'confidence':{'élevée':3,'modérée':2,'faible':1}.get(v['confidence'],0),
               'freshness':date(r['observed_at']).timestamp(),'distance':-r['distance_km'] if r['distance_km'] is not None else None,
               'price':-r['price_cents'] if r['price_cents'] is not None else None}[kind]
        return (value is not None,value if value is not None else 0,r['id'])
    return sorted(out,key=key,reverse=True)
