"""Temporal holdout of observed ASKING prices, with disjoint probable vehicles."""
from math import sqrt
from statistics import median
from .model import date,iso
from .valuation import estimate,Rules,risks


def evaluate(rows,cutoff,as_of,rules=None):
    cutoff,as_of=date(cutoff),date(as_of)
    if cutoff>=as_of: raise ValueError('Le cutoff doit précéder la fin du holdout')
    rules=rules or Rules()
    test=[r for r in rows if cutoff<date(r['observed_at'])<=as_of]
    test_groups={r['group_id'] for r in test}
    train=[r for r in rows if date(r['observed_at'])<=cutoff and r['group_id'] not in test_groups]
    # One evaluation observation per vehicle; no duplicate weighting.
    unique={}
    for r in sorted(test,key=lambda p:(p['observed_at'],p['id'])): unique.setdefault(r['group_id'],r)
    results=[];abstained=0
    for target in unique.values():
        if risks(target):
            abstained+=1;continue
        val=estimate(target,train,rules,date(target['observed_at']))
        if val['market_price_cents'] is None or target['price_cents'] is None:
            abstained+=1;continue
        error=(val['market_price_cents']-target['price_cents'])/100
        results.append({'error':error,'absolute_error':abs(error),'price_eur':target['price_cents']/100,
            'inside_observed_iqr':val['q25_cents']<=target['price_cents']<=val['q75_cents']})
    def metrics(values):
        if not values:return {'n':0,'mae_eur':None,'rmse_eur':None,'median_ae_eur':None,'observed_iqr_coverage':None}
        n=len(values)
        return {'n':n,'mae_eur':round(sum(r['absolute_error'] for r in values)/n,2),
                'rmse_eur':round(sqrt(sum(r['error']**2 for r in values)/n),2),
                'median_ae_eur':round(median(r['absolute_error'] for r in values),2),
                'observed_iqr_coverage':sum(r['inside_observed_iqr'] for r in values)/n}
    return {'cutoff':iso(cutoff),'holdout_end':iso(as_of),'training_vehicles':len({r['group_id'] for r in train}),
        'holdout_vehicles':len(unique),'abstained':abstained,'metrics':metrics(results),
        'segments':{name:metrics([r for r in results if low<=r['price_eur']<high]) for name,low,high in [('moins_10k',0,10000),('10k_20k',10000,20000),('20k_40k',20000,40000),('40k_plus',40000,float('inf'))]},
        'synthetic':all(r['source']=='demo' for r in rows),
        'warning':'Prix demandés uniquement. La couverture IQR est descriptive, sans garantie ni calibration. Les résultats synthétiques ne mesurent pas la précision sur le marché réel.'}
