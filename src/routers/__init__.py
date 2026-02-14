from src.controller.auth import AuthController
from src.controller.user import UserController
from src.controller.livekit import LiveKitController
from src.controller.document import DocumentController
from src.controller.agent import AgentController
from src.controller.analytics import AnalyticsController
from src.controller.conversation import ConversationController
from src.routers.router import Router

auth_route = Router(router=AuthController.router, prefix="/auth")
user_route = Router(router=UserController.router, prefix="/user")
livekit_route = Router(router=LiveKitController.router, prefix="/livekit")
document_route = Router(router=DocumentController.router, prefix="/document")
agent_route = Router(router=AgentController.router, prefix="/agent")
analytics_route = Router(router=AnalyticsController.router, prefix="/analytics")
conversation_route = Router(router=ConversationController.router, prefix="/conversation")

__all__ = [
    "auth_route",
    "user_route",
    "livekit_route",
    "document_route",
    "agent_route",
    "analytics_route",
    "conversation_route",
]
