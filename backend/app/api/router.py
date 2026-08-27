from fastapi import APIRouter

from app.api.routes import admin_config, auth, beneficiaries, kyc, limits, remittances, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(kyc.router)
api_router.include_router(beneficiaries.router)
api_router.include_router(remittances.router)
api_router.include_router(limits.router)
api_router.include_router(admin_config.router)
