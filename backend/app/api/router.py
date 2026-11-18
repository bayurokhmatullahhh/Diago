from fastapi import APIRouter

from app.api.routes import agent, assistant, health, notifications, todos

api_router = APIRouter()
api_router.include_router(agent.router)
api_router.include_router(assistant.router)
api_router.include_router(health.router)
api_router.include_router(notifications.router)
api_router.include_router(todos.router)
