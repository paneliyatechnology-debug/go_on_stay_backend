import os
import sys
from django.core.management.base import BaseCommand
from sync_postman import sync_postman


class Command(BaseCommand):
    help = 'Synchronizes local Postman collection directly to Postman Cloud workspace via Postman API.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Path to specific collection JSON file to sync.'
        )

    def handle(self, *args, **options):
        specified_file = options.get('file')
        self.stdout.write(self.style.NOTICE('Starting GoOnStay Postman Cloud Sync...'))
        success = sync_postman(specified_file)
        if success:
            self.stdout.write(self.style.SUCCESS('Successfully synced GoOnStay collection to Postman!'))
        else:
            self.stdout.write(self.style.ERROR('Postman sync failed. Please check error output above.'))
            sys.exit(1)
