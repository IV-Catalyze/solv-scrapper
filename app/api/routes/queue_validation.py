# ... existing code ...
def _get_routes_module():
    """Import from routes.py file (not the package) to avoid circular imports.
    
    First tries to use the actual app.api.routes module if it's already loaded.
    Otherwise, loads routes.py as a separate module instance.
    """
    import sys
    
    # Try to use the actual app.api.routes module if it's already loaded
    # This ensures we use the same module-level variables (container_client, etc.)
    if 'app.api.routes' in sys.modules:
        return sys.modules['app.api.routes']
    
    # Fallback: load routes.py as a separate module instance
    import importlib.util
    from pathlib import Path
    
    if 'app.api.routes_module' not in sys.modules:
        routes_file = Path(__file__).parent.parent.parent / 'app' / 'api' / 'routes.py'
        spec = importlib.util.spec_from_file_location('app.api.routes_module', routes_file)
        routes_module = importlib.util.module_from_spec(spec)
        sys.modules['app.api.routes_module'] = routes_module
        spec.loader.exec_module(routes_module)
        return routes_module
    else:
        return sys.modules['app.api.routes_module']
# ... existing code ...
