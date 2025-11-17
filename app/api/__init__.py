"""
API routes and endpoints for the Patient Form Data Capture application.
"""

# Import app lazily to avoid circular imports
def get_app():
    """Get the FastAPI application instance."""
    from app.api.routes import app
    return app

__all__ = ["get_app"]

