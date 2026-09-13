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
PREFIX = 'jheliztv.xyz/complete-v2'
REMOTE = 'mailcontrol_drive:ProductionBackups/jheliztv.xyz/complete-v2'

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
    os.environ.update(RCLONE_CONFIG='/root/.config/production-backups/drive/rclone.conf', RCLONE_CONFIG_R2_TYPE='s3', RCLONE_CONFIG_R2_PROVIDER='Cloudflare', RCLONE_CONFIG_R2_ENDPOINT=env['R2_ENDPOINT'], RCLONE_CONFIG_R2_ACCESS_KEY_ID=env['R2_ACCESS_KEY_ID'], RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=env['R2_SECRET_ACCESS_KEY'])
    return 'r2:' + env['R2_BUCKET'] + '/' + PREFIX

def digest(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def inspect(name):
    return json.loads(run('docker', 'inspect', name))[0]

def retention(remote, archive):
    """Prune only inventoried CompleteV2 copies, after both restores succeed."""
    today = dt.datetime.now(dt.timezone.utc)
    inventory_path = STATE / 'inventory.json'
    inventory = json.loads(inventory_path.read_text()) if inventory_path.exists() else {}
    policy = {'daily': (14, 14), 'weekly': (8, 8), 'monthly': (12, 12)}
    pattern = r'jheliz-complete-[0-9W-]+\.tar\.gz\.age'
    for tier in policy:
        for name in inventory.get(tier, []):
            if not re.fullmatch(pattern, name):
                raise RuntimeError('Invalid retention inventory')
    # Drive and R2 keep independent inventories and identical retention windows.
    drive = inventory.setdefault('_drive', {tier: [] for tier in policy})
    for tier in policy:
        if any(not re.fullmatch(pattern, name) for name in drive.get(tier, [])):
            raise RuntimeError('Invalid Drive retention inventory')

    def save():
        (STATE / 'inventory.tmp').write_text(json.dumps(inventory))
        (STATE / 'inventory.tmp').replace(inventory_path)

    additions = {'daily': archive.name}
    if today.weekday() == 6:
        additions['weekly'] = 'jheliz-complete-' + today.strftime('%G-W%V') + '.tar.gz.age'
    if today.day == 1:
        additions['monthly'] = 'jheliz-complete-' + today.strftime('%Y%m') + '.tar.gz.age'
    for tier, name in additions.items():
        if not re.fullmatch(pattern, name):
            raise RuntimeError('Invalid archive name')
        if tier != 'daily' and name not in inventory.get(tier, []):
            # Copy the already verified object, not an independently rebuilt archive.
            run('rclone','copyto',remote+'/daily/'+archive.name,remote+'/'+tier+'/'+name,'--s3-no-check-bucket','--immutable')
        if tier != 'daily' and name not in drive.get(tier, []):
            run('rclone','copyto',str(archive),REMOTE+'/'+tier+'/'+name,'--immutable')
        inventory[tier] = sorted(set(inventory.get(tier, []) + [name]), reverse=True)
        drive[tier] = sorted(set(drive.get(tier, []) + [name]), reverse=True)
    save()
    for tier, (keep_r2, keep_drive) in policy.items():
        for old in sorted(drive.get(tier, []), reverse=True)[keep_drive:]:
            run('rclone','deletefile',REMOTE+'/'+tier+'/'+old,'--drive-use-trash=false')
            drive[tier].remove(old)
            save()
            print('RETENTION_DRIVE_REMOVED ' + tier + '/' + old)
        for old in sorted(inventory.get(tier, []), reverse=True)[keep_r2:]:
            run('rclone','deletefile',remote+'/'+tier+'/'+old,'--s3-no-check-bucket')
            inventory[tier].remove(old)
            save()
            print('RETENTION_R2_EXPIRED_REMOVED ' + tier + '/' + old)
    # Honor the original grace period for objects archived by the previous policy.
    for item in list(inventory.get('_expired', [])):
        if not re.fullmatch(r'(daily|weekly|monthly)/' + pattern, item['key']):
            raise RuntimeError('Invalid expired inventory')
        if today.timestamp() - item['timestamp'] > 30 * 86400:
            run('rclone','deletefile',remote+'/expired/'+item['key'],'--s3-no-check-bucket')
            inventory['_expired'].remove(item)
            save()
    for old in sorted(STATE.glob('jheliz-complete-*.tar.gz.age'), reverse=True)[2:]:
        if re.fullmatch(pattern, old.name):
            old.unlink()

def capacity():
    remote_config()
    info = json.loads(run('rclone','about','mailcontrol_drive:','--json'))
    percent = 100 * (1 - info.get('free', 0) / info['total']) if info.get('total') else 0
    print('DRIVE_USED_PERCENT=' + str(round(percent, 2)))
    flag = STATE / 'capacity-warning-date'
    day = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')
    if percent >= 85 and (not flag.exists() or flag.read_text() != day):
        notify('JhelizTV: Google Drive al ' + str(round(percent, 2)) + '%. Revisar capacidad.')
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
        (config / 'git-revision.txt').write_bytes(run('git', '-c', 'safe.directory='+str(ROOT), '-C', str(ROOT), 'rev-parse', 'HEAD'))
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
        try:
            run('rclone','copyto',str(archive),REMOTE+'/daily/'+name,'--retries','3')
        except Exception:
            upload_errors.append('Google Drive')
        if upload_errors:
            raise RuntimeError('Upload failed: ' + ', '.join(upload_errors))
        downloaded = work / 'r2.age'
        run('rclone','copyto',remote+'/daily/'+name,str(downloaded),'--s3-no-check-bucket')
        if digest(downloaded) != digest(archive): raise RuntimeError('R2 digest mismatch')
        verify(downloaded,work,'r2')
        downloaded = work / 'drive.age'
        run('rclone','copyto',REMOTE+'/daily/'+name,str(downloaded),'--retries','3')
        if digest(downloaded) != digest(archive): raise RuntimeError('Drive digest mismatch')
        verify(downloaded,work,'drive')
        retention(remote, archive)
        status = {'timestamp':dt.datetime.now(dt.timezone.utc).timestamp(),'archive':name,'tables':len(counts),'files':len(manifest['sha256']),'r2':'restored','drive':'restored'}
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
