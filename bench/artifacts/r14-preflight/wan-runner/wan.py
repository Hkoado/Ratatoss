from pathlib import Path
from datetime import datetime
import hashlib,json,os,re,secrets,subprocess as s,threading,time,sys
os.umask(0o077)
root=Path(__file__).resolve().parent
base=(root/'wan-lab-id').read_text()
b,c,r=[base+'-'+role for role in ('b','c','relay')]
def run(*args):
    return s.check_output(['docker',*args],text=True,timeout=15).strip()
# Croc prints the receive instructions, including the session code and the
# relay --pass, on stderr. Only allowlisted milestone/error lines reach the log.
ALLOWED=re.compile(r'\d+%|error|fail|timeout|refused|reset|EOF|panic|finished|connected to|banner|Tailcat|path=|transport|pake',re.I)
SECRET_VARS=('CROC_SECRET','CROC_PASS')
def pump(stream,path,hidden):
    with open(path,'ab') as out:
        buf=b''
        for chunk in iter(lambda: stream.read1(65536),b''):
            *lines,buf=re.split(rb'[\r\n]',buf+chunk)
            for raw in lines:
                line=raw.decode(errors='replace')
                for value in hidden:
                    line=line.replace(value,'<redacted>')
                if '--pass' in line or 'CROC_SECRET' in line or not ALLOWED.search(line):
                    continue
                out.write((line+'\n').encode()); out.flush()
def start(node,cmd,folder,variables):
    hidden=[value for name,value in variables.items() if name in SECRET_VARS and value]
    proc=s.Popen(['docker','exec','-w',folder,*[arg for name in variables for arg in ('-e',name)],node,'/croc',*cmd],env={**os.environ,**variables},stderr=s.STDOUT,stdout=s.PIPE)
    proc.pump=threading.Thread(target=pump,args=(proc.stdout,root/(node+folder.replace("/", "-")+".log"),hidden),daemon=True)
    proc.pump.start()
    return proc
def wait_file(node,path,sec,proc=None):
    deadline=time.monotonic()+sec
    while time.monotonic()<deadline:
        if s.run(['docker','exec',node,'test','-f',path]).returncode==0:
            return
        if proc is not None and proc.poll() is not None:
            raise RuntimeError('Croc stopped before first observed payload')
        time.sleep(.05)
    raise TimeoutError(path)
flags=['--disable-clipboard','--no-update-check','--no-compress']
def stamp(): return datetime.now().astimezone().isoformat(timespec='seconds')
codefile=root/'wan-code'
try:
    src='/private/tmp/ratatoss-issue60.rWLFYq/scripts/croc_r02_tap.py'
    run('cp',src,b+':/work/croc_r02_tap.py')
    run('cp',str(root/'observe.py'),b+':/work/observe.py')
    run('exec','-d',b,'python','-B','/work/observe.py')
    wait_file(b,'/lab/ready',5)
    local_password=secrets.token_hex(24)
    local_code='5522-'+secrets.token_hex(18)
    relay=start(r,flags+['relay','--host','0.0.0.0','--ports','19009,19010'],'/lab',{'CROC_PASS':local_password})
    time.sleep(.4)
    run('exec',b,'python','-c',"import socket; socket.create_connection(('relay',19009), timeout=2).close()")
    print('B observer and local relay ready',stamp(),flush=True)
    deadline=time.monotonic()+3300
    while time.monotonic()<deadline:
        if codefile.exists() and codefile.read_text().strip():
            break
        time.sleep(.4)
    else: sys.exit('Timed out waiting for the private WAN code')
    code=codefile.read_text().strip()
    codefile.unlink()
    began=stamp()
    local_env={'CROC_PASS':local_password,'CROC_SECRET':local_code}
    attempts_until=time.monotonic()+900
    attempt=0
    while time.monotonic()<attempts_until:
        attempt+=1
        print('A-B receiver attempt',attempt,stamp(),flush=True)
        brx=start(b,['--debug',*flags]+['--ip','127.0.0.2:9009','--yes'],'/lab/rx',{'CROC_SECRET':code,'CROC_CONFIG_DIR':'/lab/rx'})
        try:
            wait_file(b,'/lab/started-rx',180,brx)
            break
        except RuntimeError:
            brx.pump.join(timeout=2)
            message=((root/(b+'-lab-rx.log')).read_text(errors='replace').strip().splitlines() or [''])[-1]
            print('Relay wait timed out' if 'timeout' in message else 'Receiver exited without captured data',stamp(),flush=True)
            time.sleep(5)
    else:
        raise TimeoutError('Waiting for sender with matching code')
    btx=start(b,['--throttleUpload','8M',*flags,'--relay','127.0.0.3:19009','send','--no-local','--transport','relay','--no-multi','/fixtures/b-to-c-32mib.bin'],'/lab/tx',{**local_env,'CROC_CONFIG_DIR':'/lab/tx'})
    crx=start(c,flags+['--relay','relay:19009','--yes'],'/lab/rx',local_env)
    for proc in (brx,btx,crx):
        code_=proc.wait(timeout=180)
        proc.pump.join(timeout=2)
        if code_:
            raise RuntimeError('Croc transfer failed')
    run('exec',b,'touch','/lab/stop')
    wait_file(b,'/lab/intervals',5)
    timings=json.loads(run('exec',b,'cat','/lab/intervals'))
    results={}
    for node,name,digest in [(b,'a-32mib.bin','25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a'),(c,'b-to-c-32mib.bin','7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679')]:
        path='/lab/rx/'+name
        size=int(run('exec',node,'stat','-c','%s',path))
        actual=run('exec',node,'sha256sum',path).split()[0]
        if size!=33554432 or actual!=digest: raise RuntimeError('Fixture mismatch')
        results[name]={'bytes':size,'sha256':actual}
    overlap=None
    if all(timings.values()):
        overlap=max(0,min(v['last_ns'] for v in timings.values())-max(v['first_ns'] for v in timings.values()))
    (root/'wan-result.json').write_text(json.dumps({'started_at':began,'completed_at':stamp(),'routes':{'A-B':'1.getcroc.com:9009','B-C':'Docker internal relay'},'files':results,'intervals':timings,'payload_overlap_ns':overlap},indent=2))
    print('Completed',stamp(),'overlap_ns',overlap)
finally:
    if codefile.exists(): codefile.unlink()
    s.run(['docker','rm','-f',b,c,r],stdout=s.DEVNULL,stderr=s.DEVNULL)
    s.run(['docker','network','rm',base],stdout=s.DEVNULL,stderr=s.DEVNULL)
