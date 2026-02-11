from src.controller.auth import AuthController
from src.controller.user import UserController
from src.controller.livekit import LiveKitController
from src.routers.router import Router

auth_route = Router(router=AuthController.router, prefix="/auth")
user_route = Router(router=UserController.router, prefix="/user")
livekit_route = Router(router=LiveKitController.router, prefix="/livekit")

__all__ = [
    "auth_route",
    "user_route",
    "livekit_route",
]
