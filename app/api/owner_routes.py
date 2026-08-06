"""Owner (원장님) API routes.

This module has been split into app/api/owner/ (dashboard_routes.py,
staff_routes.py, ad_owner_routes.py, review_routes.py, misc_routes.py,
_helpers.py). This file remains as a backward-compatible shim so existing
imports (`from app.api.owner_routes import router`) keep working.
"""
from app.api.owner import router  # noqa: F401
