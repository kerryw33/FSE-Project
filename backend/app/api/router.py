from fastapi import APIRouter

from app.api.routes import auth, beneficiaries, kyc, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(kyc.router)
api_router.include_router(beneficiaries.router)
