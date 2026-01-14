"""
Lab Orders Mapper - Extract and map lab orders from encounter orders.

This module provides deterministic extraction of lab orders from encounter orders array,
with a preserve-all-fields approach to ensure no data is lost.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def extract_lab_orders(encounter_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract lab orders from encounter.orders array.
    
    Strategy (preserve-all-fields):
    1. For each order, start with source order (preserves ALL fields including unknown ones)
    2. Map known fields explicitly (ensures correct field names)
    3. Additional fields are automatically preserved
    
    Known fields mapped:
    - orderId: From order.id or order.orderId
    - name: From order.name or order.orderName
    - status: From order.status
    - priority: From order.priority
    - reason: From order.reason
    
    Args:
        encounter_data: Encounter dictionary with orders field
        
    Returns:
        List of lab order dictionaries with all fields from source
        
    Examples:
        >>> extract_lab_orders({"orders": [{"id": "o1", "name": "COVID test"}]})
        [{"orderId": "o1", "name": "COVID test", "status": None, "priority": None, "reason": None}]
        
        >>> extract_lab_orders({"orders": [
        ...     {"id": "o1", "name": "Test", "newField": "value"}
        ... ]})
        [{"orderId": "o1", "name": "Test", "status": None, "priority": None, "reason": None, 
          "newField": "value"}]
    """
    if not isinstance(encounter_data, dict):
        logger.warning("Encounter data is not a dict, returning empty lab orders")
        return []
    
    orders = encounter_data.get("orders", [])
    if not isinstance(orders, list):
        logger.warning("Orders is not a list, returning empty lab orders")
        return []
    
    if not orders:
        logger.debug("No orders found, returning empty list")
        return []
    
    lab_orders = []
    for idx, order in enumerate(orders):
        if not isinstance(order, dict):
            logger.warning(f"Order at index {idx} is not a dict, skipping")
            continue
        
        # Start with source order (preserves ALL fields including unknown ones)
        lab_order = dict(order)
        
        # Map known fields explicitly (ensures correct field names)
        # Handle multiple possible field names for orderId and name
        order_id = order.get("orderId") or order.get("id") or order.get("order_id")
        order_name = order.get("name") or order.get("orderName") or order.get("order_name")
        
        known_field_mappings = {
            "orderId": order_id,
            "name": order_name,
            "status": order.get("status"),
            "priority": order.get("priority"),
            "reason": order.get("reason"),
        }
        
        # Update with mapped values (preserves additional fields)
        lab_order.update(known_field_mappings)
        
        # Ensure name is present (required field)
        if not lab_order.get("name"):
            logger.warning(f"Order at index {idx} missing name field, using default")
            lab_order["name"] = f"Order {idx + 1}"
        
        # Log preserved additional fields
        known_fields = set(known_field_mappings.keys())
        additional_fields = set(lab_order.keys()) - known_fields
        if additional_fields:
            logger.debug(f"Preserved additional fields from order {idx}: {additional_fields}")
        
        lab_orders.append(lab_order)
    
    logger.info(f"Extracted {len(lab_orders)} lab orders from {len(orders)} source orders")
    return lab_orders
