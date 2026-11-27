"""After the rows are in: queue what the registry generates for an approved record.

The registry's approval path does this per record (core
intake_form_data_service and g2p_completion_score_service): a register that
requires functional ids gets a G2PFunctionalIdGenerationQueue row and a
TEMP- placeholder id, and a register that requires completion scores gets a
PENDING row per section. The registry's own workers then do the work. These
statements queue the same rows for every migrated record that has none yet,
so running them again queues nothing twice. queue() runs them; the SQL file
(load.SqlFile) carries them after its inserts.
"""
from sqlalchemy import text

from .transform import MIGRATED_BY

_REGISTERS = """
SELECT register_id, register_mnemonic, functional_id_generation_required, completion_score_required
  FROM g2p_register_definitions WHERE register_purpose = 'REGISTER'
"""


def _literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def statements(engine, completion_scores=True) -> list[tuple[str, str]]:
    """(label, SQL) for every register that needs it, with its values written in."""
    import importlib
    models = importlib.import_module("openg2p_registry_extensions.register_domain.models")
    out = []
    by = _literal(MIGRATED_BY)
    with engine.connect() as conn:
        registers = conn.execute(text(_REGISTERS)).all()
    for register_id, mnemonic, ids_required, scores_required in registers:
        cls = getattr(models, f"G2PRegister{mnemonic}", None)
        if cls is None:
            continue
        table, rid = cls.__tablename__, _literal(register_id)
        if ids_required:
            out.append((f"{mnemonic}: functional ids queued", f"""WITH todo AS (
    SELECT r.internal_record_id FROM {table} r
     WHERE r.created_by = {by} AND (r.functional_record_id IS NULL OR r.functional_record_id = '')
       AND NOT EXISTS (SELECT 1 FROM g2p_functional_id_generation_queue q
                        WHERE q.register_id = {rid} AND q.internal_record_id = r.internal_record_id)),
queued AS (
    INSERT INTO g2p_functional_id_generation_queue
           (queue_id, register_id, internal_record_id, id_allocation_status,
            id_allocation_no_of_attempts, id_updation_status, id_updation_no_of_attempts)
    SELECT gen_random_uuid()::text, {rid}, internal_record_id, 'PENDING', 0, 'NOT_APPLICABLE', 0
      FROM todo RETURNING internal_record_id)
UPDATE {table} r SET functional_record_id = 'TEMP-' || replace(gen_random_uuid()::text, '-', '')
  FROM queued WHERE r.internal_record_id = queued.internal_record_id"""))
        if scores_required and completion_scores:
            out.append((f"{mnemonic}: completion scores queued", f"""INSERT INTO g2p_completion_score_computation_queue
       (queue_id, register_id, internal_record_id, section_id, compute_status, compute_number_of_attempts)
SELECT gen_random_uuid()::text, {rid}, r.internal_record_id, s.section_id, 'PENDING', 0
  FROM {table} r
  JOIN g2p_register_sections s ON s.register_id = {rid} AND (s.section_register_id = {rid} OR s.is_list)
 WHERE r.created_by = {by}
   AND NOT EXISTS (SELECT 1 FROM g2p_completion_score_computation_queue q
                    WHERE q.register_id = {rid} AND q.internal_record_id = r.internal_record_id
                      AND q.section_id = s.section_id)"""))
    return out


def requeue_scores(cur, models, gen2_ids) -> int:
    """In the caller's transaction: these records were updated, so their completion scores are
    computed again: a PENDING row per section, unless one is already waiting."""
    ids, n = list(gen2_ids), 0
    if not ids:
        return n
    cur.execute(_REGISTERS + " AND completion_score_required")
    for register_id, mnemonic, _, _ in cur.fetchall():
        cls = getattr(models, f"G2PRegister{mnemonic}", None)
        if cls is None:
            continue
        cur.execute(f"""INSERT INTO g2p_completion_score_computation_queue
       (queue_id, register_id, internal_record_id, section_id, compute_status, compute_number_of_attempts)
SELECT gen_random_uuid()::text, %(rid)s, r.internal_record_id, s.section_id, 'PENDING', 0
  FROM {cls.__tablename__} r
  JOIN g2p_register_sections s ON s.register_id = %(rid)s AND (s.section_register_id = %(rid)s OR s.is_list)
 WHERE r.internal_record_id = ANY(%(ids)s)
   AND NOT EXISTS (SELECT 1 FROM g2p_completion_score_computation_queue q
                    WHERE q.register_id = %(rid)s AND q.internal_record_id = r.internal_record_id
                      AND q.section_id = s.section_id AND q.compute_status = 'PENDING')""", {"rid": register_id, "ids": ids})
        n += cur.rowcount
    return n


def queue(engine, log, completion_scores=True, before=None) -> dict:
    """before(cur) runs first in the transaction."""
    counts = {}
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        if before:
            before(cur)
        for label, sql in statements(engine, completion_scores):
            cur.execute(sql)
            counts[label] = cur.rowcount
            log.info("%s: %d", label, cur.rowcount)
        raw.commit()
    finally:
        raw.close()
    return counts
