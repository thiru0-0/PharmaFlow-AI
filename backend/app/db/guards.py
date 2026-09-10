"""Database-level enforcement of the batch lifecycle and the certificate gate.

These run *in addition to* the service-layer checks so a direct SQL/API write cannot
skip a state or attach an orphan certificate. Dialect-specific (SQLite + PostgreSQL).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_LEGAL = """
    (OLD.state = 'ACTIVE' AND NEW.state IN ('ACTIVE','RETURN_INITIATED'))
 OR (OLD.state = 'RETURN_INITIATED' AND NEW.state IN ('RETURN_INITIATED','PICKUP_SCHEDULED'))
 OR (OLD.state = 'PICKUP_SCHEDULED' AND NEW.state IN ('PICKUP_SCHEDULED','DISPUTED','PICKUP_CONFIRMED'))
 OR (OLD.state = 'DISPUTED' AND NEW.state IN ('DISPUTED','PICKUP_CONFIRMED'))
 OR (OLD.state = 'PICKUP_CONFIRMED' AND NEW.state IN ('PICKUP_CONFIRMED','RECEIVED_BY_MANUFACTURER'))
 OR (OLD.state = 'RECEIVED_BY_MANUFACTURER' AND NEW.state IN ('RECEIVED_BY_MANUFACTURER','DESTROYED_CERTIFIED'))
 OR (OLD.state = 'DESTROYED_CERTIFIED' AND NEW.state = 'DESTROYED_CERTIFIED')
"""

_SQLITE = [
    "DROP TRIGGER IF EXISTS trg_batch_state_guard",
    f"""
    CREATE TRIGGER trg_batch_state_guard
    BEFORE UPDATE OF state ON batches FOR EACH ROW
    WHEN NOT ({_LEGAL})
    BEGIN
        SELECT RAISE(ABORT, 'illegal batch state transition (db guard)');
    END;
    """,
    "DROP TRIGGER IF EXISTS trg_cert_gate",
    """
    CREATE TRIGGER trg_cert_gate
    BEFORE INSERT ON destruction_certificates FOR EACH ROW
    WHEN (
        (SELECT COUNT(*) FROM manufacturer_receipts r WHERE r.batch_id = NEW.batch_id) = 0
        OR (SELECT state FROM batches b WHERE b.id = NEW.batch_id) <> 'RECEIVED_BY_MANUFACTURER'
    )
    BEGIN
        SELECT RAISE(ABORT, 'certificate gate: no confirmed receipt / batch not RECEIVED_BY_MANUFACTURER');
    END;
    """,
]

_PG = [
    """
    CREATE OR REPLACE FUNCTION pf_batch_state_guard() RETURNS trigger AS $$
    BEGIN
        IF NEW.state = OLD.state THEN RETURN NEW; END IF;
        IF NOT (
    """
    + _LEGAL
    + """
        ) THEN
            RAISE EXCEPTION 'illegal batch state transition % -> % (db guard)', OLD.state, NEW.state;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "DROP TRIGGER IF EXISTS trg_batch_state_guard ON batches",
    """
    CREATE TRIGGER trg_batch_state_guard BEFORE UPDATE ON batches
    FOR EACH ROW EXECUTE FUNCTION pf_batch_state_guard();
    """,
    """
    CREATE OR REPLACE FUNCTION pf_cert_gate() RETURNS trigger AS $$
    DECLARE n int; st text;
    BEGIN
        SELECT COUNT(*) INTO n FROM manufacturer_receipts r WHERE r.batch_id = NEW.batch_id;
        SELECT state INTO st FROM batches b WHERE b.id = NEW.batch_id;
        IF n = 0 OR st <> 'RECEIVED_BY_MANUFACTURER' THEN
            RAISE EXCEPTION 'certificate gate: no confirmed receipt / batch not RECEIVED_BY_MANUFACTURER';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "DROP TRIGGER IF EXISTS trg_cert_gate ON destruction_certificates",
    """
    CREATE TRIGGER trg_cert_gate BEFORE INSERT ON destruction_certificates
    FOR EACH ROW EXECUTE FUNCTION pf_cert_gate();
    """,
]


def install_guards(engine: Engine) -> None:
    stmts = _SQLITE if engine.dialect.name == "sqlite" else _PG
    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))
