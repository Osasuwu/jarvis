#!/usr/bin/env python3
"""Advance global task sources — tick due rows into events queue.

Intended to run every 5 min via Task Scheduler (Workshop only).

Idempotent single-transaction advancer:
- SELECT due rows WHERE enabled AND (next_run IS NULL OR next_run <= now()) FOR UPDATE SKIP LOCKED
- INSERT events rows (dedup on sha256('global_task:'||id||':'||EXTRACT(EPOCH FROM next_run)))
- UPDATE last_run, next_run, enabled
- Handles both coalesce (one event per due row) and fire_per_interval (bounded to 24/row)

Requires DATABASE_URL env var pointing to Supabase postgres://...
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any

import psycopg

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def digest_sha256(data: str) -> str:
    """SHA256 hex digest of a string (matching postgres digest(..., 'hex'))."""
    return hashlib.sha256(data.encode()).hexdigest()


def compute_dedup_key(source_id: str, next_run_epoch: float) -> str:
    """Compute dedup_key = sha256('global_task:'||source_id||':'||EXTRACT(EPOCH FROM next_run)).

    Args:
        source_id: UUID string
        next_run_epoch: seconds since epoch (full timestamp, NOT hour-truncated)

    Returns:
        Hex digest
    """
    data = f"global_task:{source_id}:{int(next_run_epoch)}"
    return digest_sha256(data)


def advance_global_tasks(db_url: str | None = None) -> int:
    """Advance due global task sources to events queue.

    Returns:
        Total event rows inserted.
    """
    if not db_url:
        db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL env var not set")
        return 0

    try:
        conn = psycopg.connect(db_url)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return 0

    total_events = 0

    try:
        with conn.cursor() as cur:
            # Begin transaction
            cur.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")

            # 1. Fetch due rows FOR UPDATE SKIP LOCKED
            logger.info("Fetching due global_task_sources...")
            cur.execute("""
                SELECT
                    id, title, dispatcher_skill, output_sink, payload,
                    cadence, last_run, next_run, on_lapse
                FROM global_task_sources
                WHERE enabled = true
                  AND (next_run IS NULL OR next_run <= now())
                FOR UPDATE SKIP LOCKED
                ORDER BY created_at ASC
            """)
            due_rows = cur.fetchall()
            logger.info(f"Found {len(due_rows)} due rows")

            col_names = [d[0] for d in cur.description]
            col_index = {name: i for i, name in enumerate(col_names)}

            # 2. Process each row
            for row in due_rows:
                source_id = str(row[col_index["id"]])
                title = row[col_index["title"]]
                dispatcher_skill = row[col_index["dispatcher_skill"]]
                output_sink = row[col_index["output_sink"]]
                payload = row[col_index["payload"]] or {}
                cadence = row[col_index["cadence"]]
                next_run = row[col_index["next_run"]]
                on_lapse = row[col_index["on_lapse"]]

                # Compute next_run epoch for dedup
                now = datetime.now()
                if next_run is None:
                    next_run_epoch = now.timestamp()
                else:
                    next_run_epoch = next_run.timestamp()

                if on_lapse == "coalesce":
                    # One event per due row, lapse_intervals = missed-interval count
                    if next_run is None:
                        lapse_intervals = 1  # first run
                    else:
                        # Count missed intervals: FLOOR((now - next_run) / cadence) + 1
                        if cadence:
                            # cadence is a PostgreSQL interval; convert to seconds
                            # For simplicity in Python, assume cadence is reasonable
                            # (minutes/hours/days). Fetch the actual delta from DB.
                            cur.execute("""
                                SELECT EXTRACT(EPOCH FROM (now() - %s::timestamptz)) /
                                       EXTRACT(EPOCH FROM %s::interval) as intervals_missed
                            """, (next_run, cadence))
                            (intervals_missed,) = cur.fetchone()
                            lapse_intervals = max(1, int(intervals_missed) + 1)
                        else:
                            lapse_intervals = 1

                    dedup_key = compute_dedup_key(source_id, next_run_epoch)

                    # INSERT event with ON CONFLICT DO NOTHING
                    event_payload = {
                        "source_id": source_id,
                        "dispatcher_skill": dispatcher_skill,
                        "output_sink": output_sink,
                        "payload": payload,
                        "lapse_intervals": lapse_intervals,
                    }
                    logger.info(
                        f"Inserting event for {source_id} "
                        f"(lapse_intervals={lapse_intervals}, dedup_key={dedup_key[:8]}...)"
                    )
                    cur.execute("""
                        INSERT INTO events (
                            event_type, severity, repo, source, title, payload, dedup_key
                        ) VALUES (
                            'global_task_due', 'low', '_global', 'global_task_advancer',
                            %s, %s::jsonb, %s
                        )
                        ON CONFLICT (dedup_key) DO NOTHING
                    """, (title, json.dumps(event_payload), dedup_key))
                    total_events += 1

                elif on_lapse == "fire_per_interval":
                    # Fire up to 24 times for missed intervals
                    if next_run is None:
                        # First run, fire once
                        fire_count = 1
                    else:
                        if cadence:
                            cur.execute("""
                                SELECT EXTRACT(EPOCH FROM (now() - %s::timestamptz)) /
                                       EXTRACT(EPOCH FROM %s::interval) as intervals_missed
                            """, (next_run, cadence))
                            (intervals_missed,) = cur.fetchone()
                            fire_count = min(24, max(1, int(intervals_missed) + 1))
                        else:
                            fire_count = 1

                    logger.info(
                        f"Fire-per-interval for {source_id}: firing {fire_count} times "
                        f"(capped at 24)"
                    )

                    if fire_count >= 24 and (next_run is not None):
                        logger.warning(
                            f"fire_per_interval cap reached for {source_id} "
                            f"({fire_count} fires); advancing next_run to now"
                        )

                    for i in range(fire_count):
                        # Compute dedup_key for each fire
                        fire_epoch = next_run_epoch + (i * (cadence.total_seconds() if hasattr(cadence, 'total_seconds') else 3600))
                        dedup_key = compute_dedup_key(source_id, fire_epoch)

                        event_payload = {
                            "source_id": source_id,
                            "dispatcher_skill": dispatcher_skill,
                            "output_sink": output_sink,
                            "payload": payload,
                            "lapse_intervals": i + 1,
                        }
                        cur.execute("""
                            INSERT INTO events (
                                event_type, severity, repo, source, title, payload, dedup_key
                            ) VALUES (
                                'global_task_due', 'low', '_global', 'global_task_advancer',
                                %s, %s::jsonb, %s
                            )
                            ON CONFLICT (dedup_key) DO NOTHING
                        """, (title, json.dumps(event_payload), dedup_key))
                        total_events += 1

                # 3. UPDATE last_run and next_run
                if cadence:
                    # next_run = GREATEST(now(), next_run + cadence)
                    cur.execute("""
                        UPDATE global_task_sources
                        SET last_run = now(),
                            next_run = GREATEST(now(), coalesce(next_run, now()) + %s::interval)
                        WHERE id = %s
                    """, (cadence, source_id))
                else:
                    # One-shot: disable after first run
                    cur.execute("""
                        UPDATE global_task_sources
                        SET last_run = now(),
                            next_run = NULL,
                            enabled = false
                        WHERE id = %s
                    """, (source_id,))

            # Commit transaction
            conn.commit()
            logger.info(f"Advanced global_task_sources: {total_events} events inserted")

    except Exception as e:
        conn.rollback()
        logger.error(f"Transaction failed: {e}")
        return 0
    finally:
        conn.close()

    return total_events


if __name__ == "__main__":
    try:
        count = advance_global_tasks()
        sys.exit(0 if count >= 0 else 1)
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        sys.exit(1)
