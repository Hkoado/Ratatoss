"""Controller device identity and two-way pairing.

Interface for the job and consent layer (#8):

- `create_router(connect=..., pair_code_key=...)` returns the `/v1` enrollment
  and pairing routes to mount on the controller application.
- `authenticate(connection, authorization_headers)` returns the calling
  `Device`, or None for a missing, malformed, unknown or revoked token.
- `active_pair_id(connection, a, b)` returns the ACTIVE pair joining two
  devices. Use it to check each job target inside the job-creation transaction.
- `active_peer_ids(connection, device_id)` lists devices the caller may target.
- `issue_enrollment_code(connection, now_ms=...)` creates a one-time code for
  an administrator to share out of band.
"""

from .api import create_router
from .identity import Device, authenticate, enroll_device, issue_enrollment_code
from .pairing import active_pair_id, active_peer_ids

__all__ = [
    "Device",
    "active_pair_id",
    "active_peer_ids",
    "authenticate",
    "create_router",
    "enroll_device",
    "issue_enrollment_code",
]
