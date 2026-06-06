from django.apps import AppConfig

class CoremovieshubConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'coremovieshub'
    
    def ready(self):
        import os
        from django.conf import settings
        
        # Skip bot initialization in migrations and shell
        if os.environ.get('RUN_MAIN') or not settings.DEBUG:
            try:
                # Do NOT auto-start the bot here – it will be started via 'runbot' command
                # from .bot import setup_bot
                # setup_bot()
                print("✅ Telegram bot auto-initialisation skipped (use 'python manage.py runbot')")
            except Exception as e:
                print(f"⚠️ Telegram bot initialization skipped: {e}")
                
