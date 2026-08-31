from fastapi import APIRouter

from app.api.routes import (
    admin_config,
    auth,
    beneficiaries,
    cash_out,
    kyc,
    limits,
    remittances,
    settlement,
    users,
    wallet,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(kyc.router)
api_router.include_router(beneficiaries.router)
api_router.include_router(remittances.router)
api_router.include_router(limits.router)
api_router.include_router(admin_config.router)
api_router.include_router(settlement.router)
api_router.include_router(wallet.router)
api_router.include_router(cash_out.router)
