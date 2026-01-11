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

__all__ = ["main_router"]

