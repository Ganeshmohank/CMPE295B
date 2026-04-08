from fastapi import APIRouter

from app.routers import action_items, dashboard, logs, meetings, projects

api_router = APIRouter()
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
api_router.include_router(action_items.router, prefix="/action-items", tags=["action-items"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
