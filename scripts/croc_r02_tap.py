"""Loopback wire timing for the pinned Croc v11.6.5 benchmark profile."""

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from functools import partial
import time

# With one file, no compression and these MiB-aligned fixtures, Croc sends
# 32 KiB blocks on the relay data socket. The encrypted frame body consists of
# a 12-byte nonce, an 8-byte encrypted offset, payload, and a 16-byte tag.
PAYLOAD_BYTES = 32 * 1024
PAYLOAD_OFFSET = 12 + 8
PAYLOAD_END = PAYLOAD_OFFSET + PAYLOAD_BYTES
FRAME_BODY_BYTES = PAYLOAD_END + 16
MAX_ADMISSION_BYTES = 4096
TAP_READ_BYTES = 16 * 1024


@dataclass(frozen=True)
class PayloadInterval:
    first_ns: int
    last_ns: int
    payload_bytes: int
    frames: int
    wire_bytes: int


class DataFrames:
    """Count payload byte positions without inspecting or retaining frame bodies."""

    def __init__(self):
        self.header = bytearray()
        self.offset = 0
        self.size = 0
        self.frames = 0
        self.admission_seen = False
        self.payload_bytes = 0
        self.wire_bytes = 0
        self.first_ns = None
        self.last_ns = None
        self.invalid = False

    def observe(self, block: bytes, when_ns: int):
        self.wire_bytes += len(block)
        if self.invalid:
            return
        cursor = 0
        while cursor < len(block):
            if not self.size:
                count = min(8 - len(self.header), len(block) - cursor)
                self.header.extend(block[cursor:cursor + count])
                cursor += count
                if len(self.header) < 8:
                    return
                self.size = int.from_bytes(self.header[4:], "little")
                # Relay admission uses short frames. Once payload starts, only
                # full payload frames or the one-byte relay ping can follow.
                other = self.size == 1 or not self.frames and 0 < self.size <= MAX_ADMISSION_BYTES
                if self.header[:4] != b"croc" or not (self.size == FRAME_BODY_BYTES or other):
                    self.invalid = True
                    return
                self.admission_seen |= not self.frames and self.size != FRAME_BODY_BYTES
                if not self.admission_seen:
                    self.invalid = True
                    return
                self.header.clear()
                self.offset = 0

            count = min(self.size - self.offset, len(block) - cursor)
            next_offset = self.offset + count
            if self.size == FRAME_BODY_BYTES:
                seen = min(next_offset, PAYLOAD_END) - max(self.offset, PAYLOAD_OFFSET)
                if seen > 0:
                    if self.first_ns is None:
                        self.first_ns = when_ns
                    self.last_ns = when_ns
                    self.payload_bytes += seen
            cursor += count
            self.offset = next_offset
            if self.offset == self.size:
                self.frames += self.size == FRAME_BODY_BYTES
                self.size = 0

    def interval(self, expected_bytes: int) -> PayloadInterval | None:
        if (self.invalid or self.header or self.size or self.payload_bytes != expected_bytes
                or self.frames * PAYLOAD_BYTES != expected_bytes
                or self.first_ns is None or self.last_ns <= self.first_ns):
            return None
        return PayloadInterval(self.first_ns, self.last_ns, self.payload_bytes, self.frames, self.wire_bytes)


class RelayTap:
    """Forward only the locked loopback relay ports for one B-side Croc role."""

    def __init__(self, listen_host: str, relay_host: str, ports: tuple[int, int], *, transmit: bool):
        self.listen_host = listen_host
        self.relay_host = relay_host
        self.ports = ports
        self.transmit = transmit
        self.connections = set()
        self.flows = []

    def interval(self, expected_bytes: int) -> PayloadInterval | None:
        flows = [flow for flow in self.flows if flow.payload_bytes or flow.invalid]
        return flows[0].interval(expected_bytes) if len(flows) == 1 else None

    @asynccontextmanager
    async def listen(self):
        servers = []
        try:
            for port in self.ports:
                servers.append(await asyncio.start_server(
                    partial(self._accept, port), self.listen_host, port,
                ))
            yield self
        finally:
            for server in servers:
                server.close()
            for task in tuple(self.connections):
                task.cancel()
            await asyncio.gather(*self.connections, return_exceptions=True)
            for server in servers:
                await server.wait_closed()

    def _accept(self, port, reader, writer):
        task = asyncio.create_task(self._bridge(port, reader, writer))
        self.connections.add(task)
        task.add_done_callback(self.connections.discard)

    async def _bridge(self, port, peer_reader, peer_writer):
        flow = DataFrames() if port == self.ports[1] else None
        if flow is not None:
            self.flows.append(flow)
        relay_writer = None
        pumps = []
        try:
            relay_reader, relay_writer = await asyncio.open_connection(self.relay_host, port)
            pumps = [
                asyncio.create_task(self._pump(peer_reader, relay_writer, flow if self.transmit else None)),
                asyncio.create_task(self._pump(relay_reader, peer_writer, flow if not self.transmit else None)),
            ]
            await asyncio.gather(*pumps)
        except OSError:
            # The relay or child may close the socket on a fault run. Incomplete
            # or reset data streams cannot be used as measurement evidence.
            if flow is not None and (flow.size or flow.header):
                flow.invalid = True
        finally:
            for task in pumps:
                task.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            for writer in (peer_writer, relay_writer):
                if writer is not None:
                    writer.close()
                    with suppress(OSError):
                        await writer.wait_closed()

    @staticmethod
    async def _pump(reader, writer, flow):
        while block := await reader.read(TAP_READ_BYTES):
            if flow is not None:
                flow.observe(block, time.monotonic_ns())
            writer.write(block)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
