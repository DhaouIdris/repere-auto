from dataclasses import dataclass
from pathlib import Path
import os
from .valuation import Rules


@dataclass(frozen=True)
class Config:
    db_path: str
    mode: str = 'demo'
    environment: str = 'development'
    access_token: str = ''
    session_secret: str = ''
    origin: str = 'http://127.0.0.1:8080'
    rules: Rules = Rules()
    cooldown_hours: int = 24
    price_drop_pct: float = 3

    def __post_init__(self):
        if self.mode not in ('demo','import') or self.environment not in ('development','staging','production'): raise ValueError('Environnement invalide')
        if len(self.access_token)<32 or len(self.session_secret)<32: raise ValueError('Deux secrets distincts de 32 caractères minimum requis')
        if self.access_token==self.session_secret: raise ValueError('Secrets de connexion et session distincts requis')
        if not 0<=self.cooldown_hours<=168 or not 0<self.price_drop_pct<=80: raise ValueError('Paramètres de notification invalides')
        from urllib.parse import urlsplit
        u=urlsplit(self.origin)
        if u.path not in ('','/') or u.query or u.fragment or u.username or not u.hostname: raise ValueError('APP_ORIGIN invalide')
        if self.environment!='development' and u.scheme!='https': raise ValueError('HTTPS obligatoire en staging/production')
        if self.environment=='development' and u.hostname not in ('127.0.0.1','localhost','::1'): raise ValueError('Le développement écoute seulement une origine locale')


def from_env():
    return Config(db_path=os.environ.get('DATABASE_PATH','data/repere-demo.sqlite'),mode=os.environ.get('DATA_MODE','demo'),
        environment=os.environ.get('APP_ENV','development'),access_token=os.environ.get('ACCESS_TOKEN',''),
        session_secret=os.environ.get('SESSION_SECRET',''),origin=os.environ.get('APP_ORIGIN','http://127.0.0.1:8080').rstrip('/'),
        rules=Rules(min_comps=int(os.environ.get('MIN_COMPARABLES','6')),min_discount=float(os.environ.get('MIN_DISCOUNT_PCT','15')),
                    max_iqr_ratio=float(os.environ.get('MAX_IQR_RATIO','0.25'))),
        cooldown_hours=int(os.environ.get('ALERT_COOLDOWN_HOURS','24')),price_drop_pct=float(os.environ.get('PRICE_DROP_PCT','3')))
