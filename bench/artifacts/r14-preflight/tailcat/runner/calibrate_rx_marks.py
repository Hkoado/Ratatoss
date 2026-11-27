"""Validate the file-size poller against RelayTap on one local Croc transfer.

All processes run natively on this Mac, so every timestamp uses the same
host monotonic clock. B sends b-to-c-32mib.bin to C over a local relay on ::1.
RelayTap (scripts/croc_r02_tap.py) on 127.0.0.1 records TX payload frames at B.
A poller stats C's receive file every POLL seconds and records file growth.
Croc output is discarded; secrets are random and never written to disk.
Usage: python3 -I obs-validate.py <repo_scripts_dir> <fixture_dir> <workdir> [poll_s]
"""
import asyncio, hashlib, json, os, secrets, subprocess, sys, threading, time

SCRIPTS, FIX, W = sys.argv[1], sys.argv[2], sys.argv[3]
POLL = float(sys.argv[4]) if len(sys.argv) > 4 else 0.005
sys.path.insert(0, SCRIPTS)
from croc_r02_tap import RelayTap  # noqa: E402

X = os.path.expanduser('~/Library/Caches/Ratatoss/mac-c.g0mZhb/croc')
SIZE = 32 * 1024 * 1024
FLAGS = ['--disable-clipboard', '--no-update-check', '--no-compress']
pw, code = secrets.token_hex(24), '5522-' + secrets.token_hex(18)
for d in ('cfg-relay', 'cfg-b', 'cfg-c', 'rx-c'):
    os.makedirs(f'{W}/{d}', exist_ok=True)
target = f'{W}/rx-c/b-to-c-32mib.bin'
samples = []          # (mono_ns, size) whenever size changes
stop = threading.Event()


def poll():
    last = -1
    while not stop.is_set():
        try:
            size = os.stat(target).st_blocks * 512
        except FileNotFoundError:
            size = -1
        if size != last:
            samples.append((time.monotonic_ns(), size))
            last = size
        time.sleep(POLL)


rx_lines = []


def watch(stream):
    import re
    buf = b''
    for chunk in iter(lambda: stream.read1(65536), b''):
        t = time.monotonic_ns()
        *lines, buf = re.split(rb'[\r\n]', buf + chunk)
        for raw in lines:
            line = raw.decode(errors='replace').replace(code, '<redacted>').replace(pw, '<redacted>')
            m = re.search(r'(\d+)%', line)
            if m or 'finished receiving' in line:
                rx_lines.append((t, int(m.group(1)) if m else 'finished'))


def croc(args, cwd, cfg, extra_env, capture=False):
    env = {**os.environ, 'CROC_CONFIG_DIR': f'{W}/{cfg}', **extra_env}
    if not capture:
        return subprocess.Popen([X, *args], cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p = subprocess.Popen([X, *args], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    threading.Thread(target=watch, args=(p.stdout,), daemon=True).start()
    return p


async def main():
    relay = croc([*FLAGS, 'relay', '--host', '::1', '--ports', '19009,19010'], W, 'cfg-relay', {'CROC_PASS': pw})
    await asyncio.sleep(0.6)
    tap = RelayTap('127.0.0.1', '::1', (19009, 19010), transmit=True)
    threading.Thread(target=poll, daemon=True).start()
    try:
        async with tap.listen():
            env = {'CROC_PASS': pw, 'CROC_SECRET': code}
            tx = croc(['--throttleUpload', '8M', *FLAGS, '--relay', '127.0.0.1:19009', 'send', '--no-local',
                       '--transport', 'relay', '--no-multi', f'{FIX}/b-to-c-32mib.bin'], W, 'cfg-b', env)
            deadline = time.monotonic() + 20
            while not tap.connections and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            await asyncio.sleep(1.5)
            loop = asyncio.get_running_loop()
            for attempt in range(3):
                rx_lines.clear()
                rx = croc(['--debug', *FLAGS, '--relay', '127.0.0.1:19009', '--yes'], f'{W}/rx-c', 'cfg-c', env, capture=True)
                rx_rc = await loop.run_in_executor(None, rx.wait)
                if rx_rc == 0 or tx.poll() is not None:
                    break
                await asyncio.sleep(1)
            try:
                tx_rc = await asyncio.wait_for(loop.run_in_executor(None, tx.wait), 30)
            except asyncio.TimeoutError:
                tx.kill(); tx_rc = 'killed'
            rcs = [tx_rc, rx_rc, attempt + 1]
            await asyncio.sleep(0.2)
    finally:
        stop.set()
        relay.terminate(); relay.wait()
    interval = tap.interval(SIZE)
    grow = [s for s in samples if s[1] > 0]
    first_grow = grow[0] if grow else None
    full = next((s for s in samples if s[1] >= SIZE), None)
    digest = hashlib.sha256(open(target, 'rb').read()).hexdigest() if os.path.exists(target) else None
    out = {
        'poll_s': POLL, 'exit_codes': rcs, 'sha256_c': digest,
        'tap': None if interval is None else {'first_ns': interval.first_ns, 'last_ns': interval.last_ns,
                                              'payload_bytes': interval.payload_bytes},
        'file_first_nonzero': first_grow, 'file_full': full,
        'first_size_samples': samples[:4], 'distinct_sizes': len({s[1] for s in samples}),
    }
    if interval and first_grow and full:
        out['first_lag_ms'] = (first_grow[0] - interval.first_ns) / 1e6
        out['last_lag_ms'] = (full[0] - interval.last_ns) / 1e6
        out['tap_span_s'] = (interval.last_ns - interval.first_ns) / 1e9
        out['file_span_s'] = (full[0] - first_grow[0]) / 1e9
    if interval:
        pos = [x for x in rx_lines if isinstance(x[1], int) and x[1] > 0]
        hundred = next((x for x in rx_lines if x[1] == 100), None)
        fin = next((x for x in rx_lines if x[1] == 'finished'), None)
        out['progress_first_lag_ms'] = (pos[0][0] - interval.first_ns) / 1e6 if pos else None
        out['progress_first_pct'] = pos[0][1] if pos else None
        out['progress_100_lag_ms'] = (hundred[0] - interval.last_ns) / 1e6 if hundred else None
        out['finished_lag_ms'] = (fin[0] - interval.last_ns) / 1e6 if fin else None
        out['progress_updates'] = len(pos)
        gaps = [(b[0] - a[0]) / 1e6 for a, b in zip(pos, pos[1:])]
        out['progress_gap_ms_max'] = max(gaps) if gaps else None
    print(json.dumps(out, indent=1))

asyncio.run(main())
