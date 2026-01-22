"""
Image caching utility with in-memory LRU cache.

This module provides caching for downloaded images to reduce Azure Blob Storage API calls
and improve response times. It's fully backward compatible - if caching fails, the system
falls back to direct downloads.

Features:
- In-memory LRU cache with size limits
- Automatic eviction of oldest entries when limits are reached
- Backward compatible - continues working if cache unavailable
"""

import logging
from typing import Optional, Dict
from collections import OrderedDict

logger = logging.getLogger(__name__)

# In-memory cache configuration
_image_cache: Dict[str, bytes] = OrderedDict()
_cache_size_limit = 100  # Max 100 images in memory
_cache_size_bytes_limit = 100 * 1024 * 1024  # 100MB limit
_current_cache_size = 0  # Track total bytes in cache


def get_cached_image(image_path: str) -> Optional[bytes]:
    """
    Get image from in-memory cache.
    
    Args:
        image_path: The path to the image in Azure Blob Storage
        
    Returns:
        Cached image bytes, or None if not cached
        
    This function is backward compatible - returns None if cache is unavailable.
    """
    if image_path in _image_cache:
        # Move to end (LRU - most recently used)
        _image_cache.move_to_end(image_path)
        logger.debug(f"Image cache hit: {image_path}")
        return _image_cache[image_path]
    
    return None


def cache_image(image_path: str, image_bytes: bytes) -> None:
    """
    Cache image in memory.
    
    Args:
        image_path: The path to the image in Azure Blob Storage
        image_bytes: The image bytes to cache
        
    This function is backward compatible - continues if caching fails.
    """
    global _current_cache_size
    
    if not image_bytes:
        return
    
    image_size = len(image_bytes)
    
    # Cache in memory (with size limits)
    # Only cache if image is not too large
    if image_size < _cache_size_bytes_limit:
        # Remove oldest entries if cache is full
        while len(_image_cache) >= _cache_size_limit:
            oldest_key, oldest_value = _image_cache.popitem(last=False)
            _current_cache_size -= len(oldest_value)
            logger.debug(f"Evicted image from cache: {oldest_key}")
        
        # Check if adding this image would exceed size limit
        if _current_cache_size + image_size > _cache_size_bytes_limit:
            # Remove oldest entries until we have space
            while _current_cache_size + image_size > _cache_size_bytes_limit and _image_cache:
                oldest_key, oldest_value = _image_cache.popitem(last=False)
                _current_cache_size -= len(oldest_value)
                logger.debug(f"Evicted image from cache (size limit): {oldest_key}")
        
        # Add to cache
        if image_path in _image_cache:
            # Update existing entry
            old_size = len(_image_cache[image_path])
            _current_cache_size -= old_size
            _image_cache.move_to_end(image_path)
        else:
            _image_cache[image_path] = image_bytes
            _current_cache_size += image_size
            logger.debug(f"Image cached: {image_path} ({image_size} bytes)")
    else:
        logger.debug(f"Image too large to cache: {image_path} ({image_size} bytes)")


def clear_cache(image_path: Optional[str] = None) -> None:
    """
    Clear cache for specific image or all images.
    
    Args:
        image_path: Optional specific image path to clear. If None, clears all.
        
    This is useful when images are updated or deleted.
    """
    global _current_cache_size
    
    if image_path:
        # Clear from memory
        if image_path in _image_cache:
            old_size = len(_image_cache[image_path])
            _current_cache_size -= old_size
            del _image_cache[image_path]
            logger.debug(f"Cleared cache for: {image_path}")
    else:
        # Clear all
        _image_cache.clear()
        _current_cache_size = 0
        logger.debug("Cleared all images from cache")


def get_cache_stats() -> Dict[str, any]:
    """
    Get cache statistics for monitoring.
    
    Returns:
        Dictionary with cache statistics
    """
    return {
        "cache_size": len(_image_cache),
        "cache_bytes": _current_cache_size,
        "cache_limit": _cache_size_limit,
        "cache_bytes_limit": _cache_size_bytes_limit,
    }
