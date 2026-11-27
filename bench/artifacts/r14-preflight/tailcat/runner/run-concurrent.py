"""#60 concurrent run on the lab Mac: A->B (Tailcat, remote A) while B->C (local relay, RelayTap).

All B and C processes run natively on this Mac, so every timestamp below is
time.monotonic_ns() of this host.

  rx_first  first increase of st_blocks of B's receive file (poll POLL_S)
  rx_last   Croc debug line "finished receiving" of B's receiver
  tx_first/tx_last  RelayTap payload frames B->C on the local relay data port

B->C sender waits in its room from the start; C joins at rx_first, which
starts the B->C payload. Croc output is filtered (allowlist) and secrets are
redacted; IP addresses are scrubbed. Requires Python 3.11 (RelayTap).

Usage: python -I run-concurrent.py <scripts_dir> <fixture_dir> <session_dir> [ab_relay]
<session_dir>/code holds the A->B Croc code (43 chars); it is deleted after reading.
"""
import asyncio, csv, datetime, hashlib, json, os, re, secrets, subprocess, sys, threading, time

SCRIPTS, FIX, R = sys.argv[1], sys.argv[2], sys.argv[3]
AB_RELAY = sys.argv[4] if len(sys.argv) > 4 else '1.getcroc.com:9009'
sys.path.insert(0, SCRIPTS)
from croc_r02_tap import RelayTap  # noqa: E402

X = os.path.expanduser('~/Library/Caches/Ratatoss/mac-c.g0mZhb/croc')
SIZE = 32 * 1024 * 1024
POLL_S = 0.005
FLAGS = ['--disable-clipboard', '--no-update-check', '--no-compress']
code = open(f'{R}/code').read().strip()
os.unlink(f'{R}/code')
if len(code) != 43 and AB_RELAY == '1.getcroc.com:9009':
    sys.exit(f'A->B code has {len(code)} characters, expected 43')
pw, bc_code = secrets.token_hex(24), '5522-' + secrets.token_hex(18)
HIDDEN = [code, pw, bc_code]
for d in ('rx-b', 'rx-c', 'cfg-b-rx', 'cfg-b-tx', 'cfg-c', 'cfg-relay'):
    os.makedirs(f'{R}/{d}', exist_ok=True)
rx_file = f'{R}/rx-b/a-32mib.bin'
c_file = f'{R}/rx-c/b-to-c-32mib.bin'
ALLOWED = re.compile(r'\d+%|error|fail|timeout|refused|reset|EOF|panic|finished|connected to|banner|Tailcat|path=|transport|pake', re.I)
V4 = re.compile(r'\d{1,3}(?:\.\d{1,3}){3}')
V6 = re.compile(r'\b[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{0,4}){3,7}\b')
events = {}
stop = threading.Event()


def wall():
    return datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')


def scrub(line):
    for value in HIDDEN:
        line = line.replace(value, '<redacted>')
    return V6.sub('<v6>', V4.sub('<v4>', line))


def pump(proc, name):
    with open(f'{R}/{name}.log', 'a') as out:
        buf = b''
        for chunk in iter(lambda: proc.stdout.read1(65536), b''):
            t = time.monotonic_ns()
            *lines, buf = re.split(rb'[\r\n]', buf + chunk)
            for raw in lines:
                line = scrub(raw.decode(errors='replace'))
                if '--pass' in line or 'CROC_SECRET' in line or not ALLOWED.search(line):
                    continue
                if name == 'b-rx' and 'finished receiving' in line and 'rx_last' not in events:
                    events['rx_last'] = t
                if name == 'b-rx' and 'Tailcat transport summary' in line:
                    events['tailcat_summary'] = line.split('Tailcat transport summary:')[-1].strip()
                out.write(f'{t} {line}\n')
                out.flush()


def croc(name, args, cwd, cfg, env_extra, quiet=False):
    env = {**os.environ, 'CROC_CONFIG_DIR': f'{R}/{cfg}', **env_extra}
    if quiet:
        return subprocess.Popen([X, *args], cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc = subprocess.Popen([X, *args], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    proc.pump = threading.Thread(target=pump, args=(proc, name), daemon=True)
    proc.pump.start()
    return proc


def poll_blocks(started):
    while not stop.is_set():
        try:
            blocks = os.stat(rx_file).st_blocks
        except FileNotFoundError:
            blocks = 0
        if blocks > 0:
            events['rx_first'] = time.monotonic_ns()
            events['rx_first_wall'] = wall()
            started.set()
            return
        time.sleep(POLL_S)


def sample_sockets(pid):
    with open(f'{R}/b-rx-sockets.csv', 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['mono_ns', 'proto', 'local_port', 'interface', 'bytes_in', 'bytes_out'])
        while not stop.is_set():
            t = time.monotonic_ns()
            try:
                out = subprocess.run(['nettop', '-L', '1', '-p', str(pid), '-n', '-x'],
                                     capture_output=True, text=True, timeout=10).stdout
            except Exception:
                out = ''
            for line in out.splitlines():
                cols = line.split(',')
                m = re.match(r'(udp[46]|tcp[46]) (\S+)<->', cols[1]) if len(cols) > 5 else None
                if m:
                    w.writerow([t, m.group(1), re.split(r'[:.]', m.group(2))[-1], cols[2], cols[4], cols[5]])
            fh.flush()
            stop.wait(1.0)


def sha(path):
    if not os.path.exists(path):
        return None, None
    return os.path.getsize(path), hashlib.sha256(open(path, 'rb').read()).hexdigest()


async def main():
    loop = asyncio.get_running_loop()
    began = wall()
    relay = croc('relay', [*FLAGS, 'relay', '--host', '::1', '--ports', '19009,19010'], R, 'cfg-relay',
                 {'CROC_PASS': pw}, quiet=True)
    await asyncio.sleep(0.6)
    tap = RelayTap('127.0.0.1', '::1', (19009, 19010), transmit=True)
    procs = {}
    try:
        async with tap.listen():
            local = {'CROC_PASS': pw, 'CROC_SECRET': bc_code}
            procs['b-tx'] = croc('b-tx', ['--throttleUpload', '8M', *FLAGS, '--relay', '127.0.0.1:19009', 'send',
                                          '--no-local', '--transport', 'relay', '--no-multi',
                                          f'{FIX}/b-to-c-32mib.bin'], R, 'cfg-b-tx', local)
            deadline = time.monotonic() + 20
            while not tap.connections and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            if not tap.connections:
                raise RuntimeError('B->C sender did not reach the local relay')
            started = threading.Event()
            threading.Thread(target=poll_blocks, args=(started,), daemon=True).start()
            print('B/C ready', wall(), flush=True)
            procs['b-rx'] = croc('b-rx', ['--debug', *FLAGS, '--relay', AB_RELAY, '--yes'], f'{R}/rx-b', 'cfg-b-rx',
                                 {'CROC_SECRET': code})
            threading.Thread(target=sample_sockets, args=(procs['b-rx'].pid,), daemon=True).start()
            while not started.is_set():
                if procs['b-rx'].poll() is not None:
                    raise RuntimeError(f"A->B receiver exited {procs['b-rx'].returncode} before payload")
                await asyncio.sleep(0.005)
            procs['c-rx'] = croc('c-rx', [*FLAGS, '--relay', '127.0.0.1:19009', '--yes'], f'{R}/rx-c', 'cfg-c', local)
            print('rx_first; C joined', events['rx_first_wall'], flush=True)
            rcs = {}
            for name in ('b-rx', 'b-tx', 'c-rx'):
                try:
                    rcs[name] = await asyncio.wait_for(loop.run_in_executor(None, procs[name].wait), 300)
                except asyncio.TimeoutError:
                    procs[name].kill()
                    rcs[name] = 'killed'
                procs[name].pump.join(2)
            await asyncio.sleep(0.2)
    finally:
        stop.set()
        for p in procs.values():
            if p.poll() is None:
                p.kill()
        relay.terminate()
        relay.wait()
    tx = tap.interval(SIZE)
    b_bytes, b_sha = sha(rx_file)
    c_bytes, c_sha = sha(c_file)
    res = {
        'started_at': began, 'completed_at': wall(), 'ab_relay_control': AB_RELAY,
        'exit_codes': rcs,
        'A-B': {'bytes': b_bytes, 'sha256': b_sha, 'tailcat_summary': events.get('tailcat_summary')},
        'B-C': {'bytes': c_bytes, 'sha256': c_sha},
        'marks_ns': {'rx_first': events.get('rx_first'), 'rx_last': events.get('rx_last'),
                     'tx_first': tx.first_ns if tx else None, 'tx_last': tx.last_ns if tx else None},
        'rx_first_wall': events.get('rx_first_wall'),
        'tx_payload_bytes': tx.payload_bytes if tx else None,
        'poll_s': POLL_S,
    }
    m = res['marks_ns']
    if all(m.values()):
        res['overlap_ns'] = max(0, min(m['rx_last'], m['tx_last']) - max(m['rx_first'], m['tx_first']))
        res['goodput_MiBps'] = {'A-B': 32 / ((m['rx_last'] - m['rx_first']) / 1e9),
                                'B-C': 32 / ((m['tx_last'] - m['tx_first']) / 1e9)}
        res['tx_first_after_rx_first_ms'] = (m['tx_first'] - m['rx_first']) / 1e6
    fam = {}
    path = f'{R}/b-rx-sockets.csv'
    if os.path.exists(path):
        last = {}
        for row in csv.DictReader(open(path)):
            last[(row['proto'], row['local_port'])] = row
        for (proto, _), row in last.items():
            fam.setdefault(proto, [0, 0])
            fam[proto][0] += int(row['bytes_in'])
            fam[proto][1] += int(row['bytes_out'])
    res['b_rx_socket_bytes_by_family'] = {k: {'in': v[0], 'out': v[1]} for k, v in fam.items()}
    json.dump(res, open(f'{R}/result.json', 'w'), indent=2)
    print(json.dumps(res, indent=2))

asyncio.run(main())
