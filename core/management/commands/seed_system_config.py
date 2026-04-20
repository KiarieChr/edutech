"""
Seed default SystemConfiguration entries.
Safe to run multiple times — skips existing keys.
"""
from django.core.management.base import BaseCommand
from core.models import SystemConfiguration

V = SystemConfiguration.ValueType
G = SystemConfiguration.Group

# (key, value, value_type, group, label, description, order)
DEFAULT_CONFIGS = [
    # ── Payments & M-Pesa ────────────────────────────────────────
    ('mpesa_consumer_key', '', V.SECRET, G.PAYMENTS,
     'M-Pesa Consumer Key', 'Safaricom Daraja API consumer key', 10),
    ('mpesa_consumer_secret', '', V.SECRET, G.PAYMENTS,
     'M-Pesa Consumer Secret', 'Safaricom Daraja API consumer secret', 20),
    ('mpesa_shortcode', '', V.STRING, G.PAYMENTS,
     'M-Pesa Shortcode', 'Business shortcode (paybill or till number)', 30),
    ('mpesa_passkey', '', V.SECRET, G.PAYMENTS,
     'M-Pesa Passkey', 'Lipa Na M-Pesa Online passkey', 40),
    ('mpesa_callback_url', '', V.STRING, G.PAYMENTS,
     'M-Pesa Callback URL', 'URL that Safaricom calls with payment confirmation', 50),
    ('mpesa_environment', 'sandbox', V.STRING, G.PAYMENTS,
     'M-Pesa Environment', 'sandbox or production', 60),
    ('payment_currency', 'KES', V.STRING, G.PAYMENTS,
     'Default Currency', 'ISO 4217 currency code (e.g. KES, USD)', 70),
    ('payment_auto_reconcile', 'true', V.BOOLEAN, G.PAYMENTS,
     'Auto-Reconcile Payments', 'Automatically match M-Pesa callbacks to invoices', 80),

    # ── Timetable ────────────────────────────────────────────────
    ('timetable_period_duration', '40', V.INTEGER, G.TIMETABLE,
     'Period Duration (minutes)', 'Default length of each class period', 10),
    ('timetable_break_duration', '15', V.INTEGER, G.TIMETABLE,
     'Break Duration (minutes)', 'Default break time between periods', 20),
    ('timetable_lunch_duration', '60', V.INTEGER, G.TIMETABLE,
     'Lunch Break (minutes)', 'Duration of the lunch break', 30),
    ('timetable_max_periods_per_day', '8', V.INTEGER, G.TIMETABLE,
     'Max Periods Per Day', 'Maximum number of teaching periods in a day', 40),
    ('timetable_start_time', '08:00', V.STRING, G.TIMETABLE,
     'School Start Time', 'When the first period begins (HH:MM)', 50),
    ('timetable_end_time', '16:00', V.STRING, G.TIMETABLE,
     'School End Time', 'When the last period ends (HH:MM)', 60),
    ('timetable_format', 'weekly', V.STRING, G.TIMETABLE,
     'Timetable Format', 'weekly, bi-weekly, or rotating', 70),
    ('timetable_working_days', '["Monday","Tuesday","Wednesday","Thursday","Friday"]', V.JSON, G.TIMETABLE,
     'Working Days', 'Days of the week that school is in session', 80),

    # ── Notifications ────────────────────────────────────────────
    ('sms_gateway', 'africastalking', V.STRING, G.NOTIFICATIONS,
     'SMS Gateway Provider', 'africastalking, twilio, or none', 10),
    ('sms_api_key', '', V.SECRET, G.NOTIFICATIONS,
     'SMS API Key', 'API key for the SMS gateway', 20),
    ('sms_sender_id', '', V.STRING, G.NOTIFICATIONS,
     'SMS Sender ID', 'Sender name/number shown to recipients', 30),
    ('email_backend', 'smtp', V.STRING, G.NOTIFICATIONS,
     'Email Backend', 'smtp, sendgrid, or console', 40),
    ('smtp_host', '', V.STRING, G.NOTIFICATIONS,
     'SMTP Host', 'SMTP server hostname (e.g. smtp.gmail.com)', 50),
    ('smtp_port', '587', V.INTEGER, G.NOTIFICATIONS,
     'SMTP Port', 'SMTP server port', 60),
    ('smtp_username', '', V.STRING, G.NOTIFICATIONS,
     'SMTP Username', 'Email account username', 70),
    ('smtp_password', '', V.SECRET, G.NOTIFICATIONS,
     'SMTP Password', 'Email account password', 80),
    ('notify_on_admission', 'true', V.BOOLEAN, G.NOTIFICATIONS,
     'Notify on Admission', 'Send SMS/email when a student is admitted', 90),
    ('notify_on_fee_payment', 'true', V.BOOLEAN, G.NOTIFICATIONS,
     'Notify on Fee Payment', 'Send SMS/email when a fee payment is received', 100),

    # ── Grading & Reports ────────────────────────────────────────
    ('grading_pass_mark', '40', V.INTEGER, G.GRADING,
     'Pass Mark (%)', 'Minimum percentage score to pass', 10),
    ('grading_scale_type', 'letter', V.STRING, G.GRADING,
     'Grading Scale Type', 'letter (A-E), points (1-12), or percentage', 20),
    ('report_card_format', 'standard', V.STRING, G.GRADING,
     'Report Card Format', 'standard, detailed, or cbc_competency', 30),
    ('show_position_on_report', 'true', V.BOOLEAN, G.GRADING,
     'Show Position on Report', 'Display class rank/position on report cards', 40),
    ('show_teacher_remarks', 'true', V.BOOLEAN, G.GRADING,
     'Teacher Remarks', 'Allow teachers to add per-subject remarks', 50),

    # ── Security ─────────────────────────────────────────────────
    ('session_timeout_minutes', '30', V.INTEGER, G.SECURITY,
     'Session Timeout (minutes)', 'Auto-logout after this period of inactivity', 10),
    ('password_min_length', '8', V.INTEGER, G.SECURITY,
     'Minimum Password Length', 'Minimum number of characters for user passwords', 20),
    ('password_require_uppercase', 'true', V.BOOLEAN, G.SECURITY,
     'Require Uppercase', 'Passwords must contain at least one uppercase letter', 30),
    ('password_require_number', 'true', V.BOOLEAN, G.SECURITY,
     'Require Number', 'Passwords must contain at least one digit', 40),
    ('max_login_attempts', '5', V.INTEGER, G.SECURITY,
     'Max Login Attempts', 'Lock account after this many consecutive failed logins', 50),
    ('mfa_enabled', 'false', V.BOOLEAN, G.SECURITY,
     'Enable Two-Factor Auth', 'Require MFA for admin accounts (OTP via email/SMS)', 60),
    ('audit_log_retention_days', '365', V.INTEGER, G.SECURITY,
     'Audit Log Retention (days)', 'Auto-purge audit logs older than this (0 = never)', 70),

    # ── Admissions ───────────────────────────────────────────────
    ('admission_auto_number', 'true', V.BOOLEAN, G.ADMISSIONS,
     'Auto-Generate Admission Numbers', 'Automatically assign sequential admission numbers', 10),
    ('admission_number_prefix', 'ADM', V.STRING, G.ADMISSIONS,
     'Admission Number Prefix', 'Prefix for auto-generated admission numbers', 20),
    ('admission_number_digits', '4', V.INTEGER, G.ADMISSIONS,
     'Admission Number Digits', 'Number of digits after the prefix (e.g. 4 → ADM0001)', 30),
    ('require_application', 'true', V.BOOLEAN, G.ADMISSIONS,
     'Require Application Form', 'Students must submit an application before admission', 40),
    ('admission_require_documents', 'true', V.BOOLEAN, G.ADMISSIONS,
     'Require Documents Upload', 'Require birth certificate and other documents', 50),
    ('admission_age_min', '3', V.INTEGER, G.ADMISSIONS,
     'Minimum Admission Age', 'Minimum age in years for new admissions', 60),
    ('admission_age_max', '25', V.INTEGER, G.ADMISSIONS,
     'Maximum Admission Age', 'Maximum age in years for new admissions', 70),
]


class Command(BaseCommand):
    help = 'Seed default system configuration entries (safe to re-run)'

    def handle(self, *args, **options):
        created_count = 0
        for key, value, value_type, group, label, description, order in DEFAULT_CONFIGS:
            _, created = SystemConfiguration.objects.get_or_create(
                key=key,
                defaults={
                    'value': value,
                    'value_type': value_type,
                    'group': group,
                    'label': label,
                    'description': description,
                    'display_order': order,
                }
            )
            if created:
                created_count += 1
                self.stdout.write(f"  + {group}/{key}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created {created_count} new config entries "
            f"({len(DEFAULT_CONFIGS) - created_count} already existed)."
        ))
