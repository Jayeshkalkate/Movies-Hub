import logging
import uuid
import httpx
from django.conf import settings
from .models import MembershipVerification

logger = logging.getLogger(__name__)

async def check_telegram_membership(user_telegram_id: int, chat_id: str) -> bool:
    """
    Asynchronously check if a user is a member of a Telegram channel.
    """
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getChatMember"
    params = {"chat_id": chat_id, "user_id": user_telegram_id}
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            data = response.json()
            if data.get("ok"):
                status = data["result"].get("status")
                return status in {"member", "administrator", "creator"}
            return False
    except Exception as e:
        logger.error("Failed to check Telegram membership for user %s: %s", user_telegram_id, e)
        return False

def generate_verification_code(user) -> str:
    """
    Generate a unique verification code for a user.
    """
    code = uuid.uuid4().hex
    obj, _ = MembershipVerification.objects.get_or_create(user=user)
    obj.verification_code = code
    obj.save()
    return code
