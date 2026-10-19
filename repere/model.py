from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value=None):
    return (value or utcnow()).isoformat().replace('+00:00', 'Z')


def date(value):
    if not isinstance(value, str):
        raise ValueError('Date ISO avec fuseau requise')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('Date ISO invalide') from None
    if parsed.tzinfo is None:
        raise ValueError('Fuseau de la date requis')
    return parsed.astimezone(timezone.utc)


def norm(value):
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', value or '').lower() if not unicodedata.combining(c))).split())


def text(value, maximum=300):
    if value is None or value == '':
        return None
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Champ texte invalide ou trop long')
    return value.strip() or None


def integer(value, lo, hi, name):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]+', str(value)):
        raise ValueError(f'{name}: entier requis')
    value = int(value)
    if not lo <= value <= hi:
        raise ValueError(f'{name}: hors limites')
    return value


def cents(value):
    if value is None or value == '':
        return None
    try:
        raw = str(value).replace('\u202f', '').replace('\xa0', '').replace(' ', '').replace('€', '').replace(',', '.')
        amount = Decimal(raw)
        if not amount.is_finite() or amount <= 0 or amount > 2_000_000 or amount.as_tuple().exponent < -2:
            raise ValueError('Prix EUR positif, deux décimales maximum')
        return int(amount * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Prix EUR invalide') from None


def enum(value, aliases, name):
    if value is None or value == '':
        return None
    key = norm(text(value))
    if key not in aliases:
        raise ValueError(f'{name}: valeur inconnue')
    return aliases[key]


FUELS = {norm(k): v for v, names in {
    'essence': ['essence', 'petrol', 'gasoline'], 'diesel': ['diesel', 'gazole'],
    'electrique': ['électrique', 'electric', 'BEV'], 'hybride': ['hybride', 'hybrid', 'HEV'],
    'hybride_rechargeable': ['hybride rechargeable', 'plug-in hybrid', 'PHEV'], 'gpl': ['GPL', 'LPG'],
}.items() for k in names + [v]}
GEARS = {norm(k): v for v, names in {'manuelle': ['manuelle', 'manual', 'BVM', 'BVM6'], 'automatique': ['automatique', 'automatic', 'BVA', 'DSG', 'EDC', 'e-CVT']}.items() for k in names + [v]}
SELLERS = {norm(k): v for v, names in {'particulier': ['particulier', 'private'], 'professionnel': ['professionnel', 'professional', 'pro', 'dealer']}.items() for k in names}
CONDITIONS = {norm(k): k for k in ['normal', 'endommage', 'pieces', 'inconnu']}


def safe_url(value, domains=None):
    if not value:
        return None
    value = text(value, 1500)
    try:
        u = urlsplit(value)
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None, 443):
            raise ValueError()
        host=u.hostname.lower()
        if '.' not in host or host.endswith(('.localhost','.local')) or host=='localhost': raise ValueError()
        try: ipaddress.ip_address(host)
        except ValueError: pass
        else: raise ValueError()
        # External URLs are links only; the server never downloads them.
        if domains is not None and u.hostname.lower() not in domains:
            raise ValueError()
    except (ValueError, AttributeError):
        raise ValueError('URL HTTPS non autorisée') from None
    return value


@dataclass(frozen=True)
class Listing:
    source: str
    source_id: str
    brand: str | None
    model: str | None
    generation: str | None = None
    trim: str | None = None
    engine: str | None = None
    year: int | None = None
    month: int | None = None
    mileage_km: int | None = None
    price_cents: int | None = None
    fuel: str | None = None
    gearbox: str | None = None
    power_kw: int | None = None
    fiscal_hp: int | None = None
    critair: int | None = None
    city: str | None = None
    postal_code: str | None = None
    department: str | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    seller: str | None = None
    condition: str | None = None
    defects: str | None = None
    maintenance: str | None = None
    inspection: str | None = None
    accident_claim: str | None = None
    warranty: str | None = None
    description: str | None = None
    url: str | None = None
    published_at: str | None = None
    observed_at: str | None = None
    financing_only: bool = False
    image_urls: tuple = ()
    images_authorized: bool = False
    flags: tuple = ()

    @property
    def id(self):
        return hashlib.sha256(f'{self.source}\0{self.source_id}'.encode()).hexdigest()[:24]

    def to_dict(self):
        return asdict(self)


RAW_FIELDS = {f.name for f in fields(Listing)} - {'source', 'price_cents', 'flags'} | {'price_eur'}


def parse_listing(raw, source, mode, now=None):
    now = now or utcnow()
    if not isinstance(raw, dict) or set(raw) - RAW_FIELDS:
        raise ValueError('Champs inconnus/interdits ; contacts, VIN et plaques ne sont pas acceptés')
    source_id = text(raw.get('source_id'), 120)
    if not source_id:
        raise ValueError('source_id requis')
    result = {k: text(raw.get(k), 4000 if k == 'description' else 300) for k in ['brand','model','generation','trim','engine','city','region','defects','maintenance','inspection','accident_claim','warranty','description']}
    brands = {'vw':'Volkswagen','volkswagen':'Volkswagen','renault':'Renault','peugeot':'Peugeot','toyota':'Toyota','dacia':'Dacia','tesla':'Tesla','citroen':'Citroën','mercedes benz':'Mercedes-Benz','bmw':'BMW'}
    result['brand'] = brands.get(norm(result['brand']), result['brand'])
    for k, lo, hi in [('year',1950,now.year),('month',1,12),('mileage_km',0,2_000_000),('power_kw',1,1500),('fiscal_hp',1,150),('critair',0,5)]:
        result[k] = integer(raw.get(k),lo,hi,k)
    for k, values in [('fuel',FUELS),('gearbox',GEARS),('seller',SELLERS),('condition',CONDITIONS)]:
        result[k] = enum(raw.get(k), values,k)
    flags=[]
    postal = text(raw.get('postal_code'),5)
    if postal and (not re.fullmatch(r'\d{5}',postal) or postal[:2] in ['00','97','98'] or int(postal[:2]) > 95):
        raise ValueError('Code postal métropolitain attendu')
    department = text(raw.get('department'),3)
    if department and not re.fullmatch(r'(0[1-9]|[1-8][0-9]|9[0-5]|2A|2B)', department):
        raise ValueError('Département métropolitain invalide')
    # No invented Corsican department: 20xxx alone does not distinguish 2A / 2B.
    if postal and department and postal[:2] != '20' and postal[:2] != department:
        raise ValueError('Code postal et département incohérents')
    result.update(postal_code=postal, department=department)
    for key, lo, hi in [('latitude',41,52),('longitude',-6,10)]:
        value=raw.get(key)
        if value not in (None,''):
            try: value=float(value)
            except (ValueError,TypeError): raise ValueError('Coordonnées invalides') from None
            if not lo <= value <= hi: raise ValueError('Coordonnées hors métropole')
        else: value=None
        result[key]=value
    if (result['latitude'] is None) != (result['longitude'] is None):
        raise ValueError('Paire latitude/longitude requise')
    for key in ['published_at','observed_at']:
        value=raw.get(key)
        if value:
            d=date(value)
            if d > now + timedelta(minutes=5): raise ValueError('Date dans le futur')
            result[key]=iso(d)
        else: result[key]=None
    result['observed_at'] = result['observed_at'] or iso(now)
    if result['published_at'] and date(result['published_at']) > date(result['observed_at']):
        raise ValueError('Publication postérieure à observation')
    financing=raw.get('financing_only')
    if financing is None or financing=='': financing=False
    if financing in ('true','false'): financing=financing=='true'
    if not isinstance(financing,bool): raise ValueError('financing_only doit être booléen')
    result['financing_only']=financing
    images=raw.get('image_urls')
    if images is None or images=='': images=[]
    if not isinstance(images,list) or len(images)>10: raise ValueError('Dix références d’images maximum')
    allowed=raw.get('images_authorized')
    if allowed is None or allowed=='': allowed=False
    if allowed in ('true','false'): allowed=allowed=='true'
    if not isinstance(allowed,bool): raise ValueError('images_authorized doit être booléen')
    if images and (not allowed or mode=='demo'): raise ValueError('Droits explicites sur les images requis ; aucune image externe en démo')
    result['image_urls']=tuple(safe_url(u) for u in images)
    result['images_authorized']=allowed
    danger=' '.join(result.get(k) or '' for k in ['description','defects'])
    # Conservative flags, not an inference that a vehicle is mechanically sound.
    if re.search(r'\b(accidente|non roulant|pour pieces|moteur hs|epave)\b',norm(danger)): flags.append('dommages_declares')
    if re.search(r'\b(sous condition de financement|par mois|mensualite|loyer mensuel)\b',norm(danger)): flags.append('prix_financement_possible')
    for key in ['description','defects','maintenance','inspection','accident_claim','warranty']:
        value=result[key]
        if value:
            cleaned=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\w)(?:\+33|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)|\b[A-HJ-NPR-Z0-9]{17}\b|\b[A-Z]{2}-\d{3}-[A-Z]{2}\b','[information retirée]',value)
            if cleaned!=value: flags.append('texte_expurge')
            result[key]=cleaned
    domains={'leboncoin':{'www.leboncoin.fr','leboncoin.fr'},'lacentrale':{'www.lacentrale.fr','lacentrale.fr'},'autoscout24':{'www.autoscout24.fr','autoscout24.fr','www.autoscout24.com','autoscout24.com'},'paruvendu':{'www.paruvendu.fr'}}
    result['url']=safe_url(raw.get('url'),domains.get(source))
    if mode=='demo' and result['url']: raise ValueError('La démo ne contient pas de vrais liens')
    result['price_cents']=cents(raw.get('price_eur'))
    if result['price_cents'] is None: flags.append('prix_manquant')
    if not result['condition'] or result['condition']=='inconnu': flags.append('etat_non_renseigne')
    return Listing(source=source,source_id=source_id,flags=tuple(sorted(set(flags))),**result)


def fingerprint(listing):
    d=listing.to_dict()
    # A probable duplicate requires an identical substantial redacted description,
    # exact mileage and location plus the whole mechanical signature. Conservative.
    keys=['brand','model','generation','trim','engine','fuel','gearbox','seller','year','month','mileage_km','postal_code']
    if len(norm(d['description'])) < 30 or any(d[k] is None for k in keys):
        return listing.id, 'identite_source'
    # Use the same text normalization as valuation. Price and observation date
    # are deliberately absent: a price change does not create another vehicle.
    parts=[norm(str(d[k])) for k in keys]+[norm(d['description'])]
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:24], 'doublon_probable_normalise'
