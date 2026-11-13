"""After the rows are in: queue what the registry generates for an approved record.

The registry's approval path does this per record (core
intake_form_data_service and g2p_completion_score_service): a register that
requires functional ids gets a G2PFunctionalIdGenerationQueue row and a
TEMP- placeholder id, and a register that requires completion scores gets a
PENDING row per section. The registry's own workers then do the work. This
queues the same rows, in SQL, for every migrated record that has none yet, so
running it again queues nothing twice.
"""
from sqlalchemy import text

from .transform import MIGRATED_BY

_REGISTERS = """
SELECT register_id, register_mnemonic, functional_id_generation_required, completion_score_required
  FROM g2p_register_definitions WHERE register_purpose = 'REGISTER'
"""


def queue(engine, log, completion_scores=True) -> dict:
    import importlib
    models = importlib.import_module("openg2p_registry_extensions.register_domain.models")
    counts = {}
    with engine.begin() as conn:
        for register_id, mnemonic, ids_required, scores_required in conn.execute(text(_REGISTERS)).all():
            cls = getattr(models, f"G2PRegister{mnemonic}", None)
            if cls is None:
                continue
            table = cls.__tablename__
            if ids_required:
                n = conn.execute(text(f"""
                    WITH todo AS (
                        SELECT r.internal_record_id FROM {table} r
                         WHERE r.created_by = :by AND (r.functional_record_id IS NULL OR r.functional_record_id = '')
                           AND NOT EXISTS (SELECT 1 FROM g2p_functional_id_generation_queue q
                                            WHERE q.register_id = :rid AND q.internal_record_id = r.internal_record_id)),
                    queued AS (
                        INSERT INTO g2p_functional_id_generation_queue
                               (queue_id, register_id, internal_record_id, id_allocation_status,
                                id_allocation_no_of_attempts, id_updation_status, id_updation_no_of_attempts)
                        SELECT gen_random_uuid()::text, :rid, internal_record_id, 'PENDING', 0, 'NOT_APPLICABLE', 0
                          FROM todo RETURNING internal_record_id)
                    UPDATE {table} r SET functional_record_id = 'TEMP-' || replace(gen_random_uuid()::text, '-', '')
                      FROM queued WHERE r.internal_record_id = queued.internal_record_id"""),
                                 {"by": MIGRATED_BY, "rid": register_id}).rowcount
                counts[f"{mnemonic}: functional ids queued"] = n
                log.info("%s: %d records queued for a functional id", mnemonic, n)
            if scores_required and completion_scores:
                n = conn.execute(text(f"""
                    INSERT INTO g2p_completion_score_computation_queue
                           (queue_id, register_id, internal_record_id, section_id, compute_status, compute_number_of_attempts)
                    SELECT gen_random_uuid()::text, :rid, r.internal_record_id, s.section_id, 'PENDING', 0
                      FROM {table} r
                      JOIN g2p_register_sections s ON s.register_id = :rid
                                                  AND (s.section_register_id = :rid OR s.is_list)
                     WHERE r.created_by = :by
                       AND NOT EXISTS (SELECT 1 FROM g2p_completion_score_computation_queue q
                                        WHERE q.register_id = :rid AND q.internal_record_id = r.internal_record_id
                                          AND q.section_id = s.section_id)"""),
                                 {"by": MIGRATED_BY, "rid": register_id}).rowcount
                counts[f"{mnemonic}: completion scores queued"] = n
                log.info("%s: %d completion-score computations queued", mnemonic, n)
    return counts
