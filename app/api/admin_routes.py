"""
Admin API routes — accessible only by ADMIN role.
Covers: merchants CRUD, PG config, transactions, payout requests,
        ad orders management, metrics, fee policies, sales assignments, landing stats.

모듈화되어 app/api/admin/ 패키지로 이동. 하위 호환 re-export.
"""
from app.api.admin import router  # noqa: F401
