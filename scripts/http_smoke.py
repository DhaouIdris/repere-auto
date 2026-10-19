"""Real Gunicorn + TCP + authenticated API smoke test, no external services."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from repere.adapters import prepare
from repere.db import initialize,connect,ingest
from repere.demo import payload
from repere.model import utcnow


def main():
    with tempfile.TemporaryDirectory() as folder:
        path=str(Path(folder)/'http.sqlite')
        now=utcnow();initialize(path,'demo');items,rights=prepare(payload(now),'demo',now)
        with connect(path) as db:ingest(db,items,rights,now)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        token='http-test-token-0000000000000000000000'
        env=os.environ|{'DATABASE_PATH':path,'DATA_MODE':'demo','APP_ENV':'development','APP_ORIGIN':origin,'ACCESS_TOKEN':token,'SESSION_SECRET':'http-test-session-111111111111111111111'}
        process=subprocess.Popen([sys.executable,'-m','gunicorn','--bind',f'127.0.0.1:{port}','--workers','1','--threads','2','repere.web:create_app()'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(origin+'/ready',timeout=.5) as r:assert r.status==200
                    break
                except OSError:
                    if process.poll() is not None:raise RuntimeError('Gunicorn failed to boot')
                    time.sleep(.05)
            else:raise RuntimeError('Readiness timeout')
            req=urllib.request.Request(origin+'/api/listings?only_deals=true',headers={'Authorization':'Bearer '+token})
            with urllib.request.urlopen(req,timeout=10) as r:
                data=json.load(r);assert data['total']==6;assert r.headers['X-Frame-Options']=='DENY'
            try:urllib.request.urlopen(origin+'/api/summary',timeout=5)
            except urllib.error.HTTPError as e:assert e.code==401
            else:raise AssertionError('Anonymous access was allowed')
            for path in ['/','/app.js','/style.css','/health']:
                with urllib.request.urlopen(origin+path,timeout=5) as r:assert r.status==200
            print('HTTP smoke PASS: Gunicorn, readiness, authenticated ranking, anonymous denial and static assets')
        finally:
            process.terminate()
            _,stderr=process.communicate(timeout=10)
            if process.returncode not in (0,-15):print(stderr,file=sys.stderr)


if __name__=='__main__':main()
