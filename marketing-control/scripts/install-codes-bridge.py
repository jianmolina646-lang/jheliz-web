"""Run as root on the VPS; preserves the running Telegram configuration."""
import json
import os
import secrets
import subprocess
from pathlib import Path

def run(*args):
    return subprocess.check_output(args, text=True).strip()

source = json.loads(run('docker','inspect','jheliz-codes_bot-1'))[0]
root = Path('/opt/jheliz-codes-bridge')
root.mkdir(mode=0o700, exist_ok=True)
key = secrets.token_hex(32)
environment = dict(item.split('=',1) for item in source['Config']['Env'])
environment.update(WHATSAPP_CODES_BRIDGE_SECRET=key, WHATSAPP_CODES_ADMIN_NUMBERS='51978640413')
env_file = root/'bridge.env'
env_file.write_text('\n'.join(f'{k}={v}' for k,v in environment.items())+'\n')
env_file.chmod(0o600)
net='jheliz-codes-private'
if net not in run('docker','network','ls','--format','{{.Name}}').splitlines():
    run('docker','network','create',net)
if 'jheliz-codes-bridge' in run('docker','ps','-a','--format','{{.Names}}').splitlines():
    raise RuntimeError('Bridge already exists; inspect it before replacing.')
args=['docker','create','--name','jheliz-codes-bridge','--restart','unless-stopped','--network',net,'--network-alias','codes-bridge','--env-file',str(env_file),'--workdir',source['Config']['WorkingDir'] or '/app']
for mount in source['Mounts']:
    args += ['--mount',f"type={mount['Type']},source={mount.get('Name') or mount['Source']},target={mount['Destination']}"+(',readonly' if not mount['RW'] else '')]
for host in source['HostConfig'].get('ExtraHosts') or []:
    args += ['--add-host',host]
for filename in ('whatsapp_bridge.py','whatsapp_wsgi.py','whatsapp_urls.py'):
    args += ['--mount',f'type=bind,source={root/filename},target=/app/codes/{filename},readonly']
args += [source['Image'],'gunicorn','codes.whatsapp_wsgi:application','--bind','0.0.0.0:4010','--workers','1','--threads','4','--timeout','90','--access-logfile','/dev/null']
run(*args)
for network, options in source['NetworkSettings']['Networks'].items():
    run('docker','network','connect','--gw-priority',str(options.get('GwPriority',0)),network,'jheliz-codes-bridge')
run('docker','start','jheliz-codes-bridge')
project=Path('/opt/jheliz-marketing-control')
override=project/'compose.codes.json'
override.write_text(json.dumps({'services':{'worker':{'environment':{'CODES_BRIDGE_SECRET':key,'CODES_BRIDGE_URL':'http://codes-bridge:4010/_internal/codes/whatsapp/','CODES_WHATSAPP_INSTANCE_NAME':'codigos jheliz'},'networks':['default','codes_private']}},'networks':{'codes_private':{'external':True,'name':net}}}))
override.chmod(0o600)
print('Private bridge created; WhatsApp override prepared. No secrets printed.')
