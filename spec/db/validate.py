"""Executable SQLite schema examples. No external Python dependencies."""

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


HERE = Path(__file__).resolve().parent
DATA = b"a"
DIGEST = sha256(DATA).digest()
PART = {"index": 0, "offset": 0, "size": len(DATA), "sha256": DIGEST.hex()}
MANIFEST = json.dumps(
    {
        "version": 1, "name": "fixture.bin", "size": len(DATA),
        "piece_size": 1, "batch_size": 1, "sha256": DIGEST.hex(),
        "pieces": [PART], "batches": [PART],
    },
    sort_keys=True, separators=(",", ":"),
).encode("utf-8")
MANIFEST_HASH = sha256(MANIFEST).digest()


def uid():
    return str(uuid4())


def open_schema(name):
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.executescript((HERE / name).read_text(encoding="utf-8"))
    assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert conn.execute("PRAGMA synchronous").fetchone() == (2,)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    return conn


def rejected(conn, error_name, sql, args=()):
    try:
        conn.execute(sql, args)
    except sqlite3.IntegrityError as exc:
        assert exc.sqlite_errorname == error_name, exc
    else:
        raise AssertionError(f"Expected {error_name} for {sql}")


def controller(conn):
    source, target, pair, job, offer = (uid() for _ in range(5))
    for device in (source, target):
        conn.execute(
            "INSERT INTO devices(device_id, display_name, token_sha256, enrolled_at_ms) VALUES (?, ?, ?, 0)",
            (device, device, sha256(device.encode()).digest()),
        )
    pair_sql = """
        INSERT INTO pairs(pair_id, opener_device_id, claimant_device_id, code_sha256,
                          comparison_code, opener_confirmed_at_ms, claimant_confirmed_at_ms,
                          created_at_ms, expires_at_ms, state)
        VALUES (?, ?, ?, ?, '012345', 1, 1, 0, 20, 'ACTIVE')
    """
    conn.execute(pair_sql, (pair, source, target, DIGEST))
    rejected(conn, "SQLITE_CONSTRAINT_UNIQUE", pair_sql,
             (uid(), target, source, sha256(b"different code").digest()))
    conn.execute(
        """INSERT INTO jobs(job_id, source_device_id, manifest_canonical, manifest_sha256,
                            file_sha256, size_bytes, created_at_ms, state)
           VALUES (?, ?, ?, ?, ?, 1, 0, 'OPEN')""",
        (job, source, MANIFEST, MANIFEST_HASH, DIGEST),
    )
    conn.execute("INSERT INTO job_batches VALUES (?, 0, 0, 1, ?)", (job, DIGEST))
    conn.execute("INSERT INTO offers VALUES (?, ?, ?, ?, 20, 1, 0, 'ACCEPTED')",
                 (offer, job, target, pair))
    conn.executemany("INSERT INTO job_members VALUES (?, ?, 0)", [(job, source), (job, target)])
    rejected(conn, "SQLITE_CONSTRAINT_FOREIGNKEY", "INSERT INTO inventory VALUES (?, ?, 99, 2)", (job, target))
    conn.execute("INSERT INTO inventory VALUES (?, ?, 0, 2)", (job, source))

    first, replacement = uid(), uid()
    assignment_sql = """
        INSERT INTO assignments(assignment_id, job_id, batch_id, source_device_id, target_device_id,
                                source_epoch, target_epoch, relay_profile, created_at_ms, expires_at_ms, state)
        VALUES (?, ?, 0, ?, ?, 0, 0, 'demo-lan', ?, ?, 'OFFERED')
    """
    conn.execute(assignment_sql, (first, job, source, target, 2, 30))
    rejected(conn, "SQLITE_CONSTRAINT_UNIQUE", assignment_sql, (replacement, job, source, target, 29, 50))
    conn.execute("BEGIN IMMEDIATE")
    expired = conn.execute(
        """UPDATE assignments SET state='EXPIRED', closed_at_ms=?
           WHERE assignment_id=? AND state IN ('OFFERED','RUNNING') AND expires_at_ms <= ?""",
        (30, first, 30),
    )
    assert expired.rowcount == 1
    conn.execute(assignment_sql, (replacement, job, source, target, 30, 60))
    conn.execute("COMMIT")
    assert conn.execute("SELECT state FROM assignments WHERE assignment_id=?", (first,)).fetchone() == ("EXPIRED",)

    # A late ACK credits inventory once without touching the replacement lease.
    def apply_ack():
        conn.execute("BEGIN IMMEDIATE")
        processed = conn.execute(
            "UPDATE assignments SET ack_processed_at_ms=31 WHERE assignment_id=? AND ack_processed_at_ms IS NULL",
            (first,),
        )
        if processed.rowcount:
            conn.execute("INSERT INTO inventory VALUES (?, ?, 0, 31)", (job, target))
        conn.execute("COMMIT")

    apply_ack()
    assert conn.execute("SELECT state FROM assignments WHERE assignment_id=?", (replacement,)).fetchone() == ("OFFERED",)
    conn.execute("DELETE FROM inventory WHERE job_id=? AND device_id=?", (job, target))
    apply_ack()
    assert conn.execute("SELECT COUNT(*) FROM inventory WHERE device_id=?", (target,)).fetchone() == (0,)

    conn.execute("INSERT INTO inventory VALUES (?, ?, 0, 32)", (job, target))
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO receipts VALUES (?, ?, 33)", (job, target))
    conn.execute("UPDATE offers SET state='VERIFIED' WHERE offer_id=?", (offer,))
    conn.execute("UPDATE assignments SET state='CANCELED', closed_at_ms=33 WHERE assignment_id=?", (replacement,))
    conn.execute("UPDATE jobs SET state='COMPLETE', closed_at_ms=33 WHERE job_id=?", (job,))
    conn.execute("COMMIT")
    rejected(conn, "SQLITE_CONSTRAINT_PRIMARYKEY", "INSERT INTO receipts VALUES (?, ?, 34)", (job, target))
    assert conn.execute("SELECT verified_at_ms FROM receipts").fetchall() == [(33,)]


def node(conn):
    job, attempt, boot = uid(), uid(), uid()
    conn.execute(
        """INSERT INTO local_jobs(job_id, role, source_device_id, offer_id, manifest_canonical,
                                  manifest_sha256, private_job_path, consent, consent_request_key, created_at_ms)
           VALUES (?, 'TARGET', ?, ?, ?, ?, ?, 'ACCEPT', ?, 1)""",
        (job, uid(), uid(), MANIFEST, MANIFEST_HASH, f"jobs/{job}", uid()),
    )
    conn.execute("INSERT INTO delivery(job_id, intended_path, state) VALUES (?, 'final.bin', 'PLANNED')", (job,))
    conn.execute("INSERT INTO local_batches VALUES (?, 0, NULL, 1, 'MISSING')", (job,))
    conn.execute("INSERT INTO local_attempts VALUES (?, ?, 0, ?, 'RX', 'rx', 1, NULL, 'VERIFIED')", (attempt, job, boot))
    ack_sql = """
        INSERT INTO outbox(request_key, job_id, event_kind, batch_id, assignment_id,
                           payload_json, created_at_ms, next_attempt_at_ms)
        VALUES (?, ?, 'ACK', ?, ?, ?, 2, 2)
    """
    ack_key, ack_json = uid(), json.dumps({"sha256": DIGEST.hex()})
    rejected(conn, "SQLITE_CONSTRAINT_FOREIGNKEY", ack_sql, (uid(), job, 99, attempt, ack_json))

    def commit_batch(commit):
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE local_batches SET state='AVAILABLE', storage_path='batch/0' WHERE job_id=?", (job,))
        conn.execute("UPDATE local_attempts SET state='FINISHED', closed_at_ms=2 WHERE assignment_id=?", (attempt,))
        conn.execute(ack_sql, (ack_key, job, 0, attempt, ack_json))
        conn.execute("COMMIT" if commit else "ROLLBACK")

    commit_batch(False)
    assert conn.execute("SELECT state FROM local_batches").fetchall() == [("MISSING",)]
    assert conn.execute("SELECT * FROM outbox").fetchall() == []
    commit_batch(True)
    rejected(conn, "SQLITE_CONSTRAINT_UNIQUE", ack_sql, (uid(), job, 0, attempt, ack_json))

    reconcile_key, receipt_key = uid(), uid()
    conn.execute(
        """INSERT INTO outbox(request_key, job_id, event_kind, boot_id, payload_json, created_at_ms, next_attempt_at_ms)
           VALUES (?, ?, 'RECONCILE', ?, ?, 3, 3)""",
        (reconcile_key, job, boot, json.dumps({"boot_id": boot, "verified_batch_ids": [0]})),
    )
    receipt_sql = """
        INSERT INTO outbox(request_key, job_id, event_kind, payload_json, created_at_ms, next_attempt_at_ms)
        VALUES (?, ?, 'RECEIPT', ?, 4, 4)
    """
    receipt_json = json.dumps({"manifest_sha256": MANIFEST_HASH.hex(), "file_sha256": DIGEST.hex(), "size": 1})
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE delivery SET state='PUBLISHED', published_at_ms=4 WHERE job_id=?", (job,))
    conn.execute(receipt_sql, (receipt_key, job, receipt_json))
    conn.execute("COMMIT")
    rejected(conn, "SQLITE_CONSTRAINT_UNIQUE", receipt_sql, (uid(), job, receipt_json))
    conn.execute(
        "UPDATE outbox SET first_sent_at_ms=4, attempt_count=1, next_attempt_at_ms=5 WHERE request_key=?",
        (reconcile_key,),
    )
    result = conn.execute(
        """SELECT request_key FROM outbox WHERE job_id=?
           ORDER BY (event_kind='RECONCILE' AND boot_id=?) DESC, event_id""",
        (job, boot),
    ).fetchall()
    assert result == [(reconcile_key,), (ack_key,), (receipt_key,)]
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE local_batches SET state='CORRUPT' WHERE job_id=? AND batch_id=0", (job,))
    conn.execute("DELETE FROM outbox WHERE job_id=? AND batch_id=0 AND event_kind='ACK' AND first_sent_at_ms IS NULL", (job,))
    conn.execute("COMMIT")
    assert conn.execute("SELECT COUNT(*) FROM outbox WHERE event_kind='ACK'").fetchone() == (0,)


if __name__ == "__main__":
    with closing(open_schema("controller.sql")) as db:
        controller(db)
    with closing(open_schema("node.sql")) as db:
        node(db)
    print(f"Controller and Node schema checks passed (SQLite {sqlite3.sqlite_version}).")
