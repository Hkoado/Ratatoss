-- Bootstrap SQLite >= 3.38. Apply these connection settings before BEGIN.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;

BEGIN IMMEDIATE;

CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL CHECK (length(display_name) > 0),
    token_sha256 BLOB NOT NULL UNIQUE CHECK (length(token_sha256) = 32),
    enrolled_at_ms INTEGER NOT NULL,
    revoked_at_ms INTEGER CHECK (revoked_at_ms >= enrolled_at_ms),
    boot_id TEXT,
    heartbeat_at_ms INTEGER,
    connection_epoch INTEGER NOT NULL DEFAULT 0 CHECK (connection_epoch >= 0),
    rx_free INTEGER NOT NULL DEFAULT 0 CHECK (rx_free >= 0),
    tx_free INTEGER NOT NULL DEFAULT 0 CHECK (tx_free >= 0),
    CHECK ((boot_id IS NULL) = (heartbeat_at_ms IS NULL))
) STRICT;

CREATE TABLE enrollments (
    code_sha256 BLOB PRIMARY KEY CHECK (length(code_sha256) = 32),
    issued_at_ms INTEGER NOT NULL,
    expires_at_ms INTEGER NOT NULL CHECK (expires_at_ms > issued_at_ms),
    consumed_at_ms INTEGER,
    device_id TEXT UNIQUE REFERENCES devices(device_id),
    CHECK ((consumed_at_ms IS NULL) = (device_id IS NULL)),
    CHECK (consumed_at_ms >= issued_at_ms AND consumed_at_ms < expires_at_ms)
) STRICT;

CREATE TABLE pairs (
    pair_id TEXT PRIMARY KEY,
    opener_device_id TEXT NOT NULL REFERENCES devices(device_id),
    claimant_device_id TEXT REFERENCES devices(device_id),
    device_low TEXT GENERATED ALWAYS AS (min(opener_device_id, claimant_device_id)) VIRTUAL,
    device_high TEXT GENERATED ALWAYS AS (max(opener_device_id, claimant_device_id)) VIRTUAL,
    code_sha256 BLOB NOT NULL UNIQUE CHECK (length(code_sha256) = 32),
    comparison_code TEXT CHECK (length(comparison_code) = 6 AND comparison_code NOT GLOB '*[^0-9]*'),
    opener_confirmed_at_ms INTEGER,
    claimant_confirmed_at_ms INTEGER,
    created_at_ms INTEGER NOT NULL,
    expires_at_ms INTEGER NOT NULL CHECK (expires_at_ms > created_at_ms),
    state TEXT NOT NULL CHECK (state IN ('OPEN','CLAIMED','ACTIVE','DECLINED','EXPIRED','REVOKED')),
    CHECK (opener_device_id <> claimant_device_id),
    CHECK ((claimant_device_id IS NULL) = (comparison_code IS NULL)),
    CHECK (state <> 'OPEN' OR claimant_device_id IS NULL),
    CHECK (state NOT IN ('CLAIMED','ACTIVE','DECLINED','REVOKED') OR claimant_device_id IS NOT NULL),
    CHECK (state <> 'ACTIVE' OR (opener_confirmed_at_ms IS NOT NULL AND claimant_confirmed_at_ms IS NOT NULL)),
    CHECK (opener_confirmed_at_ms >= created_at_ms AND opener_confirmed_at_ms < expires_at_ms),
    CHECK (claimant_confirmed_at_ms >= created_at_ms AND claimant_confirmed_at_ms < expires_at_ms)
) STRICT;

CREATE UNIQUE INDEX pairs_one_active ON pairs(device_low, device_high) WHERE state = 'ACTIVE';

CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    source_device_id TEXT NOT NULL REFERENCES devices(device_id),
    manifest_canonical BLOB NOT NULL CHECK (length(manifest_canonical) > 0),
    manifest_sha256 BLOB NOT NULL CHECK (length(manifest_sha256) = 32),
    file_sha256 BLOB NOT NULL CHECK (length(file_sha256) = 32),
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    created_at_ms INTEGER NOT NULL,
    closed_at_ms INTEGER CHECK (closed_at_ms >= created_at_ms),
    state TEXT NOT NULL CHECK (state IN ('OPEN','COMPLETE','PARTIAL','NO_DELIVERY','CANCELED')),
    CHECK ((state = 'OPEN') = (closed_at_ms IS NULL))
) STRICT;

CREATE TABLE job_batches (
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    batch_id INTEGER NOT NULL CHECK (batch_id >= 0),
    offset_bytes INTEGER NOT NULL CHECK (offset_bytes >= 0),
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    sha256 BLOB NOT NULL CHECK (length(sha256) = 32),
    PRIMARY KEY (job_id, batch_id),
    UNIQUE (job_id, offset_bytes)
) STRICT;

CREATE TABLE offers (
    offer_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    target_device_id TEXT NOT NULL REFERENCES devices(device_id),
    pair_id TEXT NOT NULL REFERENCES pairs(pair_id),
    expires_at_ms INTEGER NOT NULL,
    accepted_at_ms INTEGER CHECK (accepted_at_ms < expires_at_ms),
    allow_forward INTEGER NOT NULL DEFAULT 0 CHECK (allow_forward IN (0,1)),
    state TEXT NOT NULL CHECK (state IN ('PENDING','ACCEPTED','DECLINED','EXPIRED','REVOKED','WITHDRAWN','VERIFIED','CANCELED')),
    CHECK ((state IN ('ACCEPTED','WITHDRAWN','VERIFIED','CANCELED')) = (accepted_at_ms IS NOT NULL)),
    CHECK (allow_forward = 0 OR accepted_at_ms IS NOT NULL),
    UNIQUE (job_id, target_device_id)
) STRICT;

CREATE INDEX offers_target ON offers(target_device_id, state);

CREATE TABLE job_members (
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    reconciled_epoch INTEGER CHECK (reconciled_epoch >= 0),
    PRIMARY KEY (job_id, device_id)
) STRICT;

CREATE TABLE inventory (
    job_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    batch_id INTEGER NOT NULL,
    verified_at_ms INTEGER NOT NULL,
    PRIMARY KEY (job_id, device_id, batch_id),
    FOREIGN KEY (job_id, device_id) REFERENCES job_members(job_id, device_id),
    FOREIGN KEY (job_id, batch_id) REFERENCES job_batches(job_id, batch_id)
) STRICT;

CREATE TABLE assignments (
    assignment_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    batch_id INTEGER NOT NULL,
    source_device_id TEXT NOT NULL,
    target_device_id TEXT NOT NULL,
    source_epoch INTEGER NOT NULL CHECK (source_epoch >= 0),
    target_epoch INTEGER NOT NULL CHECK (target_epoch >= 0),
    relay_profile TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    expires_at_ms INTEGER NOT NULL CHECK (expires_at_ms > created_at_ms),
    closed_at_ms INTEGER CHECK (closed_at_ms >= created_at_ms),
    ack_processed_at_ms INTEGER CHECK (ack_processed_at_ms >= created_at_ms),
    state TEXT NOT NULL CHECK (state IN ('OFFERED','RUNNING','ACKED','FAILED','EXPIRED','CANCELED')),
    CHECK (source_device_id <> target_device_id),
    CHECK ((state IN ('OFFERED','RUNNING')) = (closed_at_ms IS NULL)),
    CHECK (state <> 'ACKED' OR ack_processed_at_ms IS NOT NULL),
    FOREIGN KEY (job_id, batch_id) REFERENCES job_batches(job_id, batch_id),
    FOREIGN KEY (job_id, source_device_id) REFERENCES job_members(job_id, device_id),
    FOREIGN KEY (job_id, target_device_id) REFERENCES job_members(job_id, device_id),
    FOREIGN KEY (job_id, target_device_id) REFERENCES offers(job_id, target_device_id)
) STRICT;

CREATE UNIQUE INDEX assignments_one_live ON assignments(job_id, target_device_id, batch_id)
    WHERE state IN ('OFFERED','RUNNING');
CREATE INDEX assignments_live_source ON assignments(source_device_id, expires_at_ms)
    WHERE state IN ('OFFERED','RUNNING');
CREATE INDEX assignments_live_target ON assignments(target_device_id, expires_at_ms)
    WHERE state IN ('OFFERED','RUNNING');

CREATE TABLE receipts (
    job_id TEXT NOT NULL,
    target_device_id TEXT NOT NULL,
    verified_at_ms INTEGER NOT NULL,
    PRIMARY KEY (job_id, target_device_id),
    FOREIGN KEY (job_id, target_device_id) REFERENCES offers(job_id, target_device_id)
) STRICT;

CREATE TABLE idempotency (
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    method TEXT NOT NULL,
    route TEXT NOT NULL,
    request_key TEXT NOT NULL,
    payload_sha256 BLOB NOT NULL CHECK (length(payload_sha256) = 32),
    job_id TEXT REFERENCES jobs(job_id),
    pair_id TEXT REFERENCES pairs(pair_id),
    status_code INTEGER NOT NULL CHECK (status_code BETWEEN 200 AND 599),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY (device_id, method, route, request_key),
    CHECK (job_id IS NULL OR pair_id IS NULL)
) STRICT;

CREATE TABLE audit (
    event_id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    batch_id INTEGER,
    source_device_id TEXT REFERENCES devices(device_id),
    target_device_id TEXT REFERENCES devices(device_id),
    assignment_id TEXT REFERENCES assignments(assignment_id),
    result_code TEXT NOT NULL,
    occurred_at_ms INTEGER NOT NULL,
    FOREIGN KEY (job_id, batch_id) REFERENCES job_batches(job_id, batch_id)
) STRICT;

COMMIT;
