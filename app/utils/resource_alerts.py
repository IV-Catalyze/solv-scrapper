"""
Resource alert utility for automatic alert creation based on resource thresholds.

This module handles checking resource usage (CPU, Memory, Disk) against configured
thresholds and automatically creates alerts when thresholds are exceeded. It also
handles automatic resolution of alerts when resources recover.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Resource thresholds configuration
RESOURCE_THRESHOLDS = {
    'cpu': {
        'warning': 80.0,
        'critical': 95.0
    },
    'memory': {
        'warning': 85.0,
        'critical': 95.0
    },
    'disk': {
        'warning': 90.0,
        'critical': 95.0
    }
}


def check_resource_thresholds(
    metadata: Optional[Dict[str, Any]],
    server_id: str
) -> List[Dict[str, Any]]:
    """
    Check resource usage against thresholds and return alerts to create.
    
    Args:
        metadata: Server metadata dict with cpuUsage, memoryUsage, diskUsage
        server_id: Server identifier
        
    Returns:
        List of alert dictionaries to create (empty if no thresholds exceeded)
    """
    if not metadata or not isinstance(metadata, dict):
        return []
    
    alerts_to_create = []
    
    # Check CPU usage
    cpu_usage = metadata.get('cpuUsage')
    if cpu_usage is not None and isinstance(cpu_usage, (int, float)):
        if cpu_usage >= RESOURCE_THRESHOLDS['cpu']['critical']:
            alerts_to_create.append({
                'resource': 'CPU',
                'usage': float(cpu_usage),
                'severity': 'critical',
                'threshold': RESOURCE_THRESHOLDS['cpu']['critical']
            })
        elif cpu_usage >= RESOURCE_THRESHOLDS['cpu']['warning']:
            alerts_to_create.append({
                'resource': 'CPU',
                'usage': float(cpu_usage),
                'severity': 'warning',
                'threshold': RESOURCE_THRESHOLDS['cpu']['warning']
            })
    
    # Check Memory usage
    memory_usage = metadata.get('memoryUsage')
    if memory_usage is not None and isinstance(memory_usage, (int, float)):
        if memory_usage >= RESOURCE_THRESHOLDS['memory']['critical']:
            alerts_to_create.append({
                'resource': 'Memory',
                'usage': float(memory_usage),
                'severity': 'critical',
                'threshold': RESOURCE_THRESHOLDS['memory']['critical']
            })
        elif memory_usage >= RESOURCE_THRESHOLDS['memory']['warning']:
            alerts_to_create.append({
                'resource': 'Memory',
                'usage': float(memory_usage),
                'severity': 'warning',
                'threshold': RESOURCE_THRESHOLDS['memory']['warning']
            })
    
    # Check Disk usage
    disk_usage = metadata.get('diskUsage')
    if disk_usage is not None and isinstance(disk_usage, (int, float)):
        if disk_usage >= RESOURCE_THRESHOLDS['disk']['critical']:
            alerts_to_create.append({
                'resource': 'Disk',
                'usage': float(disk_usage),
                'severity': 'critical',
                'threshold': RESOURCE_THRESHOLDS['disk']['critical']
            })
        elif disk_usage >= RESOURCE_THRESHOLDS['disk']['warning']:
            alerts_to_create.append({
                'resource': 'Disk',
                'usage': float(disk_usage),
                'severity': 'warning',
                'threshold': RESOURCE_THRESHOLDS['disk']['warning']
            })
    
    return alerts_to_create


def should_create_alert(
    conn,
    server_id: str,
    resource: str,
    severity: str
) -> bool:
    """
    Check if an alert should be created (avoid duplicates).
    
    Only create alert if there's no recent unresolved alert for the same
    resource and severity within the last 5 minutes.
    
    Args:
        conn: Database connection
        server_id: Server identifier
        resource: Resource name (CPU, Memory, Disk)
        severity: Alert severity (warning, critical)
        
    Returns:
        True if alert should be created, False otherwise
    """
    from psycopg2.extras import RealDictCursor
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Check for recent unresolved alerts for this server/resource/severity
        query = """
            SELECT alert_id, created_at
            FROM alerts
            WHERE source = 'server'
              AND source_id = %s
              AND resolved = FALSE
              AND severity = %s
              AND details->>'resource' = %s
              AND created_at > NOW() - INTERVAL '5 minutes'
            ORDER BY created_at DESC
            LIMIT 1
        """
        
        cursor.execute(query, (server_id, severity, resource))
        result = cursor.fetchone()
        
        # If no recent alert exists, we should create one
        return result is None
        
    except Exception as e:
        logger.warning(f"Error checking for existing alerts: {str(e)}")
        # On error, allow alert creation (fail open)
        return True
    finally:
        cursor.close()


def create_resource_alerts(
    conn,
    server_id: str,
    metadata: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Check resource thresholds and create alerts if needed.
    
    Args:
        conn: Database connection
        server_id: Server identifier
        metadata: Server metadata with resource usage
        
    Returns:
        List of created alert records
    """
    from app.api.database import save_alert
    
    created_alerts = []
    
    # Check thresholds
    alerts_to_check = check_resource_thresholds(metadata, server_id)
    
    for alert_info in alerts_to_check:
        resource = alert_info['resource']
        usage = alert_info['usage']
        severity = alert_info['severity']
        threshold = alert_info['threshold']
        
        # Check if we should create this alert (avoid duplicates)
        if not should_create_alert(conn, server_id, resource, severity):
            logger.debug(
                f"Skipping duplicate alert for {server_id} - {resource} {severity}"
            )
            continue
        
        # Create alert
        try:
            alert_dict = {
                'source': 'server',
                'source_id': server_id,
                'severity': severity,
                'message': (
                    f"{resource} usage is {usage:.1f}% "
                    f"(threshold: {threshold}%)"
                ),
                'details': {
                    'resource': resource,
                    'usage': usage,
                    'threshold': threshold,
                    'metric': resource.lower() + 'Usage'
                }
            }
            
            saved_alert = save_alert(conn, alert_dict)
            created_alerts.append(saved_alert)
            
            logger.info(
                f"Created {severity} alert for {server_id}: "
                f"{resource} usage {usage:.1f}%"
            )
            
        except Exception as e:
            logger.error(
                f"Failed to create alert for {server_id} - {resource}: {str(e)}"
            )
            # Continue with other alerts even if one fails
    
    return created_alerts


def get_unresolved_resource_alerts(
    conn,
    server_id: str,
    resource: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get unresolved alerts for a server, optionally filtered by resource.
    
    Args:
        conn: Database connection
        server_id: Server identifier
        resource: Optional resource name to filter by (CPU, Memory, Disk)
        
    Returns:
        List of unresolved alert records
    """
    from psycopg2.extras import RealDictCursor
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if resource:
            query = """
                SELECT alert_id, source, source_id, severity, message, details,
                       resolved, resolved_at, resolved_by, created_at, updated_at
                FROM alerts
                WHERE source = 'server'
                  AND source_id = %s
                  AND resolved = FALSE
                  AND details->>'resource' = %s
                ORDER BY created_at DESC
            """
            cursor.execute(query, (server_id, resource))
        else:
            query = """
                SELECT alert_id, source, source_id, severity, message, details,
                       resolved, resolved_at, resolved_by, created_at, updated_at
                FROM alerts
                WHERE source = 'server'
                  AND source_id = %s
                  AND resolved = FALSE
                  AND details->>'resource' IS NOT NULL
                ORDER BY created_at DESC
            """
            cursor.execute(query, (server_id,))
        
        results = cursor.fetchall()
        return [dict(row) for row in results]
        
    except Exception as e:
        logger.error(f"Error getting unresolved alerts: {str(e)}")
        return []
    finally:
        cursor.close()


def resolve_recovered_resource_alerts(
    conn,
    server_id: str,
    metadata: Optional[Dict[str, Any]]
) -> int:
    """
    Resolve alerts for resources that have recovered below thresholds.
    
    Args:
        conn: Database connection
        server_id: Server identifier
        metadata: Current server metadata with resource usage
        
    Returns:
        Number of alerts resolved
    """
    from app.api.database import resolve_alert
    
    if not metadata or not isinstance(metadata, dict):
        return 0
    
    resolved_count = 0
    
    # Map resources to their metric keys and warning thresholds
    resource_map = {
        'CPU': ('cpuUsage', RESOURCE_THRESHOLDS['cpu']['warning']),
        'Memory': ('memoryUsage', RESOURCE_THRESHOLDS['memory']['warning']),
        'Disk': ('diskUsage', RESOURCE_THRESHOLDS['disk']['warning']),
    }
    
    # Get all unresolved resource alerts for this server
    unresolved_alerts = get_unresolved_resource_alerts(conn, server_id)
    
    for alert in unresolved_alerts:
        details = alert.get('details')
        if not details or not isinstance(details, dict):
            continue
        
        resource = details.get('resource')
        if not resource or resource not in resource_map:
            continue
        
        metric_key, warning_threshold = resource_map[resource]
        current_usage = metadata.get(metric_key)
        
        # Check if resource has recovered (below warning threshold)
        if current_usage is not None and isinstance(current_usage, (int, float)):
            if float(current_usage) < warning_threshold:
                # Resource recovered - resolve the alert
                try:
                    alert_id = str(alert['alert_id'])
                    resolved_alert = resolve_alert(
                        conn,
                        alert_id,
                        resolved_by='system-auto-recovery'
                    )
                    resolved_count += 1
                    
                    logger.info(
                        f"Auto-resolved alert {alert_id} for {server_id} - "
                        f"{resource} recovered to {current_usage:.1f}% "
                        f"(below {warning_threshold}% threshold)"
                    )
                    
                except Exception as e:
                    logger.error(
                        f"Failed to resolve alert {alert.get('alert_id')} "
                        f"for {server_id} - {resource}: {str(e)}"
                    )
    
    return resolved_count


def process_resource_alerts(
    conn,
    server_id: str,
    metadata: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Main function to process resource alerts: create new alerts and resolve recovered ones.
    
    Args:
        conn: Database connection
        server_id: Server identifier
        metadata: Server metadata with resource usage
        
    Returns:
        Dictionary with processing results:
        - created: number of alerts created
        - resolved: number of alerts resolved
        - created_alerts: list of created alert IDs
    """
    created_alerts = create_resource_alerts(conn, server_id, metadata)
    resolved_count = resolve_recovered_resource_alerts(conn, server_id, metadata)
    
    return {
        'created': len(created_alerts),
        'resolved': resolved_count,
        'created_alerts': [str(alert['alert_id']) for alert in created_alerts]
    }
