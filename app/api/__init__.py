"""
API routes and endpoints for the Patient Form Data Capture application.
"""

# Import app lazily to avoid circular imports
def get_app():
    """Get the FastAPI application instance."""
    # Import from routes.py directly (bypassing routes package)
    import sys
    from pathlib import Path
    
    # Add routes.py to sys.modules with a different name to avoid conflict
    routes_file = Path(__file__).parent / "routes.py"
    if "app.api.routes_module" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location("app.api.routes_module", routes_file)
        routes_module = importlib.util.module_from_spec(spec)
        sys.modules["app.api.routes_module"] = routes_module
        spec.loader.exec_module(routes_module)
        return routes_module.app
    else:
        return sys.modules["app.api.routes_module"].app

# Export app for uvicorn compatibility: app.api:app
app = get_app()

__all__ = ["get_app", "app"]

