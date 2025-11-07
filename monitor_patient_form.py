#!/usr/bin/env python3
"""
Patient Form Monitor
A background Playwright script that monitors the Solvhealth queue page and captures
patient form data when the "Add Patient" button is clicked and the form is submitted.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from locations import LOCATION_ID_TO_NAME

# Import database functions
try:
    import psycopg2
    from psycopg2.extras import Json
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("⚠️  psycopg2-binary not installed. Database saving will be disabled.")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional


def str_to_bool(value: Optional[str]) -> bool:
    """Convert common truthy/falsey strings to boolean."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def extract_location_id_from_url(url):
    """
    Extract location_ids query parameter from URL.
    
    Args:
        url: Full URL string
    
    Returns:
        Location ID string, or None if not found
    """
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        location_ids = query_params.get('location_ids', [])
        if location_ids:
            # location_ids can be a list, get the first one
            return location_ids[0] if isinstance(location_ids, list) else location_ids
        return None
    except Exception as e:
        print(f"⚠️  Error extracting location_id from URL: {e}")
        return None


def get_location_name(location_id):
    """
    Get location name from location ID using the mapping.
    
    Args:
        location_id: Location ID string
    
    Returns:
        Location name string, or "Unknown Location" if not found
    """
    return LOCATION_ID_TO_NAME.get(location_id, f"Unknown Location ({location_id})")


def get_db_connection():
    """Get PostgreSQL database connection from environment variables."""
    if not DB_AVAILABLE:
        return None
    
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'solvhealth_patients'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', '')
    }
    
    try:
        conn = psycopg2.connect(**db_config)
        return conn
    except psycopg2.Error as e:
        print(f"   ⚠️  Database connection error: {e}")
        return None


def normalize_date(date_str: str) -> Optional[str]:
    """Normalize date string to YYYY-MM-DD format."""
    if not date_str or date_str.strip() == '':
        return None
    
    date_str = date_str.strip()
    
    # Try to parse various date formats
    formats = [
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%m-%d-%Y',
        '%d/%m/%Y',
        '%d-%m-%Y',
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    return None


def normalize_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Normalize timestamp string to datetime object."""
    if not timestamp_str or timestamp_str.strip() == '':
        return None
    
    timestamp_str = timestamp_str.strip()
    
    # Try ISO format first
    try:
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    # Try other common formats
    formats = [
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    
    return None


def normalize_patient_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize patient record from JSON to database format."""
    emr_id = record.get('emrId') or record.get('emr_id') or record.get('emrID')

    normalized = {
        'emr_id': emr_id.strip() if isinstance(emr_id, str) else emr_id,
        'booking_id': record.get('booking_id') or record.get('bookingId') or None,
        'booking_number': record.get('booking_number') or record.get('bookingNumber') or None,
        'patient_number': record.get('patient_number') or record.get('patientNumber') or None,
        'location_id': record.get('locationId') or record.get('location_id') or None,
        'location_name': record.get('location_name') or record.get('locationName') or None,
        'legal_first_name': record.get('legalFirstName') or record.get('legal_first_name') or record.get('firstName') or None,
        'legal_last_name': record.get('legalLastName') or record.get('legal_last_name') or record.get('lastName') or None,
        'dob': record.get('dob') or record.get('dateOfBirth') or record.get('date_of_birth') or None,
        'mobile_phone': record.get('mobilePhone') or record.get('mobile_phone') or record.get('phone') or None,
        'sex_at_birth': record.get('sexAtBirth') or record.get('sex_at_birth') or record.get('gender') or None,
        'captured_at': normalize_timestamp(record.get('captured_at') or record.get('capturedAt')) or datetime.now(),
        'reason_for_visit': record.get('reasonForVisit') or record.get('reason_for_visit') or record.get('reason') or None
    }

    # Clean up empty strings to None
    for key, value in list(normalized.items()):
        if isinstance(value, str):
            value = value.strip()
            normalized[key] = value or None

    return normalized


def ensure_db_tables_exist(conn):
    """Ensure database tables exist, create them if they don't."""
    if not conn:
        return False
    
    try:
        schema_file = Path(__file__).parent / 'db_schema.sql'
        
        if not schema_file.exists():
            print(f"   ⚠️  Schema file not found: {schema_file}")
            return False
        
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        # Remove CREATE DATABASE command if present (we're already connected)
        schema_sql = schema_sql.replace('CREATE DATABASE', '-- CREATE DATABASE')
        schema_sql = schema_sql.replace('\\c', '-- \\c')
        
        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        # Table might already exist, which is fine
        if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
            return True
        print(f"   ⚠️  Error ensuring tables exist: {e}")
        conn.rollback()
        return False


def _serialize_patient_payload(patient_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a JSON-serializable copy of the patient payload."""
    try:
        return json.loads(json.dumps(patient_data, default=str))
    except (TypeError, ValueError):
        # Fallback: convert datetimes manually
        serializable = {}
        for key, value in patient_data.items():
            if isinstance(value, datetime):
                serializable[key] = value.isoformat()
            else:
                serializable[key] = value
        return serializable


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
        raw_payload = _serialize_patient_payload(patient_data)

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
                normalized['emr_id'],
                normalized['booking_id'],
                normalized['booking_number'],
                normalized['patient_number'],
                normalized['location_id'],
                normalized['location_name'],
                normalized['legal_first_name'],
                normalized['legal_last_name'],
                normalized['dob'],
                normalized['mobile_phone'],
                normalized['sex_at_birth'],
                normalized['captured_at'],
                normalized['reason_for_visit'],
                Json(raw_payload),
                'pending'
            )
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
    error_message: Optional[str] = None
) -> bool:
    """Update an existing pending patient entry."""
    if not DB_AVAILABLE:
        return False

    pending_id = patient_data.get('pending_id')
    if not pending_id:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        normalized = normalize_patient_record(patient_data)
        raw_payload = _serialize_patient_payload(patient_data)

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
                normalized['emr_id'],
                normalized['booking_id'],
                normalized['booking_number'],
                normalized['patient_number'],
                normalized['location_id'],
                normalized['location_name'],
                normalized['legal_first_name'],
                normalized['legal_last_name'],
                normalized['dob'],
                normalized['mobile_phone'],
                normalized['sex_at_birth'],
                normalized['captured_at'],
                normalized['reason_for_visit'],
                Json(raw_payload),
                status,
                error_message,
                pending_id
            )
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
    error_message: Optional[str] = None
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
            (status, error_message, pending_id)
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

        # Prefer exact booking identifiers when available
        for column in ('booking_id', 'booking_number', 'patient_number'):
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
                    (value,)
                )
                row = cursor.fetchone()
                if row:
                    conn.commit()
                    cursor.close()
                    return row[0]

        # Fall back to matching by name + captured_at timestamp
        first = normalized.get('legal_first_name')
        last = normalized.get('legal_last_name')
        captured_at = normalized.get('captured_at')

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
                (first, last, captured_at)
            )
            row = cursor.fetchone()
            if row:
                conn.commit()
                cursor.close()
                return row[0]

        # As a last resort, match by recent pending entries without EMR ID
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


def save_patient_to_db(patient_data: Dict[str, Any], on_conflict: str = 'update') -> bool:
    """
    Save a single patient record to PostgreSQL database.
    
    Args:
        patient_data: Dictionary with patient data
        on_conflict: What to do on conflict ('ignore' or 'update')
    
    Returns:
        True if saved successfully, False otherwise
    """
    if not DB_AVAILABLE:
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        # Ensure tables exist
        ensure_db_tables_exist(conn)
        
        normalized = normalize_patient_record(patient_data)

        if not normalized.get('emr_id'):
            print("   ⚠️  Skipping database save: missing emr_id")
            return False

        cursor = conn.cursor()

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

        if on_conflict == 'ignore':
            insert_query += """
                ON CONFLICT (emr_id) DO NOTHING
            """
        elif on_conflict == 'update':
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
            normalized['emr_id'],
            normalized['booking_id'],
            normalized['booking_number'],
            normalized['patient_number'],
            normalized['location_id'],
            normalized['location_name'],
            normalized['legal_first_name'],
            normalized['legal_last_name'],
            normalized['dob'],
            normalized['mobile_phone'],
            normalized['sex_at_birth'],
            normalized['captured_at'],
            normalized['reason_for_visit']
        )

        cursor.execute(insert_query, values)
        conn.commit()
        cursor.close()
        
        print(f"   💾 Saved to database (EMR ID: {normalized['emr_id']})")
        return True
        
    except psycopg2.Error as e:
        conn.rollback()
        print(f"   ⚠️  Database error: {e}")
        return False
    except Exception as e:
        print(f"   ⚠️  Error saving to database: {e}")
        return False
    finally:
        if conn:
            conn.close()


async def capture_form_data(page):
    """
    Capture all form field values from the patient modal.
    
    Args:
        page: Playwright page object
    
    Returns:
        Dictionary with captured form data
    """
    form_data = {}
    
    try:
        # Wait for the modal to be visible
        # The modal might have various selectors, try common ones
        modal_selectors = [
            '[role="dialog"]',
            '.modal',
            '[data-testid*="modal"]',
            '[class*="Modal"]',
        ]
        
        modal_visible = False
        for selector in modal_selectors:
            try:
                await page.wait_for_selector(selector, timeout=2000, state="visible")
                modal_visible = True
                break
            except PlaywrightTimeoutError:
                continue
        
        if not modal_visible:
            print("⚠️  Modal not found, trying to capture data anyway...")
        
        # Capture text input fields - using actual field names from HTML
        field_mappings = [
            {
                'key': 'legalFirstName',
                'selectors': [
                    '[name="firstName"]',
                    '[data-testid="addPatientFirstName"]',
                    'input[name="firstName"]',
                    'input[data-testid="addPatientFirstName"]'
                ]
            },
            {
                'key': 'legalLastName',
                'selectors': [
                    '[name="lastName"]',
                    '[data-testid="addPatientLastName"]',
                    'input[name="lastName"]',
                    'input[data-testid="addPatientLastName"]'
                ]
            },
            {
                'key': 'mobilePhone',
                'selectors': [
                    '[data-testid="addPatientMobilePhone"]',
                    '[name="phone"]',
                    'input[type="tel"][data-testid*="Phone"]',
                    'input[data-testid="addPatientMobilePhone"]'
                ]
            },
            {
                'key': 'dob',
                'selectors': [
                    '[data-testid="addPatientDob"]',
                    '[name="birthDate"]',
                    'input[placeholder*="MM/DD/YYYY"]',
                    'input[data-testid="addPatientDob"]'
                ]
            },
            {
                'key': 'reasonForVisit',
                'selectors': [
                    '[name="reasonForVisit"]',
                    '[data-testid*="addPatientReasonForVisit"]',
                    '[id="reasonForVisit"]',
                    '[data-testid="addPatientReasonForVisit-0"]',
                    'input[name="reasonForVisit"]',
                    'input[id="reasonForVisit"]'
                ]
            }
        ]
        
        for field in field_mappings:
            try:
                value = None
                for selector in field['selectors']:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            value = await element.input_value()
                            if value and value.strip():
                                break
                    except Exception:
                        continue
                
                form_data[field['key']] = value or ""
            except Exception as e:
                print(f"⚠️  Error capturing {field['key']}: {e}")
                form_data[field['key']] = ""
        
        # Capture dropdown/select field (sexAtBirth) - using actual field name "birthSex"
        try:
            sex_selectors = [
                '#birthSex',
                '[id="birthSex"]',
                '[name="birthSex"]',
                '[data-testid*="birthSex"]',
                'select[name="birthSex"]',
                'select[id="birthSex"]',
            ]
            
            sex_value = None
            for selector in sex_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        # Check if it's a select element
                        tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                        if tag_name == 'select':
                            sex_value = await element.evaluate('el => el.value')
                        else:
                            # For Ant Design custom dropdown, get the selected value
                            sex_value = await element.evaluate("""
                                (el) => {
                                    // Method 1: Check for selected-value element (most reliable for Ant Design)
                                    const selectedValueEl = el.querySelector('.ant-select-selection-selected-value');
                                    if (selectedValueEl) {
                                        const selectedText = (selectedValueEl.textContent || selectedValueEl.innerText || '').trim();
                                        if (selectedText && selectedText.length > 0) {
                                            return selectedText;
                                        }
                                        // Also try title attribute
                                        const title = selectedValueEl.getAttribute('title');
                                        if (title) return title;
                                    }
                                    
                                    // Method 2: Check the rendered container
                                    const rendered = el.querySelector('.ant-select-selection__rendered');
                                    const placeholder = el.querySelector('.ant-select-selection__placeholder');
                                    
                                    if (rendered) {
                                        // Check if placeholder is hidden (meaning something is selected)
                                        let isPlaceholderHidden = false;
                                        if (placeholder) {
                                            const placeholderStyle = window.getComputedStyle(placeholder);
                                            isPlaceholderHidden = placeholderStyle.display === 'none';
                                        }
                                        
                                        if (isPlaceholderHidden || !placeholder) {
                                            // Get all text from rendered
                                            const allText = rendered.textContent || rendered.innerText || '';
                                            // Remove placeholder text if it exists
                                            const placeholderText = placeholder ? (placeholder.textContent || placeholder.innerText || '') : '';
                                            const cleanText = allText.replace(placeholderText, '').trim();
                                            
                                            if (cleanText && !cleanText.includes('Choose an option') && cleanText.length > 0) {
                                                return cleanText;
                                            }
                                        }
                                    }
                                    
                                    // Method 3: Check if dropdown is open and get selected option
                                    const dropdown = el.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
                                    if (dropdown) {
                                        const selectedOption = dropdown.querySelector('.ant-select-item-selected, .ant-select-item-option-selected');
                                        if (selectedOption) {
                                            const optionText = (selectedOption.textContent || selectedOption.innerText || '').trim();
                                            if (optionText) return optionText;
                                        }
                                    }
                                    
                                    // Method 4: Look for hidden input or form field
                                    const hiddenInput = el.querySelector('input[type="hidden"]');
                                    if (hiddenInput && hiddenInput.value) {
                                        return hiddenInput.value;
                                    }
                                    
                                    // Method 5: Check Ant Design's internal state
                                    const antSelect = el.closest('.ant-select');
                                    if (antSelect) {
                                        const hiddenInput = antSelect.querySelector('input[type="hidden"]');
                                        if (hiddenInput && hiddenInput.value) {
                                            return hiddenInput.value;
                                        }
                                    }
                                    
                                    // Method 6: Check data attributes
                                    return el.getAttribute('data-value') || 
                                           el.getAttribute('value') || 
                                           el.getAttribute('aria-label') || '';
                                }
                            """)
                        if sex_value and sex_value.strip():
                            break
                except Exception:
                    continue
            
            form_data['sexAtBirth'] = sex_value or ""
        except Exception as e:
            print(f"⚠️  Error capturing sexAtBirth: {e}")
            form_data['sexAtBirth'] = ""
        
        return form_data
        
    except Exception as e:
        print(f"⚠️  Error capturing form data: {e}")
        return form_data


async def save_patient_data(data) -> Optional[int]:
    """Persist patient data to the pending_patients staging table."""
    try:
        # Ensure captured_at is set so we can match the record later
        if not data.get('captured_at'):
            data['captured_at'] = datetime.now().isoformat()

        print("   💾 Saving patient submission to pending_patients staging table")

        pending_id = persist_pending_patient(data)
        if not pending_id:
            print("   ❌ Failed to persist patient submission to database")
            return None

        data['pending_id'] = pending_id
        print(f"✅ Pending patient saved (pending_id={pending_id})")

        if data.get('emr_id'):
            print("   📎 EMR ID already available, saving directly to patients table")
            saved = save_patient_to_db(data, on_conflict='update')
            if saved:
                mark_pending_patient_status(pending_id, 'completed')
            else:
                mark_pending_patient_status(pending_id, 'error', 'Failed to upsert into patients table')
        else:
            mark_pending_patient_status(pending_id, 'pending')
            print("   ⏳ Waiting for EMR ID before inserting into patients table")

        return pending_id

    except Exception as e:
        print(f"❌ Error saving patient data: {e}")
        import traceback
        traceback.print_exc()
        return None


async def setup_form_monitor(page, location_id, location_name):
    """
    Set up JavaScript event listener to monitor form submissions.
    
    Args:
        page: Playwright page object
        location_id: Location ID from URL
        location_name: Location name from mapping
    """
    
    # Track pending patients waiting for EMR ID
    pending_patients = []
    
    # Expose a Python function to JavaScript
    async def handle_patient_submission(form_data):
        """
        Callback function called from JavaScript when form is submitted.
        """
        print(f"\n🎯 Patient form submitted detected!")
        print(f"   Raw form data received: {form_data}")
        
        # Re-extract location_id from current URL in case user changed location
        current_url = page.url
        current_location_id = extract_location_id_from_url(current_url) or location_id
        if current_location_id:
            current_location_name = get_location_name(current_location_id) or f"Location {current_location_id}"
        else:
            current_location_name = "Unknown Location"
        
        print(f"   Location ID: {current_location_id}")
        print(f"   Location: {current_location_name}")
        
        # Add location information to the data
        complete_data = {
            'location_id': current_location_id,
            'location_name': current_location_name,
            'emr_id': '',  # Will be filled later
            'booking_id': form_data.get('booking_id', '') if isinstance(form_data, dict) else '',
            'booking_number': form_data.get('booking_number', '') if isinstance(form_data, dict) else '',
            'patient_number': form_data.get('patient_number', '') if isinstance(form_data, dict) else '',
            **form_data
        }
        
        print(f"   Complete data to save: {complete_data}")
        
        # Save the data first and capture the pending_id for future updates
        pending_id = await save_patient_data(complete_data)
        if not pending_id:
            print("   ❌ Failed to persist patient submission; skipping EMR monitoring")
            return
        complete_data['pending_id'] = pending_id
        
        # Add to pending patients list for EMR ID monitoring
        pending_patients.append(complete_data)
        
        # Start background task to wait for EMR ID (as fallback)
        asyncio.create_task(wait_for_emr_id(complete_data))
    
    # Expose the function to the page
    await page.expose_function("handlePatientSubmission", handle_patient_submission)
    
    async def wait_for_emr_id(patient_data):
        """
        Wait for the EMR ID to appear in API responses.
        Monitors network responses instead of opening the modal.
        
        Args:
            patient_data: Dictionary with patient data that was just saved
        """
        try:
            print(f"\n⏳ Waiting for EMR ID to be assigned via API...")
            print(f"   Patient: {patient_data.get('legalFirstName', '')} {patient_data.get('legalLastName', '')}")
            
            patient_first_name = patient_data.get('legalFirstName', '').strip()
            patient_last_name = patient_data.get('legalLastName', '').strip()
            captured_at = patient_data.get('captured_at', '')
            
            # Wait for API response that contains EMR ID
            max_wait_time = 120  # Maximum 2 minutes
            poll_interval = 3  # Check every 3 seconds
            elapsed_time = 0
            
            print(f"   🔄 Monitoring API responses for EMR ID (checking every {poll_interval} seconds, max {max_wait_time} seconds)...")
            
            while elapsed_time < max_wait_time:
                try:
                    # Check API responses for EMR ID by looking at the queue data
                    emr_id = await page.evaluate("""
                        (firstName, lastName) => {
                            // Look for patient data in the DOM that might contain EMR ID
                            // Check if there's any data attribute or text containing EMR ID
                            const allElements = document.querySelectorAll('[data-testid*="patient"], [data-testid*="booking"]');
                            
                            for (const element of allElements) {
                                const text = element.textContent || element.innerText || '';
                                // Check if this element contains the patient name
                                if (firstName && lastName && text.includes(firstName) && text.includes(lastName)) {
                                    // Look for EMR ID in nearby elements or data attributes
                                    const parent = element.closest('[class*="booking"], [class*="patient"]');
                                    if (parent) {
                                        const parentText = parent.textContent || parent.innerText || '';
                                        const emrMatch = parentText.match(/EMR ID[\\s:]+(\\d+)/i);
                                        if (emrMatch && emrMatch[1]) {
                                            return emrMatch[1];
                                        }
                                    }
                                }
                            }
                            
                            return null;
                        }
                    """, patient_first_name, patient_last_name)
                    
                    if emr_id:
                        print(f"   ✅ EMR ID found in DOM: {emr_id}")
                        patient_data['emr_id'] = emr_id
                        await update_patient_emr_id(patient_data)
                        print(f"   💾 Updated patient data with EMR ID: {emr_id}")
                        return
                
                except Exception as e:
                    print(f"   ⚠️  Error checking for EMR ID: {e}")
                
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                if elapsed_time % 15 == 0:  # Print status every 15 seconds
                    print(f"   ⏳ Still waiting for EMR ID... ({elapsed_time}s elapsed)")
            
            print(f"   ⚠️  EMR ID not found after {max_wait_time} seconds")
            
        except Exception as e:
            print(f"   ❌ Error waiting for EMR ID: {e}")
            import traceback
            traceback.print_exc()
    
    async def update_patient_emr_id(patient_data):
        """Update the pending record with the EMR ID and promote it to patients table."""
        try:
            if not patient_data.get('pending_id'):
                pending_id = find_pending_patient_id(patient_data)
                if pending_id:
                    patient_data['pending_id'] = pending_id
                else:
                    print("   ⚠️  Pending record not found for EMR assignment")
                    return

            pending_id = patient_data['pending_id']

            updated = update_pending_patient_record(patient_data, status='ready')
            if not updated:
                print(f"   ⚠️  Failed to update pending patient (pending_id={pending_id}) with EMR ID")
                return

            saved = save_patient_to_db(patient_data, on_conflict='update')
            if saved:
                mark_pending_patient_status(pending_id, 'completed')
                print(f"   ✅ Pending patient promoted to patients table (pending_id={pending_id})")
            else:
                mark_pending_patient_status(pending_id, 'error', 'Failed to upsert into patients table after EMR assignment')
                print(f"   ❌ Failed to insert pending patient into patients table (pending_id={pending_id})")

        except Exception as e:
            pending_id = patient_data.get('pending_id')
            if pending_id:
                mark_pending_patient_status(pending_id, 'error', str(e))
            print(f"   ❌ Error updating EMR ID in database: {e}")
            import traceback
            traceback.print_exc()
    
    # Set up a background task to periodically check for form submissions
    async def monitor_form_submissions():
        """Background task that polls for form submissions"""
        last_captured = None
        while True:
            try:
                await asyncio.sleep(0.5)  # Check every 500ms
                
                # Check if modal is visible
                modal_visible = await page.evaluate("""
                    () => {
                        const modal = document.querySelector('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
                        return modal && window.getComputedStyle(modal).display !== 'none';
                    }
                """)
                
                if modal_visible:
                    # Try to capture form data
                    form_data = await capture_form_data(page)
                    
                    # Check if we have new data (at least one field filled)
                    if any(v and v.strip() for v in form_data.values() if v):
                        # Create a hash of the data to detect changes
                        data_hash = str(sorted(form_data.items()))
                        
                        if data_hash != last_captured:
                            # Check if form is being submitted (button might be disabled/loading)
                            is_submitting = await page.evaluate("""
                                () => {
                                    const button = document.querySelector('[data-testid="addPatientSubmitButton"]') ||
                                                   document.querySelector('button[data-testid*="addPatient"]') ||
                                                   document.querySelector('button[type="submit"]');
                                    if (!button) return false;
                                    const modal = button.closest('[role="dialog"], .modal, [class*="Modal"]');
                                    return modal && (button.disabled || button.getAttribute('aria-busy') === 'true');
                                }
                            """)
                            
                            # If button is in submitting state, capture the data
                            if is_submitting:
                                print(f"\n🔄 Form submission detected via polling!")
                                last_captured = data_hash
                                await handle_patient_submission(form_data)
            except Exception as e:
                # Silently continue on errors
                pass
    
    # Start the background monitoring task
    asyncio.create_task(monitor_form_submissions())
    print("✅ Background form monitoring started")
    
    # Intercept network responses to catch EMR ID from API calls
    async def handle_response(response):
        """Intercept API responses to extract EMR ID"""
        try:
            url = response.url
            status = response.status
            
            # Look for API responses that might contain patient/booking data with EMR ID
            # Check a wider range of URLs, especially booking endpoints
            url_lower = url.lower()
            is_relevant = (
                status == 200 and (
                    "patient" in url_lower or 
                    "booking" in url_lower or 
                    "bookings" in url_lower or
                    "queue" in url_lower or 
                    "appointment" in url_lower or
                    "appointments" in url_lower or
                    "facesheet" in url_lower or
                    "visit" in url_lower or
                    "/api/" in url_lower or
                    "api-manage.solvhealth.com" in url_lower
                )
            )
            
            if is_relevant:
                try:
                    # Try to get JSON response
                    response_body = await response.json()
                    
                    # First, check for the specific booking API structure
                    # EMR ID is in: data.integration_status[0].emr_id or data.patient_match_details.external_user_profile_id
                    emr_id = None
                    patient_match = None
                    booking_data = None
                    booking_id = ''
                    booking_number = ''
                    patient_number = ''
                    all_patients = []
                    
                    # Check if this is a booking API response
                    if isinstance(response_body, dict) and 'data' in response_body:
                        booking_data = response_body.get('data', {})
                        
                        # Method 1: Check integration_status array for emr_id
                        integration_status = booking_data.get('integration_status', [])
                        if isinstance(integration_status, list) and len(integration_status) > 0:
                            for integration in integration_status:
                                if isinstance(integration, dict):
                                    integration_emr_id = integration.get('emr_id')
                                    if integration_emr_id and not emr_id:
                                        emr_id = str(integration_emr_id).strip()
                                        patient_match = booking_data
                                        print(f"   📍 Found EMR ID in integration_status: {emr_id}")
                                    # Extract booking/patient numbers from requests
                                    requests = integration.get('requests', [])
                                    if isinstance(requests, list):
                                        for request in requests:
                                            if not isinstance(request, dict):
                                                continue
                                            if not booking_number:
                                                booking_value = request.get('booking_number') or request.get('bookingNumber')
                                                if booking_value:
                                                    booking_number = str(booking_value).strip()
                                            if not patient_number:
                                                patient_value = request.get('patient_number') or request.get('patientNumber')
                                                if patient_value:
                                                    patient_number = str(patient_value).strip()
                                    if emr_id and booking_number and patient_number:
                                        break
                        
                        # Method 2: Check patient_match_details for external_user_profile_id (which is the EMR ID)
                        if not emr_id:
                            patient_match_details = booking_data.get('patient_match_details', {})
                            if isinstance(patient_match_details, dict):
                                external_user_profile_id = patient_match_details.get('external_user_profile_id')
                                if external_user_profile_id:
                                    emr_id = str(external_user_profile_id).strip()
                                    patient_match = booking_data
                                    print(f"   📍 Found EMR ID in patient_match_details: {emr_id}")
                                # Sometimes patient number may live here as well
                                if not patient_number:
                                    pm_patient_number = patient_match_details.get('patient_number')
                                    if pm_patient_number:
                                        patient_number = str(pm_patient_number).strip()
                    
                    # If not found in booking structure, recursively search
                    if not emr_id:
                        all_patients = []
                        
                        def find_emr_id(data, path=""):
                            nonlocal emr_id, patient_match, all_patients
                            if isinstance(data, dict):
                                # Check for EMR ID fields (various possible field names)
                                for key, value in data.items():
                                    key_lower = str(key).lower()
                                    if ("emr" in key_lower or "emr_id" in key_lower or "emrid" in key_lower) and isinstance(value, (str, int)):
                                        if value and str(value).strip():
                                            emr_id = str(value).strip()
                                            patient_match = data
                                            return
                                    
                                    # Collect patient-like objects
                                    if isinstance(value, dict):
                                        # Check if this looks like a patient object
                                        if any(k in str(value.keys()).lower() for k in ['first', 'last', 'name', 'patient']):
                                            all_patients.append(value)
                                        find_emr_id(value, f"{path}.{key}")
                                    elif isinstance(value, list):
                                        find_emr_id(value, path)
                            elif isinstance(data, list):
                                for item in data:
                                    find_emr_id(item, path)
                        
                        find_emr_id(response_body)
                    
                    # If we found EMR ID, try to match with pending patients
                    if emr_id:
                        print(f"\n🌐 API response contains EMR ID: {emr_id}")
                        print(f"   URL: {url}")
                        
                        # Try to extract patient info from the matched data
                        patient_first_name = ''
                        patient_last_name = ''
                        
                        if patient_match:
                            # Extract patient name from booking data structure
                            patient_first_name = (
                                patient_match.get('first_name') or
                                patient_match.get('firstName') or 
                                patient_match.get('legalFirstName') or 
                                patient_match.get('firstname') or
                                ''
                            )
                            patient_last_name = (
                                patient_match.get('last_name') or
                                patient_match.get('lastName') or 
                                patient_match.get('legalLastName') or 
                                patient_match.get('lastname') or
                                ''
                            )
                            
                            # Also try to get booking ID for matching
                            if not booking_id:
                                booking_id = patient_match.get('id') or ''
                            if not booking_number and patient_match.get('booking_number'):
                                booking_number = str(patient_match.get('booking_number')).strip()
                            if not patient_number and patient_match.get('patient_number'):
                                patient_number = str(patient_match.get('patient_number')).strip()
                        
                        # Also check all_patients if we didn't get names from patient_match
                        if not patient_first_name and all_patients:
                            for p in all_patients:
                                if emr_id in str(p.values()):
                                    patient_first_name = (
                                        p.get('firstName') or 
                                        p.get('legalFirstName') or 
                                        p.get('first_name') or ''
                                    )
                                    patient_last_name = (
                                        p.get('lastName') or 
                                        p.get('legalLastName') or 
                                        p.get('last_name') or ''
                                    )
                                    if patient_first_name or patient_last_name:
                                        break
                        
                        if patient_first_name or patient_last_name:
                            print(f"   Patient: {patient_first_name} {patient_last_name}")
                        
                        # Find matching pending patient
                        matched = False
                        for pending in list(pending_patients):  # Use list() to avoid modification during iteration
                            if pending.get('emr_id'):
                                continue  # Skip if already has EMR ID
                            
                            pending_first = pending.get('legalFirstName', '').strip()
                            pending_last = pending.get('legalLastName', '').strip()
                            
                            # Match by name (case insensitive)
                            name_match = False
                            if patient_first_name and patient_last_name:
                                name_match = (
                                    pending_first.lower() == patient_first_name.lower().strip() and 
                                    pending_last.lower() == patient_last_name.lower().strip()
                                )
                            elif patient_first_name:
                                name_match = pending_first.lower() == patient_first_name.lower().strip()
                            elif patient_last_name:
                                name_match = pending_last.lower() == patient_last_name.lower().strip()
                            
                            # Also check if phone numbers match (additional verification)
                            phone_match = False
                            if booking_data:
                                api_phone = booking_data.get('phone', '').strip()
                                pending_phone = pending.get('mobilePhone', '').strip()
                                if api_phone and pending_phone:
                                    # Normalize phone numbers (remove +, spaces, dashes)
                                    api_phone_norm = api_phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                                    pending_phone_norm = pending_phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                                    if api_phone_norm and pending_phone_norm and api_phone_norm == pending_phone_norm:
                                        phone_match = True
                            
                            # Match if name matches OR (phone matches and we have at least partial name match)
                            final_match = name_match or (phone_match and (patient_first_name or patient_last_name))
                            
                            # If no match but we have only one pending patient without EMR ID, use it
                            if not final_match and len([p for p in pending_patients if not p.get('emr_id')]) == 1:
                                final_match = True
                            
                            if final_match:
                                print(f"   ✅ Matched with pending patient!")
                                if name_match:
                                    print(f"      Match by name: {pending_first} {pending_last}")
                                if phone_match:
                                    print(f"      Match by phone: {pending_phone}")
                                pending['emr_id'] = emr_id
                                if booking_id:
                                    pending['booking_id'] = booking_id
                                if booking_number:
                                    pending['booking_number'] = booking_number
                                if patient_number:
                                    pending['patient_number'] = patient_number
                                await update_patient_emr_id(pending)
                                print(f"   💾 Updated patient data with EMR ID: {emr_id}")
                                # Remove from pending list
                                pending_patients.remove(pending)
                                matched = True
                                break
                        
                        if not matched and pending_patients:
                            print(f"   ⚠️  EMR ID found but no matching patient. Pending patients: {len(pending_patients)}")
                            # Try to update the most recent pending patient without EMR ID
                            for pending in reversed(pending_patients):
                                if not pending.get('emr_id'):
                                    print(f"   📝 Assigning EMR ID to most recent pending patient")
                                    pending['emr_id'] = emr_id
                                    if booking_id:
                                        pending['booking_id'] = booking_id
                                    if booking_number:
                                        pending['booking_number'] = booking_number
                                    if patient_number:
                                        pending['patient_number'] = patient_number
                                    await update_patient_emr_id(pending)
                                    print(f"   💾 Updated patient data with EMR ID: {emr_id}")
                                    pending_patients.remove(pending)
                                    break
                
                except Exception as e:
                    # Not JSON or can't parse, skip silently
                    pass
                    
        except Exception as e:
            # Ignore errors in response handler
            pass
    
    # Set up response interception
    page.on("response", handle_response)
    print("✅ API response interception enabled")
    print(f"   📡 Actively monitoring all API responses for EMR ID...")
    
    # Also set up periodic DOM checking as active backup
    async def actively_check_dom_for_emr():
        """Periodically check DOM for EMR IDs that might have appeared"""
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                if not pending_patients:
                    continue
                
                # Check the queue list for EMR IDs
                for pending in list(pending_patients):
                    if pending.get('emr_id'):
                        continue
                    
                    pending_first = pending.get('legalFirstName', '').strip()
                    pending_last = pending.get('legalLastName', '').strip()
                    
                    if not pending_first and not pending_last:
                        continue
                    
                    # Look for patient in DOM and check for EMR ID
                    emr_id = await page.evaluate("""
                        (firstName, lastName) => {
                            // Find patient name elements
                            const nameElements = document.querySelectorAll('[data-testid^="booking-patient-name-"]');
                            
                            for (const nameEl of nameElements) {
                                const text = nameEl.textContent || nameEl.innerText || '';
                                if (text.includes(firstName) && text.includes(lastName)) {
                                    // Look for EMR ID in the parent container
                                    const container = nameEl.closest('[class*="booking"], [class*="patient"], [data-testid*="booking"]');
                                    if (container) {
                                        const containerText = container.textContent || container.innerText || '';
                                        const emrMatch = containerText.match(/EMR ID[\\s:]+(\\d+)/i);
                                        if (emrMatch && emrMatch[1]) {
                                            return emrMatch[1];
                                        }
                                    }
                                }
                            }
                            return null;
                        }
                    """, pending_first, pending_last)
                    
                    if emr_id:
                        print(f"\n🔍 Found EMR ID in DOM: {emr_id}")
                        print(f"   Patient: {pending_first} {pending_last}")
                        pending['emr_id'] = emr_id
                        await update_patient_emr_id(pending)
                        print(f"   💾 Updated patient data with EMR ID: {emr_id}")
                        pending_patients.remove(pending)
            
            except Exception as e:
                # Silently continue on errors
                pass
    
    # Start active DOM monitoring
    asyncio.create_task(actively_check_dom_for_emr())
    print("✅ Active DOM monitoring started (checking every 5 seconds)")
    
    # Inject JavaScript to monitor the submit button
    monitor_script = """
    (function() {
        console.log('🔍 Setting up patient form monitor...');
        
        let isMonitoring = false;
        const monitoredButtons = new WeakSet();
        
        // Function to capture form data
        function captureFormData() {
            const formData = {};
            
            // First, try to capture the selected location from dropdown (if visible in modal)
            // Look for location dropdown in the modal
            const locationSelectors = [
                'select[name*="location"]',
                'select[id*="location"]',
                '[name*="location"]',
                '[id*="location"]',
                '[data-testid*="location"]',
                'select',
                '[role="combobox"]'
            ];
            
            // Find modal/dialog first
            const modal = document.querySelector('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
            if (modal) {
                for (const selector of locationSelectors) {
                    try {
                        const element = modal.querySelector(selector);
                        if (element) {
                            const style = window.getComputedStyle(element);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                let locationValue = '';
                                if (element.tagName.toLowerCase() === 'select') {
                                    locationValue = element.value || '';
                                } else {
                                    locationValue = element.value || element.textContent || element.innerText || '';
                                    const selected = element.querySelector('[selected], [aria-selected="true"], [class*="selected"]');
                                    if (selected) {
                                        locationValue = selected.value || selected.textContent || selected.innerText || locationValue;
                                    }
                                }
                                if (locationValue && locationValue.trim()) {
                                    formData.selectedLocation = locationValue;
                                    break;
                                }
                            }
                        }
                    } catch (e) {
                        continue;
                    }
                }
            }
            
            // Capture text fields - using actual field names and test IDs from the HTML
            const fieldMappings = [
                { key: 'legalFirstName', selectors: ['[name="firstName"]', '[data-testid="addPatientFirstName"]', 'input[name="firstName"]'] },
                { key: 'legalLastName', selectors: ['[name="lastName"]', '[data-testid="addPatientLastName"]', 'input[name="lastName"]'] },
                { key: 'mobilePhone', selectors: ['[data-testid="addPatientMobilePhone"]', '[name="phone"]', 'input[type="tel"][data-testid*="Phone"]'] },
                { key: 'dob', selectors: ['[data-testid="addPatientDob"]', '[name="birthDate"]', 'input[placeholder*="MM/DD/YYYY"]'] },
                { key: 'reasonForVisit', selectors: ['[name="reasonForVisit"]', '[data-testid*="addPatientReasonForVisit"]', '[id="reasonForVisit"]', '[data-testid="addPatientReasonForVisit-0"]', 'input[name="reasonForVisit"]'] }
            ];
            
            fieldMappings.forEach(field => {
                let value = '';
                for (const selector of field.selectors) {
                    try {
                        const element = document.querySelector(selector);
                        if (element) {
                            const style = window.getComputedStyle(element);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                value = element.value || element.textContent || '';
                                if (value && value.trim()) break;
                            }
                        }
                    } catch (e) {
                        continue;
                    }
                }
                formData[field.key] = value || '';
            });
            
            // Capture sexAtBirth dropdown - using actual field name "birthSex"
            const sexSelectors = [
                '#birthSex',
                '[id="birthSex"]',
                '[name="birthSex"]',
                '[data-testid*="birthSex"]',
                '[data-testid*="sex"]',
                'select[name="birthSex"]',
                'select[id="birthSex"]'
            ];
            
            let sexValue = '';
            for (const selector of sexSelectors) {
                try {
                    const element = document.querySelector(selector);
                    if (element) {
                        const style = window.getComputedStyle(element);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            if (element.tagName.toLowerCase() === 'select') {
                                sexValue = element.value || '';
                            } else {
                                // For Ant Design custom dropdowns, check the selection
                                // Method 1: Check for selected-value element (most reliable)
                                const selectedValueEl = element.querySelector('.ant-select-selection-selected-value');
                                if (selectedValueEl) {
                                    sexValue = (selectedValueEl.textContent || selectedValueEl.innerText || '').trim();
                                    if (sexValue) {
                                        // Also try title attribute
                                        const title = selectedValueEl.getAttribute('title');
                                        if (title) sexValue = title;
                                        break;
                                    }
                                }
                                
                                // Method 2: Check the rendered container
                                const rendered = element.querySelector('.ant-select-selection__rendered');
                                const placeholder = element.querySelector('.ant-select-selection__placeholder');
                                
                                if (rendered) {
                                    // Check if placeholder is hidden (meaning something is selected)
                                    let isPlaceholderHidden = false;
                                    if (placeholder) {
                                        const placeholderStyle = window.getComputedStyle(placeholder);
                                        isPlaceholderHidden = placeholderStyle.display === 'none';
                                    }
                                    
                                    if (isPlaceholderHidden || !placeholder) {
                                        // Get all text from rendered
                                        const allText = rendered.textContent || rendered.innerText || '';
                                        // Remove placeholder text if it exists
                                        const placeholderText = placeholder ? (placeholder.textContent || placeholder.innerText || '') : '';
                                        const cleanText = allText.replace(placeholderText, '').trim();
                                        
                                        if (cleanText && !cleanText.includes('Choose an option') && cleanText.length > 0) {
                                            sexValue = cleanText;
                                            if (sexValue) break;
                                        }
                                    }
                                }
                                
                                // Method 3: Check if dropdown is open and get selected option
                                const dropdown = element.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
                                if (dropdown) {
                                    const selectedOption = dropdown.querySelector('.ant-select-item-selected, .ant-select-item-option-selected');
                                    if (selectedOption) {
                                        sexValue = (selectedOption.textContent || selectedOption.innerText || '').trim();
                                        if (sexValue) break;
                                    }
                                }
                                
                                // Method 4: Look for hidden input
                                const hiddenInput = element.querySelector('input[type="hidden"]');
                                if (hiddenInput && hiddenInput.value) {
                                    sexValue = hiddenInput.value;
                                    if (sexValue) break;
                                }
                                
                                // Method 5: Check Ant Design's internal state
                                const antSelect = element.closest('.ant-select');
                                if (antSelect) {
                                    const hiddenInput = antSelect.querySelector('input[type="hidden"]');
                                    if (hiddenInput && hiddenInput.value) {
                                        sexValue = hiddenInput.value;
                                        if (sexValue) break;
                                    }
                                }
                                
                                // Method 6: Check data attributes
                                sexValue = element.getAttribute('data-value') || 
                                          element.getAttribute('value') || 
                                          element.getAttribute('aria-label') || '';
                                if (sexValue) break;
                            }
                            if (sexValue && sexValue.trim()) break;
                        }
                    }
                } catch (e) {
                    continue;
                }
            }
            formData.sexAtBirth = sexValue || '';
            
            return formData;
        }
        
        // Function to check if form is visible (has input fields)
        function isFormVisible() {
            const formFields = [
                '[name="firstName"]',
                '[data-testid="addPatientFirstName"]',
                '[name="lastName"]',
                '[data-testid="addPatientLastName"]',
                '[data-testid="addPatientMobilePhone"]',
                '[data-testid="addPatientDob"]'
            ];
            for (const selector of formFields) {
                try {
                    const element = document.querySelector(selector);
                    if (element) {
                        const style = window.getComputedStyle(element);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            return true;
                        }
                    }
                } catch (e) {
                    continue;
                }
            }
            return false;
        }
        
        // Function to setup button listener
        function setupButtonListener() {
            // Try to find the submit button - prioritize the specific testid
            // Look for buttons with text "Add" or submit buttons in modal
            const buttonSelectors = [
                '[data-testid="addPatientSubmitButton"]',
                'button[data-testid*="addPatient"][data-testid*="Submit"]',
                'button[data-testid*="addPatient"]',
                'button[data-testid*="submit"]',
                'button[data-testid*="Add"]'
            ];
            
            let submitButton = null;
            
            // First try specific selectors
            for (const selector of buttonSelectors) {
                try {
                    const buttons = document.querySelectorAll(selector);
                    if (buttons.length > 0) {
                        // Find the one that's visible and in a modal
                        for (const btn of buttons) {
                            const style = window.getComputedStyle(btn);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                // Check if it's in a modal/dialog
                                const modal = btn.closest('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
                                if (modal) {
                                    submitButton = btn;
                                    break;
                                }
                            }
                        }
                        if (submitButton) break;
                    }
                } catch (e) {
                    continue;
                }
            }
            
            // If not found, look for buttons with text "Add" in modal
            if (!submitButton) {
                try {
                    const modal = document.querySelector('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
                    if (modal) {
                        const buttons = modal.querySelectorAll('button');
                        for (const btn of buttons) {
                            const style = window.getComputedStyle(btn);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                const text = (btn.textContent || btn.innerText || '').trim();
                                // Look for buttons with "Add" text (but not "Add Patient" which is the opener)
                                if (text && text.toLowerCase().includes('add') && 
                                    !text.toLowerCase().includes('patient') &&
                                    text.length < 20) {
                                    submitButton = btn;
                                    break;
                                }
                                // Also check for submit type buttons
                                if (btn.type === 'submit' || btn.getAttribute('type') === 'submit') {
                                    submitButton = btn;
                                    break;
                                }
                            }
                        }
                    }
                } catch (e) {
                    // Ignore errors
                }
            }
            
            if (submitButton && !monitoredButtons.has(submitButton)) {
                console.log('✅ Found submit button, setting up listener');
                console.log('   Button text:', submitButton.textContent || submitButton.innerText);
                
                // Mark as monitored
                monitoredButtons.add(submitButton);
                
                // Add multiple listeners to ensure we catch it
                const captureAndSend = async function(e) {
                    console.log('🖱️  Submit button clicked!');
                    
                    // Capture immediately, don't wait
                    const formData = captureFormData();
                    console.log('📋 Captured form data:', formData);
                    
                    // Send to Python immediately
                    try {
                        await window.handlePatientSubmission(formData);
                    } catch (error) {
                        console.error('❌ Error calling handlePatientSubmission:', error);
                    }
                };
                
                // Add listener with capture phase (fires first)
                submitButton.addEventListener('click', captureAndSend, true);
                // Also add normal listener as backup
                submitButton.addEventListener('click', captureAndSend, false);
                // Also intercept mousedown (fires before click)
                submitButton.addEventListener('mousedown', captureAndSend, true);
                
                return true;
            }
            
            return false;
        }
        
        // Try to setup listener immediately
        setupButtonListener();
        
        // Use MutationObserver to watch for dynamically added buttons and modals
        const observer = new MutationObserver(function(mutations) {
            // Check for new buttons
            setupButtonListener();
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['data-testid', 'class', 'style']
        });
        
        // Also listen for form submit events as a fallback (non-blocking)
        document.addEventListener('submit', async function(e) {
            const form = e.target;
            if (form) {
                // Check if this form is in a modal and contains patient form fields
                const modal = form.closest('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
                if (modal) {
                    // Check if form has patient-related fields
                    const hasPatientFields = form.querySelector('[name="legalFirstName"], [id="legalFirstName"], [data-testid="legalFirstName"]') ||
                                           form.querySelector('[name="legalLastName"], [id="legalLastName"], [data-testid="legalLastName"]');
                    
                    if (hasPatientFields) {
                        console.log('📝 Form submit event detected in modal!');
                        
                        // Small delay to capture data (don't block submission)
                        setTimeout(async () => {
                            const formData = captureFormData();
                            console.log('📋 Captured form data:', formData);
                            
                            try {
                                await window.handlePatientSubmission(formData);
                            } catch (error) {
                                console.error('❌ Error calling handlePatientSubmission:', error);
                            }
                        }, 100);
                    }
                }
            }
        }, false); // Don't use capture phase, let form submit normally
        
        // Periodic check for buttons (in case MutationObserver misses something)
        setInterval(() => {
            setupButtonListener();
        }, 1000); // Check every second
        
        // Also log when modals appear
        const modalObserver = new MutationObserver(function(mutations) {
            const modal = document.querySelector('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
            if (modal) {
                console.log('📦 Modal detected, checking for buttons...');
                setupButtonListener();
            }
        });
        
        modalObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        console.log('✅ Patient form monitor initialized');
        console.log('🔍 Monitoring for form submissions...');
    })();
    """
    
    # Inject the monitoring script
    await page.evaluate(monitor_script)
    print("✅ Form monitor script injected")
    
    # Also set up console message listener to see JavaScript logs
    def handle_console(msg):
        if "Patient form" in msg.text or "Submit button" in msg.text or "Form submit" in msg.text or "Captured form" in msg.text:
            print(f"   [JS Console] {msg.text}")
    
    page.on("console", handle_console)


async def main():
    """
    Main function to run the patient form monitor.
    """
    # Get URL from environment variable - use URL as-is without appending location_ids
    url = os.getenv('SOLVHEALTH_QUEUE_URL')
    
    if not url:
        print("❌ Error: SOLVHEALTH_QUEUE_URL environment variable is not set.")
        print("   Please set it with the queue URL, e.g.:")
        print("   export SOLVHEALTH_QUEUE_URL='https://manage.solvhealth.com/queue?location_ids=AXjwbE'")
        print("   or")
        print("   export SOLVHEALTH_QUEUE_URL='https://manage.solvhealth.com/queue'")
        sys.exit(1)
    
    # Extract location_id from URL (optional - will be extracted from current page URL if not in initial URL)
    location_id = extract_location_id_from_url(url)
    
    if location_id:
        location_name = get_location_name(location_id) or f"Location {location_id}"
    else:
        location_id = None
        location_name = "Will be detected from page"
    
    print("=" * 60)
    print("🏥 Patient Form Monitor")
    print("=" * 60)
    print(f"📍 URL: {url}")
    if location_id:
        print(f"📍 Location ID: {location_id}")
        print(f"📍 Location Name: {location_name}")
    else:
        print(f"📍 Location: {location_name}")
    print("=" * 60)
    print("\n🔍 Listening for patient submissions...")
    headless = str_to_bool(os.getenv("PLAYWRIGHT_HEADLESS"))
    if headless:
        print("   (Running in headless mode)")
    else:
        print("   (The browser will open in non-headless mode)")
    print("   (Click 'Add Patient' and submit the form to capture data)")
    print("   (Press Ctrl+C to stop)\n")
    
    async with async_playwright() as p:
        # Launch browser with mode controlled via environment variable
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Navigate to the page with a less strict wait condition
            print(f"🌐 Navigating to {url}...")
            try:
                # Try with domcontentloaded first (faster, less strict)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                print("✅ Page loaded (DOM ready)")
            except PlaywrightTimeoutError:
                # If that times out, try with just load
                try:
                    await page.goto(url, wait_until="load", timeout=30000)
                    print("✅ Page loaded (load event)")
                except PlaywrightTimeoutError:
                    # Even if timeout, continue - the page might still be usable
                    print("⚠️  Page navigation timeout, but continuing anyway...")
                    print("   (The page may still be loading, but monitoring will start)")
            
            # Wait a bit for the page to fully initialize and any modals to be ready
            print("⏳ Waiting for page to initialize...")
            await asyncio.sleep(3)
            
            # Setup form monitor
            print("🔧 Setting up form monitor...")
            await setup_form_monitor(page, location_id, location_name)
            
            # Keep the script running indefinitely
            print("\n⏳ Monitoring... (Press Ctrl+C to stop)")
            print("   📝 Instructions:")
            print("      1. Click 'Add Patient' button (modal will open)")
            print("      2. Select location from dropdown in the modal")
            print("      3. Fill out the form fields that appear")
            print("      4. Click 'Add' button to submit")
            print("      5. Form data will be captured and saved automatically\n")
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping monitor...")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            await browser.close()
            print("👋 Browser closed. Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())


