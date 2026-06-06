from django.core.management.base import BaseCommand
from coremovieshub.bot import setup_bot

class Command(BaseCommand):
    help = 'Runs the Telegram bot in polling mode'
    
    def handle(self, *args, **options):
        self.stdout.write("Starting Telegram bot (polling mode)...")
        application = setup_bot()
        application.run_polling()