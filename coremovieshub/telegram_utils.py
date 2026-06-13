import requests
from django.conf import settings
from .models import MembershipVerification

def check_telegram_membership(user_telegram_id, chat_id):
    """
    Check if a user is a member of the MovieHub Telegram channel.
    """
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getChatMember"
    params = {
        # 'chat_id': settings.MAIN_CHANNEL_ID,
        'chat_id': chat_id,
        'user_id': user_telegram_id
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get('ok'):
            status = data['result'].get('status')
            # 'member', 'administrator', or 'creator' = valid membership
            return status in ['member', 'administrator', 'creator']
        return False
    except Exception:
        return False

def generate_verification_code(user):
    import uuid
    verification_code = uuid.uuid4().hex
    obj, created = MembershipVerification.objects.get_or_create(user=user)
    obj.verification_code = verification_code
    obj.save()
    return verification_code