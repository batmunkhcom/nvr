"""API v1 router aggregation."""

from fastapi import APIRouter

from .auth import router as auth_router
from .cameras import router as cameras_router
from .events import router as events_router
from .recordings import router as recordings_router
from .storage import router as storage_router
from .system import router as system_router
from .users import router as users_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(cameras_router)
router.include_router(events_router)
router.include_router(recordings_router)
router.include_router(storage_router)
router.include_router(system_router)
router.include_router(users_router)
