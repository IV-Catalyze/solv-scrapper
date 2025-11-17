import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

try:
    import psycopg2
    from psycopg2.extras import Json

    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("⚠️  psycopg2-binary not installed. Database saving will be disabled.")

from app.utils.patient import normalize_patient_record, serialize_patient_payload, clean_str


def get_db_connection():
    """Get PostgreSQL database connection from environment variables."""
    if not DB_AVAILABLE:
        return None

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        try:
            from urllib.parse import urlparse

            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)

            parsed = urlparse(database_url)

            db_config: Dict[str, Any] = {
                "host": parsed.hostname,
                "port": parsed.port or 5432,
                "database": parsed.path.lstrip("/"),
                "user": parsed.username,
                "password": parsed.password or "",
            }
            if parsed.hostname and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                db_config["sslmode"] = "require"
        except Exception as e:
            print(f"   ⚠️  Error parsing DATABASE_URL: {e}")
            print("   DATABASE_URL format should be: postgresql://user:password@host:port/database")
            return None
    else:
        db_host = os.getenv("DB_HOST", "localhost")
        db_config = {
            "host": db_host,
            "port": os.getenv("DB_PORT", "5432"),
            "database": os.getenv("DB_NAME", "solvhealth_patients"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", ""),
        }
        if db_host and db_host not in ("localhost", "127.0.0.1", "::1"):
            db_config["sslmode"] = "require"

    try:
        conn = psycopg2.connect(**db_config)  # type: ignore[arg-type]
        return conn
    except psycopg2.Error as e:
        print(f"   ⚠️  Database connection error: {e}")
        return None


def ensure_db_tables_exist(conn) -> bool:
    """Ensure database tables exist, create them if they don't."""
    if not conn:
        return False

    try:
        schema_file = Path(__file__).parent / "db_schema.sql"

        if not schema_file.exists():
            print(f"   ⚠️  Schema file not found: {schema_file}")
            return False

        with open(schema_file, "r") as f:
            schema_sql = f.read()

        schema_sql = schema_sql.replace("CREATE DATABASE", "-- CREATE DATABASE")
        schema_sql = schema_sql.replace("\\c", "-- \\c")

        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            return True
        print(f"   ⚠️  Error ensuring tables exist: {e}")
        conn.rollback()
        return False


def persist_pending_patient(patient_data: Dict[str, Any]) -> Optional[int]:
    """Insert a pending patient record and return its pending_id."""
    if not DB_AVAILABLE:
        return None

    conn = get_db_connection()
    if not conn:
        return None

    try:
        ensure_db_tables_exist(conn)

        normalized = normalize_patient_record(patient_data)
        raw_payload = serialize_patient_payload(patient_data)

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO pending_patients (
                emr_id,
                booking_id,
                booking_number,
                patient_number,
                location_id,
                location_name,
                legal_first_name,
                legal_last_name,
                dob,
                mobile_phone,
                sex_at_birth,
                captured_at,
                reason_for_visit,
                raw_payload,
                status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING pending_id
            """,
            (
                normalized["emr_id"],
                normalized["booking_id"],
                normalized["booking_number"],
                normalized["patient_number"],
                normalized["location_id"],
                normalized["location_name"],
                normalized["legal_first_name"],
                normalized["legal_last_name"],
                normalized["dob"],
                normalized["mobile_phone"],
                normalized["sex_at_birth"],
                normalized["captured_at"],
                normalized["reason_for_visit"],
                Json(raw_payload),
                "pending",
            ),
        )
        pending_id_row = cursor.fetchone()
        conn.commit()
        cursor.close()
        if pending_id_row:
            return pending_id_row[0]
        return None
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error saving pending patient: {e}")
        return None
    finally:
        conn.close()


def update_pending_patient_record(
    patient_data: Dict[str, Any],
    status: Optional[str] = None,
    error_message: Optional[str] = None,
) -> bool:
    """Update an existing pending patient entry."""
    if not DB_AVAILABLE:
        return False

    pending_id = patient_data.get("pending_id")
    if not pending_id:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        normalized = normalize_patient_record(patient_data)
        raw_payload = serialize_patient_payload(patient_data)

        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE pending_patients
            SET emr_id = %s,
                booking_id = %s,
                booking_number = %s,
                patient_number = %s,
                location_id = %s,
                location_name = %s,
                legal_first_name = %s,
                legal_last_name = %s,
                dob = %s,
                mobile_phone = %s,
                sex_at_birth = %s,
                captured_at = %s,
                reason_for_visit = %s,
                raw_payload = %s,
                status = COALESCE(%s, status),
                error_message = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE pending_id = %s
            """,
            (
                normalized["emr_id"],
                normalized["booking_id"],
                normalized["booking_number"],
                normalized["patient_number"],
                normalized["location_id"],
                normalized["location_name"],
                normalized["legal_first_name"],
                normalized["legal_last_name"],
                normalized["dob"],
                normalized["mobile_phone"],
                normalized["sex_at_birth"],
                normalized["captured_at"],
                normalized["reason_for_visit"],
                Json(raw_payload),
                status,
                error_message,
                pending_id,
            ),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        return updated
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error updating pending patient: {e}")
        return False
    finally:
        conn.close()


def mark_pending_patient_status(
    pending_id: int,
    status: str,
    error_message: Optional[str] = None,
) -> bool:
    """Update only the status/error message for a pending patient."""
    if not DB_AVAILABLE:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE pending_patients
            SET status = %s,
                error_message = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE pending_id = %s
            """,
            (status, error_message, pending_id),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        return updated
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error updating pending patient status: {e}")
        return False
    finally:
        conn.close()


def update_pending_status_by_identifiers(
    status: str,
    *,
    booking_id: Optional[str] = None,
    booking_number: Optional[str] = None,
    patient_number: Optional[str] = None,
    emr_id: Optional[str] = None,
) -> List[int]:
    """Update pending patients' status using identifiers when pending_id is unknown."""
    from patient_utils import normalize_status_value

    if not DB_AVAILABLE:
        return []

    status_normalized = normalize_status_value(status)
    if not status_normalized:
        return []

    identifiers: List[Tuple[str, Optional[str]]] = [
        ("booking_id", clean_str(booking_id)),
        ("booking_number", clean_str(booking_number)),
        ("patient_number", clean_str(patient_number)),
        ("emr_id", clean_str(emr_id)),
    ]

    conditions: List[str] = []
    params: List[str] = []
    for column, value in identifiers:
        if value:
            conditions.append(f"{column} = %s")
            params.append(value)

    if not conditions:
        return []

    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        query = f"""
            UPDATE pending_patients
            SET status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE {" OR ".join(conditions)}
            RETURNING pending_id
        """
        cursor.execute(query, (status_normalized, *params))
        rows = cursor.fetchall()
        conn.commit()
        cursor.close()

        updated_ids = [row[0] for row in rows] if rows else []
        if updated_ids:
            print(f"   💾 Updated pending patient status to '{status_normalized}' for pending_id(s): {updated_ids}")
        return updated_ids
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error updating pending patient status by identifiers: {e}")
        return []
    finally:
        conn.close()


def update_patient_status_by_identifiers(
    status: str,
    *,
    booking_id: Optional[str] = None,
    booking_number: Optional[str] = None,
    patient_number: Optional[str] = None,
    emr_id: Optional[str] = None,
) -> List[int]:
    """Update patients table status using identifiers."""
    from patient_utils import normalize_status_value

    if not DB_AVAILABLE:
        return []

    status_normalized = normalize_status_value(status)
    if not status_normalized:
        return []

    identifiers: List[Tuple[str, Optional[str]]] = [
        ("booking_id", clean_str(booking_id)),
        ("booking_number", clean_str(booking_number)),
        ("patient_number", clean_str(patient_number)),
        ("emr_id", clean_str(emr_id)),
    ]

    conditions: List[str] = []
    params: List[str] = []
    for column, value in identifiers:
        if value:
            conditions.append(f"{column} = %s")
            params.append(value)

    if not conditions:
        return []

    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        query = f"""
            UPDATE patients
            SET status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE {" OR ".join(conditions)}
            RETURNING id
        """
        cursor.execute(query, (status_normalized, *params))
        rows = cursor.fetchall()
        conn.commit()
        cursor.close()

        updated_ids = [row[0] for row in rows] if rows else []
        if updated_ids:
            print(f"   💾 Updated patients status to '{status_normalized}' for id(s): {updated_ids}")
        return updated_ids
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error updating patients status by identifiers: {e}")
        return []
    finally:
        conn.close()


def find_pending_patient_id(patient_data: Dict[str, Any]) -> Optional[int]:
    """Attempt to locate the pending patient row matching provided data."""
    if not DB_AVAILABLE:
        return None

    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        normalized = normalize_patient_record(patient_data)

        for column in ("booking_id", "booking_number", "patient_number"):
            value = normalized.get(column)
            if value:
                cursor.execute(
                    f"""
                    SELECT pending_id
                    FROM pending_patients
                    WHERE status IN ('pending', 'ready')
                      AND {column} = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (value,),
                )
                row = cursor.fetchone()
                if row:
                    conn.commit()
                    cursor.close()
                    return row[0]

        first = normalized.get("legal_first_name")
        last = normalized.get("legal_last_name")
        captured_at = normalized.get("captured_at")

        if first and last and captured_at:
            cursor.execute(
                """
                SELECT pending_id
                FROM pending_patients
                WHERE status IN ('pending', 'ready')
                  AND LOWER(COALESCE(legal_first_name, '')) = LOWER(%s)
                  AND LOWER(COALESCE(legal_last_name, '')) = LOWER(%s)
                  AND captured_at = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (first, last, captured_at),
            )
            row = cursor.fetchone()
            if row:
                conn.commit()
                cursor.close()
                return row[0]

        cursor.execute(
            """
            SELECT pending_id
            FROM pending_patients
            WHERE status IN ('pending', 'ready')
              AND emr_id IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.commit()
        cursor.close()
        if row:
            return row[0]
        return None
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def save_patient_to_db(patient_data: Dict[str, Any], on_conflict: str = "update") -> bool:
    """
    Save a single patient record to PostgreSQL database.
    """
    if not DB_AVAILABLE:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        ensure_db_tables_exist(conn)

        normalized = normalize_patient_record(patient_data)

        if not normalized.get("emr_id"):
            print("   ⚠️  Skipping database save: missing emr_id")
            return False

        cursor = conn.cursor()

        if normalized["emr_id"]:
            lookup_fields: List[Tuple[str, Optional[str]]] = [
                ("booking_id", normalized.get("booking_id")),
                ("booking_number", normalized.get("booking_number")),
                ("patient_number", normalized.get("patient_number")),
            ]
            for column, value in lookup_fields:
                if not value:
                    continue
                cursor.execute(
                    f"""
                    SELECT id, emr_id
                    FROM patients
                    WHERE {column} = %s
                    ORDER BY updated_at DESC NULLS LAST, captured_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (value,),
                )
                existing = cursor.fetchone()
                if existing:
                    existing_id, existing_emr = existing
                    if existing_emr != normalized["emr_id"]:
                        cursor.execute(
                            """
                            UPDATE patients
                            SET emr_id = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """,
                            (normalized["emr_id"], existing_id),
                        )
                    break

        insert_query = """
            INSERT INTO patients (
                emr_id,
                booking_id,
                booking_number,
                patient_number,
                location_id,
                location_name,
                legal_first_name,
                legal_last_name,
                dob,
                mobile_phone,
                sex_at_birth,
                captured_at,
                reason_for_visit
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        if on_conflict == "ignore":
            insert_query += """
                ON CONFLICT (emr_id) DO NOTHING
            """
        elif on_conflict == "update":
            insert_query += """
                ON CONFLICT (emr_id) DO UPDATE SET
                    booking_id = EXCLUDED.booking_id,
                    booking_number = EXCLUDED.booking_number,
                    patient_number = EXCLUDED.patient_number,
                    location_name = EXCLUDED.location_name,
                    legal_first_name = EXCLUDED.legal_first_name,
                    legal_last_name = EXCLUDED.legal_last_name,
                    dob = EXCLUDED.dob,
                    mobile_phone = EXCLUDED.mobile_phone,
                    sex_at_birth = EXCLUDED.sex_at_birth,
                    captured_at = EXCLUDED.captured_at,
                    reason_for_visit = EXCLUDED.reason_for_visit,
                    updated_at = CURRENT_TIMESTAMP
            """

        values = (
            normalized["emr_id"],
            normalized["booking_id"],
            normalized["booking_number"],
            normalized["patient_number"],
            normalized["location_id"],
            normalized["location_name"],
            normalized["legal_first_name"],
            normalized["legal_last_name"],
            normalized["dob"],
            normalized["mobile_phone"],
            normalized["sex_at_birth"],
            normalized["captured_at"],
            normalized["reason_for_visit"],
        )

        cursor.execute(insert_query, values)
        conn.commit()
        cursor.close()

        print(f"   💾 Saved to database (EMR ID: {normalized['emr_id']})")
        return True

    except psycopg2.Error as e:  # type: ignore[name-defined]
        conn.rollback()
        print(f"   ⚠️  Database error: {e}")
        return False
    except Exception as e:
        print(f"   ⚠️  Error saving to database: {e}")
        return False
    finally:
        conn.close()


