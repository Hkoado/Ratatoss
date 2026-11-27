import asyncio
from contextlib import AsyncExitStack
from dataclasses import asdict
from functools import partial
import json
from pathlib import Path
from croc_r02_tap import RelayTap

def measure(taps):
    streams=[]
    for tap in taps:
        for flow in tap.flows:
            if flow.invalid:
                return None
            if flow.payload_bytes:
                value=flow.interval(flow.payload_bytes)
                if value is None:
                    return None
                streams.append(dict(port=tap.ports[1],**asdict(value)))
    if sum(s['payload_bytes'] for s in streams)!=32*1024**2:
        return None
    return dict(first_ns=min(s['first_ns'] for s in streams),last_ns=max(s['last_ns'] for s in streams),payload_bytes=sum(s['payload_bytes'] for s in streams),frames=sum(s['frames'] for s in streams),streams=streams)

async def observe():
    rx=[RelayTap('127.0.0.2','1.getcroc.com',(9009,port),transmit=False) for port in range(9010,9018)]
    tx=RelayTap('127.0.0.3','relay',(19009,19010),transmit=True)
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(rx[0].listen())
        await stack.enter_async_context(tx.listen())
        for tap in rx[1:]:
            port=tap.ports[1]
            server=await asyncio.start_server(partial(tap._accept,port),tap.listen_host,port)
            await stack.enter_async_context(server)
        Path('/lab/ready').touch()
        started=Path('/lab/started-rx')
        while not Path('/lab/stop').exists():
            if not started.exists() and any(f.first_ns is not None for t in rx for f in t.flows):
                started.touch()
            await asyncio.sleep(.005)
    Path('/lab/intervals').write_text(json.dumps(dict(rx=measure(rx),tx=measure([tx]))))
asyncio.run(observe())
