"""Heartbeat and boot-scoped replacement of verified controller inventory."""

from .registry import Registry, RegistryError, online, utc


def heartbeat(registry: Registry, device_id: str, boot_id: str, free_rx: int,
              free_tx: int, active_ids: list[str]) -> dict:
    device = registry.row("SELECT * FROM devices WHERE device_id = ?", (device_id,))
    new_epoch = boot_id != device["boot_id"] or not online(device, registry.now_ms)
    if new_epoch:
        registry.cancel_assignments(device_id=device_id)
    else:
        active = set(active_ids)
        live = registry.rows(
            "SELECT assignment_id, source_device_id FROM assignments "
            "WHERE state IN ('OFFERED', 'RUNNING') AND expires_at_ms > ? "
            "AND (source_device_id = ? OR target_device_id = ?)",
            (registry.now_ms, device_id, device_id),
        )
        for lease in live:
            if lease["assignment_id"] not in active:
                if lease["source_device_id"] == device_id:
                    free_tx -= 1
                else:
                    free_rx -= 1
    registry.db.execute(
        "UPDATE devices SET boot_id = ?, heartbeat_at_ms = ?, "
        "connection_epoch = connection_epoch + ?, rx_free = ?, tx_free = ? WHERE device_id = ?",
        (boot_id, registry.now_ms, new_epoch, max(0, free_rx), max(0, free_tx), device_id),
    )
    return {"server_time": utc(registry.now_ms), "connection": "ONLINE"}


def reconcile(registry: Registry, device_id: str, job_id: str, boot_id: str,
              batch_ids: list[int]) -> dict:
    member = registry.row(
        "SELECT d.*, j.source_device_id, o.state AS consent FROM job_members m "
        "JOIN devices d USING (device_id) JOIN jobs j USING (job_id) "
        "LEFT JOIN offers o ON o.job_id = m.job_id AND o.target_device_id = m.device_id "
        "WHERE m.job_id = ? AND m.device_id = ?", (job_id, device_id),
    )
    if member is None:
        raise RegistryError(404)
    if (
        member["source_device_id"] != device_id
        and member["consent"] not in {"ACCEPTED", "VERIFIED"}
    ):
        raise RegistryError(409)
    if boot_id != member["boot_id"] or not online(member, registry.now_ms):
        raise RegistryError(409)
    batches = registry.rows("SELECT batch_id FROM job_batches WHERE job_id = ?", (job_id,))
    if not set(batch_ids) <= {row["batch_id"] for row in batches}:
        raise RegistryError(409)

    registry.db.execute("DELETE FROM inventory WHERE job_id = ? AND device_id = ?", (job_id, device_id))
    registry.db.executemany(
        "INSERT INTO inventory VALUES (?, ?, ?, ?)",
        ((job_id, device_id, batch_id, registry.now_ms) for batch_id in batch_ids),
    )
    registry.db.execute(
        "UPDATE job_members SET reconciled_epoch = ? WHERE job_id = ? AND device_id = ?",
        (member["connection_epoch"], job_id, device_id),
    )
    registry.db.execute(
        "UPDATE assignments AS a SET state = 'CANCELED', closed_at_ms = max(a.created_at_ms, ?) "
        "WHERE a.job_id = ? AND a.state IN ('OFFERED', 'RUNNING') AND "
        "((a.source_device_id = ? AND NOT EXISTS (SELECT 1 FROM inventory i "
        "WHERE i.job_id = a.job_id AND i.device_id = a.source_device_id AND i.batch_id = a.batch_id)) "
        "OR (a.target_device_id = ? AND EXISTS (SELECT 1 FROM inventory i "
        "WHERE i.job_id = a.job_id AND i.device_id = a.target_device_id AND i.batch_id = a.batch_id)))",
        (registry.now_ms, job_id, device_id, device_id),
    )
    return {"job_id": job_id, "device_id": device_id, "boot_id": boot_id,
            "verified_batch_ids": sorted(batch_ids)}
