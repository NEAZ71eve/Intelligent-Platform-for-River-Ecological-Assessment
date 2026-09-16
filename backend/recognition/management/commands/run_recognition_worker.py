import time
from django.core.management.base import BaseCommand
from recognition.worker import process_one


class Command(BaseCommand):
    help = 'Process queued jobs; M1 explicitly reports MODEL_NOT_CONFIGURED.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        try:
            while True:
                processed = process_one()
                if options['once']:
                    self.stdout.write('processed' if processed else 'no queued jobs')
                    return
                if not processed:
                    time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write('worker stopped')

