import logging
import uuid
import httpx
from django.conf import settings
from .models import MembershipVerification

logger = logging.getLogger(__name__)

async def check_telegram_membership(user_telegram_id: int, chat_id: int) -> bool:
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getChatMember"

    params = {
        "chat_id": chat_id,
        "user_id": user_telegram_id,
    }

    try:

        async with httpx.AsyncClient(timeout=20) as client:

            response = await client.get(url, params=params)

            response.raise_for_status()

            data = response.json()

            logger.info("Telegram getChatMember response: %s", data)

            if not data.get("ok"):

                logger.error(
                    "Telegram API Error: %s",
                    data.get("description")
                )

                return False

            status = data["result"]["status"]

            logger.info(
                "User %s status = %s",
                user_telegram_id,
                status
            )

            return status in (
                "member",
                "administrator",
                "creator",
            )

    except Exception:

        logger.exception("getChatMember failed")

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
