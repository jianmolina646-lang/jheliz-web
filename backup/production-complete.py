#!/usr/bin/env python3
"""Host-owned complete backups; never restores into a production database."""
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tarfile
import tempfile

STATE = Path('/var/lib/jheliz-backup-v2')
ROOT = Path('/opt/jheliz-deploy')
IDENTITY = '/root/.config/production-backups/age/identity.txt'
MEGA = 'jheliz-backup-1'
PREFIX = 'jheliztv.xyz/complete-v2'
REMOTE = '/JhelizControlBackups/CompleteV2'

def run(*args, **kw):
    kw.setdefault('timeout', 600)
    return sp.run(args, check=True, stdout=sp.PIPE, stderr=sp.PIPE, **kw).stdout

def notify(message):
    # The existing server notification channel is used only for backup health.
    sp.run(['bash', '-c', '. /usr/local/lib/production-backup-notify.sh; backup_notify "$1"', 'backup', message], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

def remote_config():
    raw = run('bash', '-c', 'set -a; . /root/.config/mail-control-backups/r2.env; env -0')
    env = dict(item.decode().split('=', 1) for item in raw.split(b'\0') if b'=' in item)
    for key in ('R2_ENDPOINT', 'R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY'):
        if not env.get(key):
            raise RuntimeError('Missing remote configuration: ' + key)
    os.environ.update(RCLONE_CONFIG='/dev/null', RCLONE_CONFIG_R2_TYPE='s3', RCLONE_CONFIG_R2_PROVIDER='Cloudflare', RCLONE_CONFIG_R2_ENDPOINT=env['R2_ENDPOINT'], RCLONE_CONFIG_R2_ACCESS_KEY_ID=env['R2_ACCESS_KEY_ID'], RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=env['R2_SECRET_ACCESS_KEY'])
    return 'r2:' + env['R2_BUCKET'] + '/' + PREFIX

def digest(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def inspect(name):
    return json.loads(run('docker', 'inspect', name))[0]

def mega_mkdir(path):
    try:
        run('docker','exec',MEGA,'mega-mkdir','-p',path)
    except sp.CalledProcessError:
        run('docker','exec',MEGA,'mega-ls',path)

def retention(remote, archive):
    """Only manage CompleteV2 objects; legacy and other projects stay intact."""
    today = dt.datetime.now(dt.timezone.utc)
    inventory_path = STATE / 'inventory.json'
    inventory = json.loads(inventory_path.read_text()) if inventory_path.exists() else {}
    tiers = [('daily', archive.name, 14)]
    if today.weekday() == 6:
        tiers.append(('weekly', 'jheliz-complete-' + today.strftime('%G-W%V') + '.tar.gz.age', 4))
    if today.day == 1:
        tiers.append(('monthly', 'jheliz-complete-' + today.strftime('%Y%m') + '.tar.gz.age', 6))
    for tier, name, keep in tiers:
        if tier != 'daily' and name not in inventory.get(tier, []):
            run('rclone','copyto',str(archive),remote+'/'+tier+'/'+name,'--s3-no-check-bucket','--immutable')
            mega_mkdir(REMOTE+'/'+tier)
            # Skip existing immutable period copies to avoid MEGA versions.
            existing = run('docker','exec',MEGA,'mega-ls',REMOTE+'/'+tier).decode().splitlines()
            if name not in existing:
                run('docker','exec',MEGA,'mega-put','/backups/'+archive.name,REMOTE+'/'+tier+'/'+name)
        names = list(set(inventory.get(tier, []) + [name]))
        valid = sorted((n for n in names if re.fullmatch(r'jheliz-complete-[0-9W-]+\.tar\.gz\.age', n)), reverse=True)
        # Move expired objects to a recoverable archive tier on R2.
        for old in valid[keep:]:
            run('rclone','moveto',remote+'/'+tier+'/'+old,remote+'/expired/'+tier+'/'+old,'--s3-no-check-bucket')
            run('docker','exec',MEGA,'mega-rm',REMOTE+'/'+tier+'/'+old)
            inventory.setdefault('_expired', []).append({'key': tier+'/'+old, 'timestamp': today.timestamp()})
            print('RETENTION_MEGA_REMOVED_R2_ARCHIVED ' + tier + '/' + old)
        inventory[tier] = valid[:keep]
    pending = []
    for item in inventory.get('_expired', []):
        if today.timestamp() - item['timestamp'] > 30 * 86400:
            if not re.fullmatch(r'(daily|weekly|monthly)/jheliz-complete-[0-9W-]+\.tar\.gz\.age', item['key']):
                raise RuntimeError('Invalid retention inventory')
            run('rclone','deletefile',remote+'/expired/'+item['key'],'--s3-no-check-bucket')
        else:
            pending.append(item)
    inventory['_expired'] = pending
    (STATE / 'inventory.tmp').write_text(json.dumps(inventory))
    (STATE / 'inventory.tmp').replace(inventory_path)
    for old in sorted(STATE.glob('jheliz-complete-*.tar.gz.age'), reverse=True)[3:]:
        old.unlink()

def capacity():
    info = run('docker','exec',MEGA,'mega-df').decode()
    match = re.search(r'USED STORAGE:.*?([0-9.]+)%', info)
    if not match:
        raise RuntimeError('Cannot read MEGA capacity')
    percent = float(match[1])
    print('MEGA_USED_PERCENT=' + str(percent))
    flag = STATE / 'capacity-warning-date'
    day = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')
    if percent >= 85 and (not flag.exists() or flag.read_text() != day):
        notify('JhelizTV: MEGA al ' + str(percent) + '%. Revisar capacidad; R2 mantiene copia independiente.')
        flag.write_text(day)

def verify(archive, work, label):
    plain = work / (label + '.tar.gz')
    run('age', '-d', '-i', IDENTITY, '-o', str(plain), str(archive))
    target = work / label
    target.mkdir()
    with tarfile.open(plain) as tar:
        tar.extractall(target, filter='data')
    manifest = json.loads((target / 'manifest.json').read_text())
    for path, checksum in manifest['sha256'].items():
        if digest(target / path) != checksum:
            raise RuntimeError('Checksum mismatch')
    name = 'jheliz-restore-v2-' + label + '-' + str(os.getpid())
    try:
        run('docker', 'run', '-d', '--name', name, '--network', 'none', '--memory', '512m', '--tmpfs', '/var/lib/postgresql/data', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:16-alpine')
        # initdb briefly starts a socket-only server; wait for the final TCP
        # listener so restore cannot race that temporary server's shutdown.
        run('docker', 'exec', name, 'sh', '-c', 'for i in $(seq 1 60); do pg_isready -h 127.0.0.1 -U postgres >/dev/null && exit 0; sleep 1; done; exit 1')
        with (target / 'database.dump').open('rb') as f:
            run('docker', 'exec', '-i', name, 'pg_restore', '-U', 'postgres', '-d', 'postgres', '--exit-on-error', '--no-owner', '--no-acl', stdin=f)
        # Exact counts captured from the same pg_dump snapshot.
        for table, expected in manifest['counts'].items():
            sql = 'SELECT count(*) FROM "' + table.replace('"', '""') + '"'
            actual = int(run('docker', 'exec', name, 'psql', '-U', 'postgres', '-d', 'postgres', '-Atc', sql))
            if actual != expected:
                raise RuntimeError('Restore count mismatch: ' + table)
    finally:
        sp.run(['docker', 'rm', '-f', name], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    return len(manifest['counts'])

def main():
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (STATE / 'lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if '--health' in sys.argv:
        status = json.loads((STATE / 'success.json').read_text())
        age = dt.datetime.now(dt.timezone.utc).timestamp() - status['timestamp']
        if age > 30 * 3600:
            raise RuntimeError('No verified backup in 30 hours')
        capacity()
        print('HEALTH_OK age_hours=' + str(round(age/3600, 1)))
        return
    remote = remote_config()
    web = inspect('jheliz-web-1')
    db = inspect('jheliz-db-1')
    env = dict(v.split('=', 1) for v in db['Config']['Env'] if '=' in v)
    web_env = dict(v.split('=', 1) for v in web['Config']['Env'] if '=' in v)
    from urllib.parse import urlsplit
    url = urlsplit(web_env.get('DATABASE_URL', ''))
    if url.hostname != 'db' or not url.path.lstrip('/'):
        raise RuntimeError('Web/database target mismatch')
    # A cluster can contain multiple databases; follow the running web URL.
    env['POSTGRES_DB'] = url.path.lstrip('/')
    mounts = {m['Destination']: Path(m['Source']).resolve() for m in web['Mounts']}
    for folder in ('media', 'private_media'):
        if mounts.get('/app/' + folder) != (ROOT / folder).resolve():
            raise RuntimeError('Deployment mount drift: ' + folder)
    for item in ('.env', 'secrets', 'media', 'private_media'):
        if not (ROOT / item).exists():
            raise RuntimeError('Missing required source: ' + item)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')
    name = 'jheliz-complete-' + stamp + '.tar.gz.age'
    with tempfile.TemporaryDirectory(prefix='jheliz-backup-v2-') as tmp:
        work = Path(tmp)
        payload = work / 'payload'
        payload.mkdir()
        # Hold an exported snapshot for the dump and verification counts.
        sqlproc = sp.Popen(['docker','exec','-i','jheliz-db-1','psql','-U',env['POSTGRES_USER'],'-d',env['POSTGRES_DB'],'-At','-v','ON_ERROR_STOP=1'], stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        try:
            sqlproc.stdin.write('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n'); sqlproc.stdin.flush()
            if sqlproc.stdout.readline().strip() != 'BEGIN':
                raise RuntimeError('Snapshot transaction failed')
            snapshot = sqlproc.stdout.readline().strip()
            with (payload / 'database.dump').open('wb') as f:
                sp.run(['docker','exec','jheliz-db-1','pg_dump','-U',env['POSTGRES_USER'],'-d',env['POSTGRES_DB'],'-Fc','--no-owner','--no-acl','--snapshot='+snapshot], stdout=f, stderr=sp.PIPE, check=True)
            sqlproc.stdin.write("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;\nSELECT '__END__';\n"); sqlproc.stdin.flush()
            tables = []
            for line in sqlproc.stdout:
                if line.strip() == '__END__': break
                tables.append(line.strip())
            counts = {}
            for table in tables:
                sqlproc.stdin.write('SELECT count(*) FROM "' + table.replace('"','""') + '";\n'); sqlproc.stdin.flush()
                counts[table] = int(sqlproc.stdout.readline())
            if not {'accounts_user', 'gestion_client', 'gestion_subscription', 'django_migrations'}.issubset(counts):
                raise RuntimeError('Expected application tables absent')
        finally:
            sqlproc.stdin.close(); sqlproc.wait(timeout=20)
        for folder in ('media','private_media','secrets'):
            shutil.copytree((ROOT / folder).resolve(), payload / folder)
        shutil.copy2(ROOT / '.env', payload / '.env')
        config = payload / 'deployment'; config.mkdir()
        for file in ROOT.glob('docker-compose*.yml'):
            shutil.copy2(file, config / file.name)
        # Runtime values capture private overrides needed for disaster recovery.
        (config / 'web-environment.json').write_text(json.dumps(web_env))
        manifest = {'created_utc':stamp, 'database':env['POSTGRES_DB'], 'counts':counts, 'sources':{k:str(v) for k,v in mounts.items()}, 'sha256':{str(p.relative_to(payload)):digest(p) for p in payload.rglob('*') if p.is_file()}}
        (payload / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        plain = work / 'complete.tar.gz'
        with tarfile.open(plain, 'w:gz') as tar:
            for path in payload.iterdir(): tar.add(path, arcname=path.name)
        archive = STATE / name
        recipient = run('age-keygen','-y',IDENTITY).decode().strip()
        run('age','-r',recipient,'-o',str(archive),str(plain))
        upload_errors = []
        try:
            run('rclone','copyto',str(archive),remote+'/daily/'+name,'--s3-no-check-bucket','--retries','3')
        except Exception:
            upload_errors.append('R2')
        stage = '/backups/' + name
        try:
            run('docker','cp',str(archive),MEGA+':'+stage)
            mega_mkdir(REMOTE+'/daily')
            run('docker','exec',MEGA,'mega-put',stage,REMOTE+'/daily/')
        except Exception:
            upload_errors.append('MEGA')
        if upload_errors:
            raise RuntimeError('Upload failed: ' + ', '.join(upload_errors))
        downloaded = work / 'r2.age'
        run('rclone','copyto',remote+'/daily/'+name,str(downloaded),'--s3-no-check-bucket')
        if digest(downloaded) != digest(archive): raise RuntimeError('R2 digest mismatch')
        verify(downloaded,work,'r2')
        download_dir = '/backups/verify-v2-' + stamp
        run('docker','exec',MEGA,'mkdir','-m','700',download_dir)
        try:
            run('docker','exec',MEGA,'mega-get',REMOTE+'/daily/'+name,download_dir+'/')
            downloaded = work / 'mega.age'
            run('docker','cp',MEGA+':'+download_dir+'/'+name,str(downloaded))
            if digest(downloaded) != digest(archive): raise RuntimeError('MEGA digest mismatch')
            verify(downloaded,work,'mega')
            retention(remote, archive)
        finally:
            run('docker','exec',MEGA,'rm','-f',download_dir+'/'+name,stage)
            run('docker','exec',MEGA,'rmdir',download_dir)
        status = {'timestamp':dt.datetime.now(dt.timezone.utc).timestamp(),'archive':name,'tables':len(counts),'files':len(manifest['sha256']),'r2':'restored','mega':'restored'}
        (STATE / 'success.tmp').write_text(json.dumps(status))
        (STATE / 'success.tmp').replace(STATE / 'success.json')
        capacity()
        print(json.dumps(status))

if __name__ == '__main__':
    try:
        main()
    except BlockingIOError:
        print('Backup already running')
    except Exception as exc:
        # Never print subprocess output: it can contain credentials or data.
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        if isinstance(exc, sp.CalledProcessError):
            detail += ' command=' + ' '.join(exc.cmd[:4]) + ' exit=' + str(exc.returncode)
        print('BACKUP_FAILED ' + detail, file=sys.stderr)
        notify('JhelizTV: fallo de backup/verificación completa. Revisar jheliz-backup-v2.log.')
        sys.exit(1)
