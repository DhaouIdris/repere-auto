"""Exercise the actual image, non-root, read-only, with ephemeral SQLite data."""
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request


def docker(*args):
    return subprocess.check_output(['docker',*args],text=True,timeout=30).strip()


def main(image):
    name='repere-check-'+secrets.token_hex(6)
    token=secrets.token_urlsafe(32)
    args=['run','--detach','--rm','--name',name,'--read-only','--cap-drop=ALL',
          '--security-opt=no-new-privileges:true','--tmpfs','/tmp:size=64m',
          '--tmpfs','/data:uid=10001,gid=10001,mode=0700','-p','127.0.0.1::8080']
    env={'DATABASE_PATH':'/data/check.sqlite','DATA_MODE':'demo','APP_ENV':'development',
         'APP_ORIGIN':'http://127.0.0.1:8080','ACCESS_TOKEN':token,'SESSION_SECRET':secrets.token_urlsafe(32)}
    for key,value in env.items():args+=['-e',key+'='+value]
    try:
        docker(*args,image)
        port=int(docker('port',name,'8080/tcp').splitlines()[0].rsplit(':',1)[1])
        origin='http://127.0.0.1:'+str(port)
        for _ in range(100):
            try:
                with urllib.request.urlopen(origin+'/ready',timeout=1) as response:
                    if response.status==200:break
            except OSError:time.sleep(.2)
        else:raise RuntimeError('Container readiness timeout')
        assert docker('exec',name,'id','-u')=='10001'
        docker('exec',name,'python','-m','repere','--db','/data/check.sqlite','seed-demo')
        request=urllib.request.Request(origin+'/api/listings?only_deals=true',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=15) as response:
            assert json.load(response)['total']==6
        try:urllib.request.urlopen(origin+'/api/summary',timeout=5)
        except urllib.error.HTTPError as error:assert error.code==401
        else:raise AssertionError('Anonymous access allowed')
        print('Container smoke PASS: actual image, uid 10001, read-only root, SQLite migration, six opportunities, anonymous denial')
    except Exception:
        subprocess.run(['docker','logs',name],check=False,timeout=10)
        raise
    finally:
        subprocess.run(['docker','rm','-f',name],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)


if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'repere-auto:check')
