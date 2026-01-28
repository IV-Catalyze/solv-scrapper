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
from app.api.routes import server_health
from app.api.routes import queue
from app.api.routes import queue_validation
from app.api.routes import images
from app.api.routes import validation
from app.api.routes import alerts

# Create main router
main_router = APIRouter()

# Include extracted sub-routers
main_router.include_router(ui.router)
main_router.include_router(patients.router, tags=["Patients"])
main_router.include_router(encounters.router, tags=["Encounters"])
main_router.include_router(summaries.router, tags=["Summaries"])
main_router.include_router(vm_health.router, tags=["VM"])
main_router.include_router(server_health.router, tags=["Server"])
main_router.include_router(queue.router, tags=["Queue"])
main_router.include_router(queue_validation.router, tags=["Queue"])
main_router.include_router(images.router, tags=["Images"])
main_router.include_router(validation.router, tags=["Validation"])
main_router.include_router(alerts.router, tags=["Alerts"])

# Export 'app' for backward compatibility with app.api.routes:app
# This allows deployment to use the original path without changes
# Use lazy import to avoid circular import issues by importing from routes.py directly
def _lazy_load_app():
    """Lazy import of app from routes.py to avoid circular imports."""
    import sys
    from pathlib import Path
    
    # Import from routes.py directly (bypassing app.api to avoid circular import)
    routes_file = Path(__file__).parent.parent / "routes.py"
    if "app.api.routes_module" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location("app.api.routes_module", routes_file)
        routes_module = importlib.util.module_from_spec(spec)
        sys.modules["app.api.routes_module"] = routes_module
        spec.loader.exec_module(routes_module)
        return routes_module.app
    else:
        return sys.modules["app.api.routes_module"].app

# Create a module-level __getattr__ to lazy-load app when accessed
# This allows 'from app.api.routes import app' to work
def __getattr__(name):
    """Lazy load 'app' attribute for backward compatibility."""
    if name == "app":
        return _lazy_load_app()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = ["main_router", "app"]

