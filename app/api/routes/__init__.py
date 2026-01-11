"""
Route modules for the Patient Queue API.

This module assembles all route routers into the main FastAPI application.
"""

from fastapi import APIRouter

# Import route modules that have been extracted (Phase 1)
from app.api.routes import ui
from app.api.routes import patients
from app.api.routes import encounters
from app.api.routes import summaries
from app.api.routes import vm_health
from app.api.routes import queue
from app.api.routes import queue_validation
from app.api.routes import images
from app.api.routes import validation

# Create main router
main_router = APIRouter()

# Include extracted sub-routers
main_router.include_router(ui.router)
main_router.include_router(patients.router, tags=["Patients"])
main_router.include_router(encounters.router, tags=["Encounters"])
main_router.include_router(summaries.router, tags=["Summaries"])
main_router.include_router(vm_health.router, tags=["VM"])
main_router.include_router(queue.router, tags=["Queue"])
main_router.include_router(queue_validation.router, tags=["Queue"])
main_router.include_router(images.router, tags=["Images"])
main_router.include_router(validation.router, tags=["Validation"])

# Export 'app' for backward compatibility with app.api.routes:app
# This allows deployment to use the original path without changes
# Use lazy import to avoid circular import issues
_app_instance = None

def _get_app():
    """Lazy import of app to avoid circular imports."""
    global _app_instance
    if _app_instance is None:
        # Import app from routes.py directly (bypassing app.api to avoid circular import)
        import sys
        from pathlib import Path
        routes_file = Path(__file__).parent.parent / "routes.py"
        if "app.api.routes_module" not in sys.modules:
            import importlib.util
            spec = importlib.util.spec_from_file_location("app.api.routes_module", routes_file)
            routes_module = importlib.util.module_from_spec(spec)
            sys.modules["app.api.routes_module"] = routes_module
            spec.loader.exec_module(routes_module)
            _app_instance = routes_module.app
        else:
            _app_instance = sys.modules["app.api.routes_module"].app
    return _app_instance

# Create a property-like accessor for backward compatibility
class _AppProxy:
    """Proxy to lazy-load app for backward compatibility."""
    def __getattr__(self, name):
        app = _get_app()
        return getattr(app, name)
    
    def __call__(self, scope, receive, send):
        """Make proxy callable as ASGI app."""
        app = _get_app()
        return app(scope, receive, send)

# Export app proxy for backward compatibility
app = _AppProxy()

__all__ = ["main_router", "app"]

