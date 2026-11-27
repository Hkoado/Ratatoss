from pathlib import Path
import subprocess as s,json,secrets
root=Path(__file__).resolve().parent
report=json.loads((root/'bc-mac.json').read_text())
token='r14-wan-'+secrets.token_hex(4)
(root/'wan-lab-id').write_text(token)
def d(*a): s.run(['docker',*a],check=True,stdout=s.DEVNULL)
d('network','create','--internal',token)
for role in ('b','c','relay'):
 n=token+'-'+role
 d('run','--rm','-d','--name',n,'--network',token,'--network-alias',role,'--mount','type=bind,src=/private/tmp/ratatoss-croc60.CnMTVP/croc,dst=/croc,readonly',report['image'],'sleep','3600')
 d('exec',n,'mkdir','-p','/lab/rx','/lab/tx','/fixtures','/work/scripts')
d('network','connect','bridge',token+'-b')
d('cp',str(Path.home()/'Library/Caches/Ratatoss/issue60.Sr3HOn/fixture/b-to-c-32mib.bin'),token+'-b:/fixtures/')
