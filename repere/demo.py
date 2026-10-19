"""Entirely synthetic French examples, regenerated deterministically for a given date."""
from datetime import timedelta
from .model import iso, utcnow


def payload(now=None):
    now=now or utcnow()
    templates=[
        ('Renault','Clio','V','Evolution','TCe 90','essence','manuelle',13500),
        ('Peugeot','208','II','Active','PureTech 100','essence','manuelle',14800),
        ('Dacia','Sandero','III','Stepway','TCe 90','essence','manuelle',12900),
        ('Toyota','Yaris','IV','Dynamic','Hybrid 116','hybride','automatique',17900),
        ('Volkswagen','Golf','VIII','Life','TDI 115','diesel','manuelle',21500),
        ('Tesla','Model 3','2021','Propulsion','Standard Range Plus','electrique','automatique',24900),
    ]
    rows=[]
    for g,(brand,model,generation,trim,engine,fuel,gearbox,base) in enumerate(templates):
        for i in range(15):
            price=round(base*(1+((i%7)-3)*0.014))
            if i==0: price=round(base*0.79)
            row=dict(source_id=f'synthetique-{g}-{i}',brand=brand,model=model,generation=generation,trim=trim,engine=engine,
                fuel=fuel,gearbox=gearbox,year=2022,month=1+i%12,mileage_km=40000+i*670,price_eur=price,
                seller='professionnel',condition='normal',city='Paris' if i%2==0 else 'Créteil',postal_code='75013' if i%2==0 else '94000',
                department='75' if i%2==0 else '94',region='Île-de-France',latitude=48.82 if i%2==0 else 48.79,longitude=2.36 if i%2==0 else 2.45,
                published_at=iso(now-timedelta(days=1+i%5)),observed_at=iso(now-timedelta(hours=i%3)),
                description=f'Exemple synthétique numéro {g}-{i}. Véhicule inventé pour vérifier les comparaisons et le fonctionnement du service.',
                maintenance='Entretien déclaré dans cet exemple fictif',inspection='Information synthétique à vérifier',warranty='12 mois déclarés (exemple)',
                power_kw=66 if g==0 else None,critair=None)
            rows.append(row)
        duplicate=dict(rows[-15]);duplicate['source_id']+='-republication';rows.append(duplicate)
    damaged=dict(rows[0]);damaged.update(source_id='synthetique-dommage',description='Autre véhicule fictif, exemple de dommages déclarés à exclure des opportunités.',price_eur=3900,condition='endommage',defects='Moteur HS, véhicule non roulant')
    monthly=dict(rows[1]);monthly.update(source_id='synthetique-financement',description='Autre véhicule fictif, exemple de prix sous condition de financement à exclure.',price_eur=1200,financing_only=True)
    incomplete=dict(rows[2]);incomplete.update(source_id='synthetique-incomplet',price_eur=None,engine=None)
    stale=dict(rows[3]);stale.update(source_id='synthetique-perime',description='Autre véhicule fictif, exemple de données périmées à exclure des opportunités.',price_eur=9900,observed_at=iso(now-timedelta(days=40)),published_at=iso(now-timedelta(days=45)))
    rows.extend([damaged,monthly,incomplete,stale])
    return {'schema_version':1,'source':'demo','authorized':True,'rights_reference':'SYNTHETIQUE-ORIGINAL-REPERE-AUTO','listings':rows}
