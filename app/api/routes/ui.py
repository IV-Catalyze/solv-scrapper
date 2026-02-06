"""
UI routes for HTML page rendering.

This module contains all routes that return HTML responses for the web UI.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import HTMLResponse
from psycopg2.extras import RealDictCursor

from app.api.routes.dependencies import (
    logger,
    require_auth,
    templates,
    get_db_connection,
    resolve_location_id,
    expand_status_shortcuts,
    normalize_status,
    DEFAULT_STATUSES,
    use_remote_api_for_reads,
    fetch_remote_patients,
    filter_patients_by_search,
    get_local_patients,
    fetch_locations,
)

router = APIRouter()


@router.get(
    "/",
    summary="Render the patient dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- HTML dashboard rendered via Jinja template -->"}},
            "description": "HTML table view of the patient queue filtered by the supplied query parameters.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
        500: {"description": "Server error while fetching patient data from remote API."},
    },
)
async def root(
    request: Request,
    locationId: Optional[str] = Query(
        default=None,
        alias="locationId",
        description=(
            "Location identifier to filter patients by. Required unless DEFAULT_LOCATION_ID env var is set."
        ),
    ),
    statuses: Optional[List[str]] = Query(
        default=None,
        alias="statuses",
        description="Filter patients by status. Provide multiple values by repeating the query parameter."
    ),
    search: Optional[str] = Query(
        default=None,
        alias="search",
        description="Search patients by name, EMR ID, or phone number."
    ),
    page: Optional[int] = Query(
        default=1,
        ge=1,
        alias="page",
        description="Page number for pagination (starts at 1)."
    ),
    page_size: Optional[int] = Query(
        default=25,
        ge=1,
        le=100,
        alias="page_size",
        description="Number of records per page (1-100)."
    ),
    current_user: dict = Depends(require_auth),
):
    """
    Render the patient queue dashboard as HTML.

    Uses the remote production API when location filtering is available;
    otherwise falls back to the local database.
    """
    # Normalize locationId: convert empty strings to None
    # FastAPI may receive empty string from form submission, normalize it to None
    if locationId is not None:
        locationId = locationId.strip() if isinstance(locationId, str) else locationId
        if not locationId:
            locationId = None
    
    normalized_location_id = resolve_location_id(locationId, required=False)
    
    if statuses is None:
        normalized_statuses = DEFAULT_STATUSES.copy()
    else:
        # First expand any shortcuts like 'active'
        expanded_statuses = expand_status_shortcuts(statuses)
        normalized_statuses = [
            normalize_status(status)
            for status in expanded_statuses
            if isinstance(status, str)
        ]
        normalized_statuses = [status for status in normalized_statuses if status]
        if not normalized_statuses:
            normalized_statuses = DEFAULT_STATUSES.copy()

    # Normalize search query: handle empty strings, None, and whitespace-only strings
    if search is None:
        search_query = None
    elif isinstance(search, str):
        search_query = search.strip() if search.strip() else None
    else:
        search_query = None

    try:
        use_remote_reads = use_remote_api_for_reads()
        if use_remote_reads and normalized_location_id:
            try:
                # Fetch patients directly from production API
                all_patients = await fetch_remote_patients(normalized_location_id, normalized_statuses, None)
            except HTTPException as e:
                # If remote API fails, log error and fall back to local database
                logger.warning(f"Remote API fetch failed: {e.detail}. Falling back to local database.")
                use_remote_reads = False
                # Fall through to local database path below
            
            if use_remote_reads:
                # Apply search filter if provided
                if search_query:
                    all_patients = filter_patients_by_search(all_patients, search_query)

                # Location dropdown is limited to the current location in remote mode
                locations = [
                    {
                        "location_id": normalized_location_id,
                        "location_name": None,
                    }
                ]
            else:
                # Fall back to local database if remote fetch failed
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                try:
                    all_patients = get_local_patients(cursor, normalized_location_id, normalized_statuses, None)
                    
                    # Apply search filter if provided
                    if search_query:
                        all_patients = filter_patients_by_search(all_patients, search_query)
                    
                    locations = fetch_locations(cursor)
                finally:
                    cursor.close()
                    conn.close()
        else:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                all_patients = get_local_patients(cursor, normalized_location_id, normalized_statuses, None)
                
                # Apply search filter if provided
                if search_query:
                    all_patients = filter_patients_by_search(all_patients, search_query)
                
                locations = fetch_locations(cursor)
            finally:
                cursor.close()
                conn.close()

        # Calculate pagination
        total_count = len(all_patients)
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        current_page = min(page, total_pages) if total_pages > 0 else 1
        
        # Apply pagination
        start_idx = (current_page - 1) * page_size
        end_idx = start_idx + page_size
        patients = all_patients[start_idx:end_idx]

        status_summary: Dict[str, int] = {}
        for patient in patients:
            status = patient.get("status_class") or "unknown"
            status_summary[status] = status_summary.get(status, 0) + 1

        # Create response with no-cache headers to prevent back button showing cached page
        response = templates.TemplateResponse(
            "patients_table.html",
            {
                "request": request,
                "patients": patients,
                "location_id": normalized_location_id,
                "selected_statuses": normalized_statuses,
                "search": search_query or "",
                "page": current_page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "locations": locations,
                "default_statuses": DEFAULT_STATUSES,
                "status_summary": status_summary,
                "current_user": current_user,
                "page_title": "Patient Queue Dashboard",
                "current_page_id": "patients",
            },
        )
        
        # Add cache-control headers to prevent browser caching after logout
        # Use no-cache instead of no-store to allow history navigation while preventing stale cache
        response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/experity/chat",
    summary="Experity Mapper Chat UI",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- Experity Mapper Chat UI -->"}},
            "description": "Interactive chat UI for mapping queue entries to Experity actions.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
    },
)
async def experity_chat_ui(
    request: Request,
    current_user: dict = Depends(require_auth),
):
    """
    Render the Experity Mapper Chat UI.
    
    This page provides an interactive interface to:
    - Upload JSON queue entries
    - Send requests to the /experity/map endpoint
    - View responses with Experity actions
    
    Requires authentication - users must be logged in to access this page.
    """
    try:
        # Render template with timeout protection
        # TemplateResponse is synchronous, so we wrap it in a thread with timeout
        def render_template():
            return templates.TemplateResponse(
                "experity_chat.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "page_title": "Experity Mapper",
                    "page_subtitle": "Convert Intellivisit queue entries to Experity actions",
                    "current_page_id": "chat",
                },
            )
        
        # Use asyncio to add timeout protection
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, render_template),
            timeout=5.0  # 5 second timeout for template rendering
        )
        
        # Use no-cache instead of no-store to allow history navigation while preventing stale cache
        response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except asyncio.TimeoutError:
        logger.error("Template rendering timed out for /experity/chat")
        raise HTTPException(
            status_code=504,
            detail="Page rendering timed out. Please try again."
        )
    except FileNotFoundError as e:
        logger.error(f"Template file not found: {e}")
        raise HTTPException(
            status_code=500,
            detail="Page template not found. Please contact support."
        )
    except Exception as e:
        logger.error(f"Error rendering experity_chat template: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error loading page. Please contact support if this persists."
        )


@router.get(
    "/queue/list",
    summary="Queue List",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- Queue List UI -->"}},
            "description": "Queue list page showing queue entries with patient names, encounter IDs, and status.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
    },
)
async def queue_list_ui(
    request: Request,
    status: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status: PENDING, PROCESSING, DONE, ERROR"
    ),
    page: int = Query(
        default=1,
        ge=1,
        alias="page",
        description="Page number (1-indexed)"
    ),
    per_page: int = Query(
        default=50,
        ge=1,
        le=200,
        alias="per_page",
        description="Number of records per page (1-200)"
    ),
    current_user: dict = Depends(require_auth),
):
    """
    Render the Queue List UI.
    
    This page provides an interface to:
    - View queue entries with patient names and encounter IDs
    - Filter by status
    - View verification details for each queue entry
    
    Requires authentication - users must be logged in to access this page.
    """
    conn = None
    cursor = None
    
    try:
        # Validate status if provided
        if status and status not in ['PENDING', 'PROCESSING', 'DONE', 'ERROR']:
            status = None
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query queue table with LEFT JOIN to patients table to get patient names
        # Patient names are stored in patients table, not in encounter payload
        # Also LEFT JOIN encounters table to get original encounter_payload as fallback for createdBy
        # Note: We don't join queue_validations here to avoid errors if table doesn't exist
        # Validation existence is checked when the user clicks "View Verification"
        query = """
            SELECT 
                q.queue_id,
                q.encounter_id,
                q.emr_id,
                q.status,
                q.raw_payload as encounter_payload,
                q.created_at,
                TRIM(
                    CONCAT(
                        COALESCE(p.legal_first_name, ''), 
                        ' ', 
                        COALESCE(p.legal_last_name, '')
                    )
                ) as patient_name,
                COALESCE(
                    q.raw_payload->>'createdBy',
                    q.raw_payload->>'created_by',
                    q.raw_payload->'createdByUser'->>'email',
                    q.raw_payload->'createdByUser'->>'name',
                    q.raw_payload->'createdByUser'->>'id',
                    q.raw_payload->'createdByUser'->>'username',
                    e.encounter_payload->>'createdBy',
                    e.encounter_payload->>'created_by',
                    e.encounter_payload->'createdByUser'->>'email',
                    e.encounter_payload->'createdByUser'->>'name',
                    e.encounter_payload->'createdByUser'->>'id',
                    e.encounter_payload->'createdByUser'->>'username'
                ) as created_by
            FROM queue q
            LEFT JOIN patients p ON q.emr_id = p.emr_id
            LEFT JOIN encounters e ON q.encounter_id = e.encounter_id
        """
        params: List[Any] = []
        
        # Build WHERE clause
        where_clause = ""
        if status:
            where_clause = " WHERE q.status = %s"
            params.append(status)
        
        # Count total records for pagination
        count_query = f"SELECT COUNT(*) as total FROM queue q{where_clause}"
        cursor.execute(count_query, tuple(params))
        total_count = cursor.fetchone().get('total', 0)
        
        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
        current_page = min(page, total_pages) if total_pages > 0 else 1
        offset = (current_page - 1) * per_page
        
        # Build main query with pagination
        query = f"""
            SELECT 
                q.queue_id,
                q.encounter_id,
                q.emr_id,
                q.status,
                q.raw_payload as encounter_payload,
                q.created_at,
                TRIM(
                    CONCAT(
                        COALESCE(p.legal_first_name, ''), 
                        ' ', 
                        COALESCE(p.legal_last_name, '')
                    )
                ) as patient_name,
                COALESCE(
                    q.raw_payload->>'createdBy',
                    q.raw_payload->>'created_by',
                    q.raw_payload->'createdByUser'->>'email',
                    q.raw_payload->'createdByUser'->>'name',
                    q.raw_payload->'createdByUser'->>'id',
                    q.raw_payload->'createdByUser'->>'username',
                    e.encounter_payload->>'createdBy',
                    e.encounter_payload->>'created_by',
                    e.encounter_payload->'createdByUser'->>'email',
                    e.encounter_payload->'createdByUser'->>'name',
                    e.encounter_payload->'createdByUser'->>'id',
                    e.encounter_payload->'createdByUser'->>'username'
                ) as created_by
            FROM queue q
            LEFT JOIN patients p ON q.emr_id = p.emr_id
            LEFT JOIN encounters e ON q.encounter_id = e.encounter_id
            {where_clause}
            ORDER BY q.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.append(per_page)
        params.append(offset)
        
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        # Debug: Log created_by extraction results for first few records
        if results:
            logger.info(f"Queue list query returned {len(results)} records")
            for i, record in enumerate(results[:3], 1):
                created_by = record.get('created_by')
                encounter_id = str(record.get('encounter_id', '')) if record.get('encounter_id') else None
                logger.info(f"Record {i} (encounter {encounter_id[:8] if encounter_id else 'None'}...): created_by = {repr(created_by)}")
        
        # Get all queue_ids to check for validations
        queue_ids = [str(r.get('queue_id', '')) for r in results if r.get('queue_id')]
        
        # Check which queue entries have validations
        has_validation_set = set()
        if queue_ids:
            try:
                # Use IN clause with tuple for PostgreSQL
                placeholders = ','.join(['%s'] * len(queue_ids))
                cursor.execute(
                    f"""
                    SELECT DISTINCT queue_id 
                    FROM queue_validations 
                    WHERE queue_id IN ({placeholders})
                    """,
                    tuple(queue_ids)
                )
                validation_results = cursor.fetchall()
                has_validation_set = {str(r.get('queue_id')) for r in validation_results if r.get('queue_id')}
            except Exception as e:
                # If queue_validations table doesn't exist or error, just continue without validation info
                logger.warning(f"Could not check validation existence: {e}")
        
        # Format the results for template
        # NOTE: Screenshot checking removed from page load for performance
        # Screenshot availability is checked when user clicks "Verify" button
        # This avoids 100+ Azure Blob Storage API calls per page load
        queue_entries = []
        for record in results:
            queue_id = str(record.get('queue_id', ''))
            
            # Get encounter_id as string
            encounter_id = str(record.get('encounter_id', '')) if record.get('encounter_id') else None
            
            # Get encounter_payload (raw_payload)
            encounter_payload = record.get('encounter_payload', {})
            if isinstance(encounter_payload, str):
                try:
                    encounter_payload = json.loads(encounter_payload)
                except json.JSONDecodeError:
                    encounter_payload = {}
            elif encounter_payload is None:
                encounter_payload = {}
            
            # Screenshot checking removed from page load for performance
            # Screenshot availability is checked when user clicks "Verify" button
            # This avoids 100+ Azure Blob Storage API calls per page load
            has_screenshots = None  # Will be checked on-demand when user clicks Verify
            screenshot_error = None
            
            # Get patient_name from JOIN result, handling empty strings and NULL
            patient_name = record.get('patient_name')
            if patient_name:
                patient_name = str(patient_name).strip()
                if not patient_name:
                    patient_name = None
            else:
                patient_name = None
            
            # Get created_by from record (same as validation page - no processing)
            # This extracts the encounter creator, not the validation creator
            created_by = record.get('created_by')
            # Handle empty strings - convert to None so template shows "—" instead of blank
            if created_by is not None and isinstance(created_by, str) and not created_by.strip():
                created_by = None
            
            # Format created_at - send as ISO format with UTC timezone for client-side conversion
            created_at = record.get('created_at')
            if created_at:
                if isinstance(created_at, datetime):
                    # If timezone-naive, assume UTC (common practice for PostgreSQL TIMESTAMP)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    # Convert to ISO format with timezone info
                    created_at = created_at.isoformat()
                else:
                    created_at = str(created_at)
            
            # Check if this queue entry has validations
            has_validation = queue_id in has_validation_set
            
            queue_entry_dict = {
                'queue_id': queue_id,
                'encounter_id': encounter_id,
                'emr_id': str(record.get('emr_id')) if record.get('emr_id') else None,
                'status': record.get('status', 'PENDING'),
                'created_at': created_at,
                'patient_name': patient_name,
                'created_by': created_by,
                'encounter_payload': encounter_payload,
                'has_validation': has_validation,
                # has_screenshots and screenshot_error removed - checked on-demand when user clicks Verify
            }
            queue_entries.append(queue_entry_dict)
            
            # Debug: Log first few entries to verify created_by is in dict
            if len(queue_entries) <= 3:
                logger.info(f"Queue entry {len(queue_entries)}: encounter_id={encounter_id[:8] if encounter_id else 'None'}..., created_by={repr(queue_entry_dict.get('created_by'))}, has_created_by_key={'created_by' in queue_entry_dict}")
        
        # Calculate pagination metadata
        has_next = current_page < total_pages
        has_prev = current_page > 1
        
        # Calculate page numbers to display (5 pages around current)
        start_page = max(1, current_page - 2)
        end_page = min(total_pages, current_page + 2)
        page_numbers = list(range(start_page, end_page + 1))
        
        # Debug: Log what's being passed to template
        if queue_entries:
            sample_entry = queue_entries[0]
            logger.info(f"Passing {len(queue_entries)} queue entries to template. Sample entry keys: {list(sample_entry.keys())}")
            logger.info(f"Sample entry created_by: {repr(sample_entry.get('created_by'))}")
            # Count entries with created_by
            entries_with_created_by = sum(1 for e in queue_entries if e.get('created_by'))
            logger.info(f"Entries with created_by data: {entries_with_created_by}/{len(queue_entries)}")
        
        response = templates.TemplateResponse(
            "queue_list.html",
            {
                "request": request,
                "current_user": current_user,
                "queue_entries": queue_entries,
                "status_filter": status,
                "total_count": total_count,
                "current_page": current_page,  # Integer for pagination
                "per_page": per_page,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
                "page_numbers": page_numbers,
                "start_page": start_page,
                "end_page": end_page,
                "page_title": "Encounters",
                "current_page_id": "encounters",  # String for navigation highlighting
            },
        )
        # Use no-cache instead of no-store to allow history navigation while preventing stale cache
        response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
        
    except Exception as e:
        logger.error(f"Error rendering queue list: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error loading queue list: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get(
    "/summaries/list",
    summary="Summaries List",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- Summaries List UI -->"}},
            "description": "Summaries list page showing all summaries.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
    },
)
async def summaries_list_ui(
    request: Request,
    emrId: Optional[str] = Query(
        default=None,
        alias="emrId",
        description="Filter by EMR ID"
    ),
    page: int = Query(
        default=1,
        ge=1,
        alias="page",
        description="Page number (1-indexed)"
    ),
    per_page: int = Query(
        default=50,
        ge=1,
        le=200,
        alias="per_page",
        description="Number of records per page (1-200)"
    ),
    current_user: dict = Depends(require_auth),
):
    """
    Render the Summaries List UI.
    
    This page provides an interface to:
    - View all summaries with patient names and encounter IDs
    - Filter by EMR ID
    - View summary notes with pagination
    
    Requires authentication - users must be logged in to access this page.
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build where clause
        where_clause = ""
        params: List[Any] = []
        
        if emrId:
            where_clause = "WHERE s.emr_id = %s"
            params.append(emrId)
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM summaries s {where_clause}"
        cursor.execute(count_query, tuple(params))
        total_count = cursor.fetchone()['total']
        
        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1
        current_page = min(page, total_pages) if total_pages > 0 else 1
        offset = (current_page - 1) * per_page
        
        # Build main query with pagination - join with patients to get patient name
        query = f"""
            SELECT 
                s.emr_id,
                s.encounter_id,
                s.note,
                s.created_at,
                s.updated_at,
                TRIM(
                    CONCAT(
                        COALESCE(p.legal_first_name, ''), 
                        ' ', 
                        COALESCE(p.legal_last_name, '')
                    )
                ) as patient_name
            FROM summaries s
            LEFT JOIN patients p ON s.emr_id = p.emr_id
            {where_clause}
            ORDER BY s.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.append(per_page)
        params.append(offset)
        
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        # Format summaries for template
        summary_list = []
        for r in results:
            # Format created_at
            created_at = r.get('created_at')
            if created_at:
                if isinstance(created_at, datetime):
                    created_at = created_at.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    created_at = str(created_at)
            
            # Format updated_at
            updated_at = r.get('updated_at')
            if updated_at:
                if isinstance(updated_at, datetime):
                    updated_at = updated_at.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    updated_at = str(updated_at)
            
            # Get patient name
            patient_name = r.get('patient_name')
            if patient_name:
                patient_name = str(patient_name).strip()
                if not patient_name:
                    patient_name = None
            else:
                patient_name = None
            
            summary_list.append({
                'emrId': r.get('emr_id'),
                'encounterId': str(r.get('encounter_id')) if r.get('encounter_id') else None,
                'note': r.get('note', ''),
                'createdAt': created_at,
                'updatedAt': updated_at,
                'patientName': patient_name or '—',
            })
        
        # Calculate page numbers to display (10 pages around current)
        max_visible = 10
        start_page = max(1, current_page - max_visible // 2)
        end_page = min(total_pages, start_page + max_visible - 1)
        if end_page - start_page < max_visible - 1:
            start_page = max(1, end_page - max_visible + 1)
        
        page_numbers = list(range(start_page, end_page + 1))
        
        response = templates.TemplateResponse(
            "summaries_list.html",
            {
                "request": request,
                "current_user": current_user,
                "summaries": summary_list,
                "emrId_filter": emrId,
                "total_count": total_count,
                "current_page": current_page,
                "per_page": per_page,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
                "page_numbers": page_numbers,
                "start_page": start_page,
                "end_page": end_page,
                "page_title": "Summaries",
                "current_page_id": "summaries",
            },
        )
        # Use no-cache instead of no-store to allow history navigation while preventing stale cache
        response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
        
    except Exception as e:
        logger.error(f"Error rendering summaries list: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error loading summaries list: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get(
    "/images/",
    summary="Images Gallery",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- Images Gallery UI -->"}},
            "description": "Images gallery page with folder navigation.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
    },
)
async def images_gallery(
    request: Request,
    current_user: dict = Depends(require_auth),
):
    """
    Render the Images Gallery UI.
    
    This page provides an interface to:
    - Browse folders and images in Azure Blob Storage
    - Navigate through folder hierarchy
    - View image thumbnails and full-size images
    
    Requires authentication - users must be logged in to access this page.
    """
    response = templates.TemplateResponse(
        "images_gallery.html",
        {
            "request": request,
            "current_user": current_user,
            "page_title": "Experity Screenshots",
            "page_subtitle": "Browse images and folders from Experity",
            "current_page_id": "images",
        },
    )
    # Use no-cache instead of no-store to allow history navigation while preventing stale cache
    response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get(
    "/emr/validation",
    summary="EMR Image Validation",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- EMR Image Validation UI -->"}},
            "description": "EMR image validation tool for comparing JSON responses against screenshots.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
    },
)
async def emr_validation_ui(
    request: Request,
    current_user: dict = Depends(require_auth),
):
    """
    Render the EMR Image Validation UI.
    
    This page provides an interface to:
    - Upload EMR screenshots
    - Paste JSON responses
    - Validate JSON against screenshots using Azure OpenAI GPT-4o
    - View validation results with detailed comparisons
    
    Requires authentication - users must be logged in to access this page.
    """
    # Hardcoded configuration
    project_endpoint = "https://iv-catalyze-openai.services.ai.azure.com/api/projects/IV-Catalyze-OpenAI-project"
    agent_name = "ImageMapper"
    
    response = templates.TemplateResponse(
        "emr_validation.html",
        {
            "request": request,
            "project_endpoint": project_endpoint,
            "agent_name": agent_name,
            "current_user": current_user,
            "page_title": "EMR Image Validation",
            "page_subtitle": "Compare JSON response against EMR screenshot",
            "show_navigation": False,
            "show_user_menu": False,
        },
    )
    # Use no-cache instead of no-store to allow history navigation while preventing stale cache
    response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get(
    "/dashboard",
    summary="Health Dashboard UI",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- Health Dashboard UI -->"}},
            "description": "Health dashboard showing system status, servers, and VMs with auto-refresh.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
    },
)
async def health_dashboard_ui(
    request: Request,
    current_user: dict = Depends(require_auth),
):
    """
    Render the Health Dashboard UI.
    
    This page provides a comprehensive view of:
    - Overall system status (healthy, degraded, unhealthy)
    - System-wide statistics (servers, VMs, processing status)
    - Server details with expandable VM lists
    - Real-time metrics (CPU, memory, disk usage)
    - Auto-refreshes every 30 seconds
    
    Requires authentication - users must be logged in to access this page.
    """
    response = templates.TemplateResponse(
        "health_dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "page_title": "Health Dashboard",
            "page_subtitle": "System health monitoring",
            "show_navigation": True,
            "show_user_menu": True,
            "current_page_id": "health-dashboard",
        },
    )
    # Use no-cache instead of no-store to allow history navigation while preventing stale cache
    response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get(
    "/alerts/dashboard",
    summary="Alerts Dashboard UI",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- Alerts Dashboard UI -->"}},
            "description": "Alerts dashboard showing all system alerts with filtering and resolution capabilities.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
    },
)
async def alerts_dashboard_ui(
    request: Request,
    current_user: dict = Depends(require_auth),
):
    """
    Render the Alerts Dashboard UI.
    
    This page provides a comprehensive view of:
    - All system alerts (from vm, server, workflow, monitor sources)
    - Filtering by resolved status, severity, and source
    - Quick resolve actions for unresolved alerts
    - Real-time alert status with auto-refresh
    - Color-coded severity indicators
    
    Requires authentication - users must be logged in to access this page.
    """
    response = templates.TemplateResponse(
        "alerts_list.html",
        {
            "request": request,
            "current_user": current_user,
            "page_title": "Alerts Dashboard",
            "page_subtitle": "System alerts and notifications",
            "show_navigation": True,
            "show_user_menu": True,
            "current_page_id": "alerts",
        },
    )
    # Use no-cache instead of no-store to allow history navigation while preventing stale cache
    response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

