-- Bootstrap SQLite >= 3.38. Apply these connection settings before BEGIN.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;

BEGIN IMMEDIATE;

CREATE TABLE local_jobs (
    job_id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('SOURCE','TARGET')),
    source_device_id TEXT NOT NULL,
    offer_id TEXT UNIQUE,
    manifest_canonical BLOB NOT NULL CHECK (length(manifest_canonical) > 0),
    manifest_sha256 BLOB NOT NULL CHECK (length(manifest_sha256) = 32),
    private_job_path TEXT NOT NULL CHECK (length(private_job_path) > 0),
    source_snapshot_path TEXT,
    consent TEXT CHECK (consent IN ('ACCEPT','DECLINE','WITHDRAW')),
    consent_request_key TEXT UNIQUE,
    allow_forward INTEGER NOT NULL DEFAULT 0 CHECK (allow_forward IN (0,1)),
    created_at_ms INTEGER NOT NULL,
    closed_at_ms INTEGER CHECK (closed_at_ms >= created_at_ms),
    CHECK (role <> 'SOURCE' OR (source_snapshot_path IS NOT NULL AND offer_id IS NULL AND consent IS NULL)),
    CHECK (role <> 'TARGET' OR (source_snapshot_path IS NULL AND offer_id IS NOT NULL)),
    CHECK ((consent IS NULL) = (consent_request_key IS NULL)),
    CHECK (allow_forward = 0 OR (role = 'TARGET' AND consent IS 'ACCEPT'))
) STRICT;

CREATE TABLE local_batches (
    job_id TEXT NOT NULL REFERENCES local_jobs(job_id),
    batch_id INTEGER NOT NULL CHECK (batch_id >= 0),
    storage_path TEXT,
    updated_at_ms INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('MISSING','AVAILABLE','CORRUPT')),
    CHECK (state <> 'AVAILABLE' OR storage_path IS NOT NULL),
    PRIMARY KEY (job_id, batch_id)
) STRICT;

CREATE TABLE local_attempts (
    assignment_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    batch_id INTEGER NOT NULL,
    boot_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('TX','RX')),
    staging_path TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    closed_at_ms INTEGER CHECK (closed_at_ms >= created_at_ms),
    state TEXT NOT NULL CHECK (state IN ('ASSIGNED','TRANSFERRING','RECEIVED','VERIFIED','FINISHED','FAILED','CANCELED')),
    CHECK ((state IN ('FINISHED','FAILED','CANCELED')) = (closed_at_ms IS NOT NULL)),
    FOREIGN KEY (job_id, batch_id) REFERENCES local_batches(job_id, batch_id),
    UNIQUE (assignment_id, job_id, batch_id)
) STRICT;

CREATE TABLE delivery (
    job_id TEXT PRIMARY KEY REFERENCES local_jobs(job_id),
    intended_path TEXT NOT NULL CHECK (length(intended_path) > 0),
    published_at_ms INTEGER,
    state TEXT NOT NULL CHECK (state IN ('PLANNED','PUBLISHING','PATH_CONFLICT','PUBLISHED')),
    CHECK ((state = 'PUBLISHED') = (published_at_ms IS NOT NULL))
) STRICT;

CREATE TABLE outbox (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_key TEXT NOT NULL UNIQUE,
    job_id TEXT NOT NULL REFERENCES local_jobs(job_id),
    event_kind TEXT NOT NULL CHECK (event_kind IN ('ACK','RECONCILE','RECEIPT')),
    batch_id INTEGER,
    assignment_id TEXT,
    boot_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at_ms INTEGER NOT NULL,
    next_attempt_at_ms INTEGER NOT NULL CHECK (next_attempt_at_ms >= created_at_ms),
    first_sent_at_ms INTEGER CHECK (first_sent_at_ms >= created_at_ms),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    sent_boot_id TEXT CHECK (sent_boot_id IS NULL OR first_sent_at_ms IS NOT NULL),
    CHECK ((event_kind = 'ACK') = (batch_id IS NOT NULL)),
    CHECK ((event_kind = 'ACK') = (assignment_id IS NOT NULL)),
    CHECK ((event_kind = 'RECONCILE') = (boot_id IS NOT NULL)),
    FOREIGN KEY (assignment_id, job_id, batch_id) REFERENCES local_attempts(assignment_id, job_id, batch_id)
) STRICT;

CREATE INDEX outbox_job_order ON outbox(job_id, event_id);
CREATE UNIQUE INDEX outbox_one_receipt ON outbox(job_id) WHERE event_kind = 'RECEIPT';
CREATE UNIQUE INDEX outbox_one_ack ON outbox(assignment_id) WHERE event_kind = 'ACK';

COMMIT;
