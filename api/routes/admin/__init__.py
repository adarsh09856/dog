from fastapi import APIRouter

from api.routes.admin.audit_logs import router as audit_logs_router
from api.routes.admin.credit_packages import router as credit_packages_router
from api.routes.admin.master_keys import router as master_keys_router
from api.routes.admin.models import router as models_router
from api.routes.admin.moderation import router as moderation_router
from api.routes.admin.monitoring import router as monitoring_router
from api.routes.admin.plans import router as plans_router
from api.routes.admin.settings import router as settings_router
from api.routes.admin.users import router as users_router

admin_router = APIRouter(prefix="/admin", tags=["admin"])

admin_router.include_router(master_keys_router)
admin_router.include_router(models_router)
admin_router.include_router(users_router)
admin_router.include_router(plans_router)
admin_router.include_router(credit_packages_router)
admin_router.include_router(monitoring_router)
admin_router.include_router(moderation_router)
admin_router.include_router(settings_router)
admin_router.include_router(audit_logs_router)
