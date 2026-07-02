from django.core.management.base import BaseCommand

from coremovieshub.services.featured import update_featured_movies


class Command(BaseCommand):

    def handle(self, *args, **kwargs):
        update_featured_movies()

        self.stdout.write(
            self.style.SUCCESS("Featured movies updated.")
        )