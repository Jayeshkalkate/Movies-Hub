# coremovieshub/management/commands/set_webhook.py

import requests
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Set Telegram bot webhook'

    def handle(self, *args, **options):
        webhook_url = f"{settings.BASE_URL}/webhook/"
        self.stdout.write(f"Webhook URL: {webhook_url}")
        token = settings.TELEGRAM_BOT_TOKEN
        url = f"https://api.telegram.org/bot{token}/setWebhook"
        response = requests.post(
            url,json={
                "url": webhook_url,
                "secret_token": settings.TELEGRAM_SECRET
                }
            )
        self.stdout.write(str(response.json()))
        
