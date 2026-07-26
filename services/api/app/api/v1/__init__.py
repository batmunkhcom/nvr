"""API v1 router aggregation."""

from fastapi import APIRouter

from .ai import router as ai_router
from .auth import router as auth_router
from .cameras import router as cameras_router
from .counters import router as counters_router
from .events import router as events_router
from .live import router as live_router
from .locations import router as locations_router
from .lpr import router as lpr_router
from .network import router as network_router
from .recording_schedules import router as recording_schedules_router
from .recordings import router as recordings_router
from .snapshot import router as snapshot_router
from .storage import router as storage_router
from .system import router as system_router
from .users import router as users_router
from .ws import router as ws_router

router = APIRouter()
router.include_router(ai_router)
router.include_router(auth_router)
router.include_router(cameras_router)
router.include_router(counters_router)
router.include_router(events_router)
router.include_router(live_router)
router.include_router(locations_router)
router.include_router(lpr_router)
router.include_router(network_router, tags=["network"])
router.include_router(recording_schedules_router)
router.include_router(recordings_router)
router.include_router(snapshot_router)
router.include_router(storage_router)
router.include_router(system_router)
router.include_router(users_router)
router.include_router(ws_router)
