"""
Queue validation routes for managing queue entry validations.

This module contains all routes related to queue entry validation and manual validation workflows.
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Depends, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from psycopg2.extras import RealDictCursor
import psycopg2

from app.api.routes.dependencies import (
    logger,
    require_auth,
    templates,
    get_db_connection,
)

router = APIRouter()

# Note: Functions find_hpi_image_by_complaint, find_encounter_image, get_image_bytes_from_blob, 
# and get_content_type_from_blob_name are imported from app.api.routes module at function level 
# to avoid circular imports. They are used directly in the code.


@router.get(
    "/queue/{queue_id}/validation",

    tags=["Queue"],

    summary="Get validation result for a queue entry",

    response_model=Dict[str, Any],

    include_in_schema=False,

    responses={

        200: {"description": "Validation result found"},

        404: {"description": "No validation found for this queue entry"},

        303: {"description": "Redirect to login page if not authenticated."},

    },

)

async def get_queue_validation(

    queue_id: str,

    request: Request,

    current_user: dict = Depends(require_auth)

) -> Dict[str, Any]:

    """

    Get validation results for a queue entry.

    

    Returns multiple validations (one per complaint):

    - validations: Array of validation objects, each with:

      - complaint_id: The complaint ID

    - validation_result: The validation results from emr/validate

      - hpi_image_path: Path to the HPI image used for validation

    - experity_action: The experityAction from queue.parsed_payload (for reference)

    - encounter_id: The encounter ID

    

    Returns 404 if no validation exists for this queue_id.

    """

    conn = None

    cursor = None

    

    try:

        conn = get_db_connection()

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        

        # Get all validation results for this queue (one per complaint)

        cursor.execute(

            """

            SELECT 

                qv.validation_id,

                qv.complaint_id,

                qv.validation_result,

                qv.encounter_id,

                q.parsed_payload->'experityAction' as experity_action_1,

                q.parsed_payload->'experityActions' as experity_action_2

            FROM queue_validations qv

            JOIN queue q ON qv.queue_id = q.queue_id

            WHERE qv.queue_id = %s

            ORDER BY qv.created_at ASC

            """,

            (queue_id,)

        )

        results = cursor.fetchall()

        

        if not results or len(results) == 0:

            raise HTTPException(

                status_code=404,

                detail=f"No validation found for queue_id: {queue_id}"

            )

        

        # Get experity_action (could be in either key) - use first result

        experity_action = results[0].get('experity_action_1') or results[0].get('experity_action_2')

        

        if isinstance(experity_action, str):

            try:

                experity_action = json.loads(experity_action)

            except json.JSONDecodeError:

                experity_action = None

        

        encounter_id_str = str(results[0].get('encounter_id', ''))

        

        # Build validations array

        validations = []

        for result in results:

            complaint_id = result.get('complaint_id')

            complaint_id_str = str(complaint_id) if complaint_id else None

        

        # Parse JSONB fields if they're strings

        validation_result = result.get('validation_result')

        if isinstance(validation_result, str):

            try:

                validation_result = json.loads(validation_result)

            except json.JSONDecodeError:

                validation_result = {}

        

            # Find HPI image path for this specific complaint

            # complaint_id is always required (guaranteed by azure_ai_agent_client.py)

            hpi_image_path = None

            if complaint_id_str:

                hpi_image_path = find_hpi_image_by_complaint(encounter_id_str, complaint_id_str)

            else:

                logger.warning(f"Validation missing complaint_id for queue_id: {queue_id}, validation_id: {result.get('validation_id')}")

                # Should not happen, but log warning if it does

            

            validations.append({

                "complaint_id": complaint_id_str,

                "validation_result": validation_result,

                "hpi_image_path": hpi_image_path

            })

        

        return {

            "validations": validations,

            "experity_action": experity_action,

            "encounter_id": encounter_id_str

        }

        

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Error fetching validation for queue_id {queue_id}: {str(e)}", exc_info=True)

        raise HTTPException(

            status_code=500,

            detail=f"Internal server error: {str(e)}"

        )

    finally:

        if cursor:

            cursor.close()

        if conn:

            conn.close()




@router.get(

    "/queue/validation/{encounter_id}",

    summary="Validation Page",

    response_class=HTMLResponse,

    include_in_schema=False,

    responses={

        200: {"description": "Manual validation page"},

        400: {"description": "Error with validation (e.g., no screenshots, no complaints)"},

        404: {"description": "Queue entry not found for encounter_id"},

        303: {"description": "Redirect to login page if not authenticated."},

    },

)

async def manual_validation_page(

    encounter_id: str,

    request: Request,

    current_user: dict = Depends(require_auth)

):

    """

    Render the manual validation page for an encounter.

    Shows complaints as tabs with fields and radio buttons for manual validation.

    Returns JSON error if validation cannot proceed (no screenshots, no complaints, etc.).

    """

    conn = None

    cursor = None

    

    try:

        conn = get_db_connection()

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        

        # Fetch queue entry by encounter_id

        cursor.execute(

            """

            SELECT 

                queue_id,

                encounter_id,

                parsed_payload

            FROM queue

            WHERE encounter_id = %s

            ORDER BY created_at DESC

            LIMIT 1

            """,

            (encounter_id,)

        )

        queue_entry = cursor.fetchone()

        

        if not queue_entry:

            # Return HTML page with alert and redirect

            error_message = f"Queue entry not found for encounter_id: {encounter_id}"

            # Escape single quotes in error message

            error_message_escaped = error_message.replace("'", "\\'")

            return HTMLResponse(

                content=f"""<!DOCTYPE html>

<html>

<head><title>Error</title></head>

<body>

    <script>

        alert('Queue Entry Not Found\\n\\n{error_message_escaped}');

        window.location.href = '/queue/list';

    </script>

</body>

</html>""",

                status_code=404

            )

        

        queue_id = str(queue_entry.get('queue_id'))

        parsed_payload = queue_entry.get('parsed_payload')

        

        # Extract experityActions from parsed_payload

        experity_actions = None

        if isinstance(parsed_payload, dict):

            experity_actions = parsed_payload.get('experityActions') or parsed_payload.get('experityAction')

        

        # Handle legacy array format

        if isinstance(experity_actions, list) and len(experity_actions) > 0:

            experity_actions = experity_actions[0]

        

        if not experity_actions or not isinstance(experity_actions, dict):

            # Return HTML page with alert and redirect

            error_message = f"No experityActions found for encounter_id: {encounter_id}"

            error_message_escaped = error_message.replace("'", "\\'")

            return HTMLResponse(

                content=f"""<!DOCTYPE html>

<html>

<head><title>Error</title></head>

<body>

    <script>

        alert('No Experity Actions Found\\n\\n{error_message_escaped}');

        window.location.href = '/queue/list';

    </script>

</body>

</html>""",

                status_code=400

            )

        

        # Get complaints array

        complaints = experity_actions.get('complaints', [])

        if not complaints or not isinstance(complaints, list) or len(complaints) == 0:

            # Return HTML page with alert and redirect

            error_message = f"No complaints found for encounter_id: {encounter_id}"

            error_message_escaped = error_message.replace("'", "\\'")

            return HTMLResponse(

                content=f"""<!DOCTYPE html>

<html>

<head><title>Error</title></head>

<body>

    <script>

        alert('No Complaints Found\\n\\n{error_message_escaped}');

        window.location.href = '/queue/list';

    </script>

</body>

</html>""",

                status_code=400

            )

        

        # Check if screenshots exist for all complaints

        complaints_with_screenshots = []

        complaints_without_screenshots = []

        

        for complaint in complaints:

            complaint_id = complaint.get('complaintId')

            if not complaint_id:

                continue

            

            complaint_id_str = str(complaint_id)

            hpi_image_path = find_hpi_image_by_complaint(encounter_id, complaint_id_str)

            

            if hpi_image_path:

                complaints_with_screenshots.append(complaint)

            else:

                complaints_without_screenshots.append(complaint)

        

        # If no screenshots found for any complaint, return JSON error (no redirect)

        if len(complaints_with_screenshots) == 0:

            error_message = f"No HPI screenshots found for encounter_id: {encounter_id}. Validation requires screenshots to compare with data."

            return JSONResponse(

                status_code=400,

                content={

                    "error": "No Screenshots Available",

                    "message": error_message

                }

            )

        

        # Use only complaints with screenshots

        complaints = complaints_with_screenshots

        

        # Fetch existing validations for this queue

        existing_validations = {}

        validation_dates = {}  # Store validation dates per complaint

        try:

            cursor.execute(

                """

                SELECT 

                    complaint_id, 

                    validation_result, 

                    COALESCE(updated_at, created_at) as last_validation_date

                FROM queue_validations

                WHERE queue_id = %s AND complaint_id IS NOT NULL

                """,

                (queue_id,)

            )

            validation_results = cursor.fetchall()

            for v_result in validation_results:

                complaint_id_from_db = str(v_result.get('complaint_id')) if v_result.get('complaint_id') else None

                if complaint_id_from_db:

                    validation_result = v_result.get('validation_result')

                    if isinstance(validation_result, str):

                        try:

                            validation_result = json.loads(validation_result)

                        except json.JSONDecodeError:

                            validation_result = {}

                    # Extract manual validation field_validations if exists

                    manual_validation = validation_result.get('manual_validation', {})

                    field_validations = manual_validation.get('field_validations', {})

                    existing_validations[complaint_id_from_db] = field_validations

                    

                    # Store validation date (already computed by SQL COALESCE)

                    last_validation_date = v_result.get('last_validation_date')

                    if last_validation_date:

                        validation_dates[complaint_id_from_db] = last_validation_date

        except Exception as e:

            logger.warning(f"Could not fetch existing validations: {e}")

        

        # Build complaints data with HPI image paths and existing validations

        complaints_data = []

        for complaint in complaints:

            complaint_id = complaint.get('complaintId')

            if not complaint_id:

                continue  # Skip complaints without complaintId

            

            complaint_id_str = str(complaint_id)

            

            # Find HPI image for this complaint - verify it actually exists

            hpi_image_path = find_hpi_image_by_complaint(encounter_id, complaint_id_str)

            

            # Double-check: if hpi_image_path was set but image doesn't actually exist, clear it

            if hpi_image_path:

                # Verify the image actually exists in blob storage

                try:

                    from app.utils.azure_blob_client import get_blob_client

                    blob_client = get_blob_client()

                    if not blob_client.blob_exists(hpi_image_path):

                        logger.warning(f"HPI image path found but blob doesn't exist: {hpi_image_path}")

                        hpi_image_path = None

                except Exception as e:

                    logger.warning(f"Could not verify blob existence for {hpi_image_path}: {e}")

                    # If we can't verify, assume it exists (don't block validation)

            

            # Only add complaint if it has a valid screenshot

            if not hpi_image_path:

                logger.warning(f"Skipping complaint {complaint_id_str} - no valid screenshot found")

                continue

            

            # Extract curated fields for validation

            curated_fields = {

                "mainProblem": complaint.get('mainProblem', ''),

                "bodyAreaKey": complaint.get('bodyAreaKey', ''),

                "notesFreeText": complaint.get('notesFreeText', ''),

                "quality": complaint.get('notesPayload', {}).get('quality', []),

                "severity": complaint.get('notesPayload', {}).get('severity', None)

            }

            

            # Get existing validation for this complaint (if any)

            existing_validation = existing_validations.get(complaint_id_str, {})

            has_existing_validation = bool(existing_validation)

            

            # Get last validation date for this complaint (if any)

            last_validation_date = validation_dates.get(complaint_id_str)

            # Convert datetime to formatted string for JSON serialization and display

            last_validation_date_str = None

            if last_validation_date:

                if isinstance(last_validation_date, datetime):

                    # Format as "Jan 21, 2025 at 10:30 AM" for display

                    last_validation_date_str = last_validation_date.strftime('%b %d, %Y at %I:%M %p')

                else:

                    last_validation_date_str = str(last_validation_date)

            

            complaints_data.append({

                "complaint_id": complaint_id_str,

                "complaint_data": complaint,

                "curated_fields": curated_fields,

                "hpi_image_path": hpi_image_path,

                "existing_validation": existing_validation,

                "has_existing_validation": has_existing_validation,

                "last_validation_date": last_validation_date_str  # Use formatted string

            })

        

        if not complaints_data:

            # Return JSON error (no redirect) if no valid complaints with screenshots

            error_message = f"No valid complaints with screenshots found for encounter_id: {encounter_id}. Validation requires screenshots to compare with data."

            return JSONResponse(

                status_code=400,

                content={

                    "error": "No Screenshots Available",

                    "message": error_message

                }

            )

        

        return templates.TemplateResponse(

            "queue_validation_manual.html",

            {

                "request": request,

                "encounter_id": encounter_id,

                "queue_id": queue_id,

                "complaints": complaints_data,

                "current_user": current_user,

                "page_title": "Encounter Validation",

                "page_subtitle": f"Encounter ID: {encounter_id}",

                "show_navigation": False,

                "show_user_menu": False,

            }

        )

        

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Error loading manual validation page for encounter_id {encounter_id}: {str(e)}", exc_info=True)

        raise HTTPException(

            status_code=500,

            detail=f"Internal server error: {str(e)}"

        )

    finally:

        if cursor:

            cursor.close()

        if conn:

            conn.close()




@router.post(

    "/queue/validation/{encounter_id}/save",

    summary="Save Manual Validation",

    include_in_schema=False,

    responses={

        200: {"description": "Manual validation saved successfully"},

        400: {"description": "Invalid request data"},

        404: {"description": "Queue entry not found"},

        303: {"description": "Redirect to login page if not authenticated."},

    },

)

async def save_manual_validation(

    encounter_id: str,

    request: Request,

    current_user: dict = Depends(require_auth)

):

    """

    Save manual validation results for a complaint.

    Expects JSON body with complaint_id and field_validations.

    """

    try:

        body = await request.json()

        complaint_id = body.get('complaint_id')

        field_validations = body.get('field_validations', {})

        

        if not complaint_id:

            raise HTTPException(

                status_code=400,

                detail="complaint_id is required"

            )

        

        if not field_validations:

            raise HTTPException(

                status_code=400,

                detail="field_validations is required"

            )

        

        conn = get_db_connection()

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        

        try:

            # Get queue_id from encounter_id

            cursor.execute(

                "SELECT queue_id, encounter_id FROM queue WHERE encounter_id = %s LIMIT 1",

                (encounter_id,)

            )

            queue_entry = cursor.fetchone()

            

            if not queue_entry:

                raise HTTPException(

                    status_code=404,

                    detail=f"Queue entry not found for encounter_id: {encounter_id}"

                )

            

            queue_id = str(queue_entry.get('queue_id'))

            encounter_id_from_db = str(queue_entry.get('encounter_id'))

            

            # Calculate overall status from field validations

            # PASS = all correct, PARTIAL = some correct, FAIL = all incorrect

            all_values = list(field_validations.values())

            correct_count = sum(1 for v in all_values if v == 'correct')

            total_count = len(all_values)

            

            if correct_count == total_count:

                overall_status = "PASS"

            elif correct_count == 0:

                overall_status = "FAIL"

            else:

                overall_status = "PARTIAL"

            

            # Build manual validation result

            manual_validation_result = {

                "overall_status": overall_status,

                "manual_validation": {

                    "field_validations": field_validations,

                    "validated_by": current_user.get('username', 'unknown'),

                    "validated_at": datetime.now(timezone.utc).isoformat()

                },

                "field_summary": {

                    "total_fields": total_count,

                    "correct_fields": correct_count,

                    "incorrect_fields": total_count - correct_count

                }

            }

            

            # Save using existing save_validation_result function

            save_validation_result(

                conn,

                queue_id,

                encounter_id_from_db,

                manual_validation_result,

                complaint_id

            )

            

            return {

                "success": True,

                "message": "Manual validation saved successfully",

                "overall_status": overall_status

            }

            

        finally:

            cursor.close()

            conn.close()

            

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Error saving manual validation for encounter_id {encounter_id}: {str(e)}", exc_info=True)

        raise HTTPException(

            status_code=500,

            detail=f"Internal server error: {str(e)}"

        )




@router.get(

    "/queue/{queue_id}/validation/image",

    tags=["Queue"],

    summary="Get validation screenshot image",

    include_in_schema=False,

    responses={

        200: {"description": "Image retrieved successfully"},

        404: {"description": "No validation or image found"},

        303: {"description": "Redirect to login page if not authenticated."},

    },

)

async def get_queue_validation_image(

    queue_id: str,

    request: Request,

    complaint_id: Optional[str] = Query(None, description="Complaint ID for complaint-specific HPI image"),

    current_user: dict = Depends(require_auth)

):

    """

    Get the HPI screenshot image used for validation.

    If complaint_id is provided, returns the complaint-specific HPI image.

    Otherwise, returns the first complaint's HPI image found.

    Uses session authentication for UI access.

    

    Note: complaint_id is always present in new validations (guaranteed by azure_ai_agent_client.py).

    """

    conn = None

    cursor = None

    

    try:

        conn = get_db_connection()

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        

        # First, get encounter_id from queue table (more reliable than queue_validations)

        cursor.execute(

            """

            SELECT encounter_id

            FROM queue

            WHERE queue_id = %s

            LIMIT 1

            """,

            (queue_id,)

        )

        queue_result = cursor.fetchone()

        

        if not queue_result:

            raise HTTPException(

                status_code=404,

                detail=f"Queue entry not found for queue_id: {queue_id}"

            )

        

        encounter_id_str = str(queue_result['encounter_id'])

        

        # complaint_id is required for finding complaint-specific HPI image

        if not complaint_id:

            raise HTTPException(

                status_code=400,

                detail="complaint_id parameter is required for complaint-specific HPI image"

            )

        

        # Find HPI image path using encounter_id and complaint_id

        hpi_image_path = find_hpi_image_by_complaint(encounter_id_str, complaint_id)

        

        if not hpi_image_path:

            raise HTTPException(

                status_code=404,

                detail=f"HPI image not found for encounter_id: {encounter_id_str} and complaint_id: {complaint_id}"

            )

        

        # Get image bytes

        image_bytes = get_image_bytes_from_blob(hpi_image_path)

        

        if not image_bytes:

            raise HTTPException(

                status_code=404,

                detail=f"Failed to load image from: {hpi_image_path}"

            )

        

        # Determine content type from file extension

        content_type = get_content_type_from_blob_name(hpi_image_path)

        

        # Return image

        from fastapi.responses import Response

        return Response(

            content=image_bytes,

            media_type=content_type,

            headers={

                "Cache-Control": "public, max-age=3600",

            }

        )

        

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Error fetching validation image for queue_id {queue_id}: {str(e)}", exc_info=True)

        raise HTTPException(

            status_code=500,

            detail=f"Internal server error: {str(e)}"

        )

    finally:

        if cursor:

            cursor.close()

        if conn:

            conn.close()


@router.get(

    "/queue/validation/{encounter_id}/image/icd",

    tags=["Queue"],

    summary="Get ICD screenshot image",

    include_in_schema=False,

    responses={

        200: {"description": "Image retrieved successfully"},

        404: {"description": "Image not found"},

        303: {"description": "Redirect to login page if not authenticated."},

    },

)

async def get_icd_image(

    encounter_id: str,

    request: Request,

    current_user: dict = Depends(require_auth)

):

    """

    Get the ICD screenshot image for an encounter.

    Uses session authentication for UI access.

    """

    try:
        # Import helper functions from app.api.routes to avoid circular imports
        from app.api.routes import find_encounter_image, get_image_bytes_from_blob, get_content_type_from_blob_name

        # Find ICD image path using encounter_id
        icd_image_path = find_encounter_image(encounter_id, "icd")

        

        if not icd_image_path:

            raise HTTPException(

                status_code=404,

                detail=f"ICD image not found for encounter_id: {encounter_id}"

            )

        

        # Get image bytes
        image_bytes = get_image_bytes_from_blob(icd_image_path)

        

        if not image_bytes:

            raise HTTPException(

                status_code=404,

                detail=f"Failed to load image from: {icd_image_path}"

            )

        

        # Determine content type from file extension
        content_type = get_content_type_from_blob_name(icd_image_path)

        

        # Return image
        from fastapi.responses import Response

        return Response(

            content=image_bytes,

            media_type=content_type,

            headers={

                "Cache-Control": "public, max-age=3600",

            }

        )

        

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Error fetching ICD image for encounter_id {encounter_id}: {str(e)}", exc_info=True)

        raise HTTPException(

            status_code=500,

            detail=f"Internal server error: {str(e)}"

        )


@router.get(

    "/queue/validation/{encounter_id}/image/historian",

    tags=["Queue"],

    summary="Get Historian screenshot image",

    include_in_schema=False,

    responses={

        200: {"description": "Image retrieved successfully"},

        404: {"description": "Image not found"},

        303: {"description": "Redirect to login page if not authenticated."},

    },

)

async def get_historian_image(

    encounter_id: str,

    request: Request,

    current_user: dict = Depends(require_auth)

):

    """

    Get the Historian screenshot image for an encounter.

    Uses session authentication for UI access.

    """

    try:
        # Import helper functions from app.api.routes to avoid circular imports
        from app.api.routes import find_encounter_image, get_image_bytes_from_blob, get_content_type_from_blob_name

        # Find Historian image path using encounter_id
        historian_image_path = find_encounter_image(encounter_id, "historian")

        

        if not historian_image_path:

            raise HTTPException(

                status_code=404,

                detail=f"Historian image not found for encounter_id: {encounter_id}"

            )

        

        # Get image bytes
        image_bytes = get_image_bytes_from_blob(historian_image_path)

        

        if not image_bytes:

            raise HTTPException(

                status_code=404,

                detail=f"Failed to load image from: {historian_image_path}"

            )

        

        # Determine content type from file extension
        content_type = get_content_type_from_blob_name(historian_image_path)

        

        # Return image
        from fastapi.responses import Response

        return Response(

            content=image_bytes,

            media_type=content_type,

            headers={

                "Cache-Control": "public, max-age=3600",

            }

        )

        

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Error fetching Historian image for encounter_id {encounter_id}: {str(e)}", exc_info=True)

        raise HTTPException(

            status_code=500,

            detail=f"Internal server error: {str(e)}"

        )


