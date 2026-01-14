"""Unit tests for lab orders mapper."""

import pytest
from app.utils.experity_mapper.lab_orders_mapper import extract_lab_orders


class TestExtractLabOrders:
    """Test extract_lab_orders function."""
    
    def test_basic_extraction(self):
        """Test basic lab orders extraction."""
        encounter = {
            "orders": [
                {
                    "id": "order-1",
                    "name": "COVID test",
                    "status": "performed",
                    "priority": "high",
                    "reason": "Screening"
                }
            ]
        }
        orders = extract_lab_orders(encounter)
        assert len(orders) == 1
        assert orders[0]["orderId"] == "order-1"
        assert orders[0]["name"] == "COVID test"
        assert orders[0]["status"] == "performed"
        assert orders[0]["priority"] == "high"
        assert orders[0]["reason"] == "Screening"
    
    def test_multiple_orders(self):
        """Test extraction of multiple orders."""
        encounter = {
            "orders": [
                {"id": "order-1", "name": "Test 1"},
                {"id": "order-2", "name": "Test 2"},
                {"id": "order-3", "name": "Test 3"}
            ]
        }
        orders = extract_lab_orders(encounter)
        assert len(orders) == 3
        assert orders[0]["orderId"] == "order-1"
        assert orders[1]["orderId"] == "order-2"
        assert orders[2]["orderId"] == "order-3"
    
    def test_preserve_additional_fields(self):
        """Test that additional fields are preserved."""
        encounter = {
            "orders": [
                {
                    "id": "order-1",
                    "name": "Test",
                    "newField": "someValue",
                    "anotherField": 123
                }
            ]
        }
        orders = extract_lab_orders(encounter)
        assert orders[0]["orderId"] == "order-1"
        assert orders[0]["name"] == "Test"
        assert orders[0]["newField"] == "someValue"
        assert orders[0]["anotherField"] == 123
    
    def test_order_id_variations(self):
        """Test different field names for orderId."""
        # Test with "orderId"
        encounter1 = {"orders": [{"orderId": "o1", "name": "Test"}]}
        orders1 = extract_lab_orders(encounter1)
        assert orders1[0]["orderId"] == "o1"
        
        # Test with "id"
        encounter2 = {"orders": [{"id": "o2", "name": "Test"}]}
        orders2 = extract_lab_orders(encounter2)
        assert orders2[0]["orderId"] == "o2"
        
        # Test with "order_id"
        encounter3 = {"orders": [{"order_id": "o3", "name": "Test"}]}
        orders3 = extract_lab_orders(encounter3)
        assert orders3[0]["orderId"] == "o3"
    
    def test_name_variations(self):
        """Test different field names for name."""
        # Test with "name"
        encounter1 = {"orders": [{"id": "o1", "name": "Test"}]}
        orders1 = extract_lab_orders(encounter1)
        assert orders1[0]["name"] == "Test"
        
        # Test with "orderName"
        encounter2 = {"orders": [{"id": "o2", "orderName": "Test"}]}
        orders2 = extract_lab_orders(encounter2)
        assert orders2[0]["name"] == "Test"
        
        # Test with "order_name"
        encounter3 = {"orders": [{"id": "o3", "order_name": "Test"}]}
        orders3 = extract_lab_orders(encounter3)
        assert orders3[0]["name"] == "Test"
    
    def test_missing_name(self):
        """Test when name is missing (should use default)."""
        encounter = {
            "orders": [
                {"id": "order-1"}
            ]
        }
        orders = extract_lab_orders(encounter)
        assert orders[0]["name"] == "Order 1"
    
    def test_missing_orders(self):
        """Test with missing orders."""
        encounter = {}
        orders = extract_lab_orders(encounter)
        assert orders == []
    
    def test_empty_orders(self):
        """Test with empty orders array."""
        encounter = {"orders": []}
        orders = extract_lab_orders(encounter)
        assert orders == []
    
    def test_invalid_encounter(self):
        """Test with invalid encounter data."""
        orders = extract_lab_orders(None)
        assert orders == []
        
        orders = extract_lab_orders("not a dict")
        assert orders == []
    
    def test_non_list_orders(self):
        """Test when orders is not a list."""
        encounter = {"orders": "not a list"}
        orders = extract_lab_orders(encounter)
        assert orders == []
    
    def test_invalid_order_item(self):
        """Test when order item is not a dict."""
        encounter = {
            "orders": [
                {"id": "order-1", "name": "Test"},
                "not a dict",
                {"id": "order-2", "name": "Test 2"}
            ]
        }
        orders = extract_lab_orders(encounter)
        assert len(orders) == 2
        assert orders[0]["orderId"] == "order-1"
        assert orders[1]["orderId"] == "order-2"
    
    def test_partial_data(self):
        """Test with partial order data."""
        encounter = {
            "orders": [
                {
                    "id": "order-1",
                    "name": "Test"
                    # Missing status, priority, reason
                }
            ]
        }
        orders = extract_lab_orders(encounter)
        assert orders[0]["orderId"] == "order-1"
        assert orders[0]["name"] == "Test"
        assert orders[0]["status"] is None
        assert orders[0]["priority"] is None
        assert orders[0]["reason"] is None
