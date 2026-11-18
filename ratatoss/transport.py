"""Contract for a future transport that exchanges staged batch files."""

from pathlib import Path
from typing import Protocol


class TransportAdapter(Protocol):
    """Session completion reports I/O completion. Verification belongs to the caller."""

    async def send(self, source: Path, session_code: str, *, timeout: float) -> None:
        """Send a staged batch using a session code supplied by coordination."""
        ...

    async def receive(self, destination: Path, session_code: str, *, timeout: float) -> None:
        """Receive into a caller-owned staging path."""
        ...
