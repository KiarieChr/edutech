import os
import django
import json
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from finance_reports.services import ReportService

# Helper to serialize decimals
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super(DecimalEncoder, self).default(o)

data = ReportService.get_trial_balance()
print(json.dumps(data, cls=DecimalEncoder, indent=2))
