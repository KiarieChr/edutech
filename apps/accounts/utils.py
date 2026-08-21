import threading
import secrets
import string
from datetime import datetime
from django.contrib.auth import get_user_model
from django.conf import settings
from core.utils import send_html_email


def generate_password(length=12):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_student_id():
    # Lazy imports to avoid circular dependencies
    from student_settings.models import AdmissionConfig
    from student_management.models import Student
    from django.utils import timezone
    import random

    # Get or create default config
    config = AdmissionConfig.objects.first()
    if not config:
        config = AdmissionConfig.objects.create(admission_format='auto', prefix='SCH')

    if config.admission_format == 'manual':
        return ""

    # 1. Determine Year Component
    year_str = ""
    if config.include_year:
        now = timezone.now()
        if config.year_format == 'YYYY':
            year_str = str(now.year)
        else:
            year_str = str(now.year)[-2:]

    # 2. Determine Prefix Component
    prefix_str = config.prefix

    # 3. Determine Separator
    sep = config.separator

    # 4. Construct Search Pattern & Base Structure
    # We need to find the last student to determine the next serial.
    # The search strategy depends on the sequence format.
    
    # Defaults
    serial_width = 4
    next_serial = 1
    
    # Helper to build ID
    def build_id(p, y, s, seq, separator):
        if seq == 'P-Y-S':
            parts = [p, y, s]
        elif seq == 'P-S-Y':
            parts = [p, s, y]
        elif seq == 'Y-P-S':
            parts = [y, p, s]
        elif seq == 'P-S':
            parts = [p, s]
        else:
            parts = [p, y, s] # Default P-Y-S
            
        # Filter empty parts (e.g. if no year)
        parts = [part for part in parts if part]
        return separator.join(parts)

    try:
        # Strategy: Get the last student created and try to parse their ID
        # Limiting to students who might match the current format roughly helps
        # But simply getting the latest student by ID is often safest for auto-increment
        # if we assume sticking to one format.
        
        # However, to be safer, we filter by the static parts of the current configuration (Prefix + Year if applicable)
        
        query = Student.objects.all()
        
        # Refine query based on sequence to find relevant last entry
        # P-Y-S -> Starts with Prefix + Sep + Year
        # P-S-Y -> Starts with Prefix
        # Y-P-S -> Starts with Year
        
        search_prefix = ""
        if config.sequence_format == 'P-Y-S':
            search_prefix = f"{prefix_str}{sep}{year_str}{sep}" if year_str else f"{prefix_str}{sep}"
        elif config.sequence_format == 'P-S-Y':
             search_prefix = f"{prefix_str}{sep}"
        elif config.sequence_format == 'Y-P-S':
             search_prefix = f"{year_str}{sep}{prefix_str}{sep}" if year_str else f"{prefix_str}{sep}"
        elif config.sequence_format == 'P-S':
             search_prefix = f"{prefix_str}{sep}"

        # Using startswith might be too restrictive if the user JUST changed settings.
        # But for auto-generation, we usually want to continue the sequence of the CURRENT format.
        # Or do we want to continue the global serial?
        # A common requirement is "Reset serial every year".
        # If 'Year' is part of the ID, usually serial resets.
        # If 'Year' is NOT part, serial continues.
        
        last_student = query.filter(admission_number__startswith=search_prefix).order_by('-id').first()

        if last_student and last_student.admission_number:
            # Attempt to extract serial
            # We assume the serial is the numeric part at the expected position
            # This is complex to regex perfectly without strict enforcement, 
            # so we'll try to find the last chunk of digits in the ID relative to our specific logic.
            
            # Simple approach: Remove the known prefix/year parts and look for the digits
            current_id = last_student.admission_number
            
            # This is a bit brittle, but sufficient for standard usage
            # Remove base structure characters to isolate serial
            temp_id = current_id.replace(prefix_str, '').replace(year_str, '').replace(sep, '')
            
            # Extract digits from what remains
            import re
            digits = re.findall(r'\d+', temp_id)
            if digits:
                # Use the longest digit sequence found, or the last one
                # Usually serial is the distinctive numeric part
                found_serial = int(digits[-1])
                next_serial = found_serial + 1
        
    except Exception as e:
        # Fallback to 1 if parsing fails
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to generate next serial for student ID: {e}")
        pass

    # Construct New ID
    serial_str = f"{next_serial:0{serial_width}d}"
    new_id = build_id(prefix_str, year_str, serial_str, config.sequence_format, config.separator)
    
    return new_id


def generate_lecturer_id():
    # Generate a username based on first and last name and registration date
    registered_year = datetime.now().strftime("%Y")
    lecturers_count = get_user_model().objects.filter(is_lecturer=True).count()
    prefix = getattr(settings, 'LECTURER_ID_PREFIX', 'LCT')
    return f"{prefix}-{registered_year}-{lecturers_count + 1}"


def generate_student_credentials():
    return generate_student_id(), generate_password()


def generate_lecturer_credentials():
    return generate_lecturer_id(), generate_password()


class EmailThread(threading.Thread):
    def __init__(self, subject, recipient_list, template_name, context):
        self.subject = subject
        self.recipient_list = recipient_list
        self.template_name = template_name
        self.context = context
        threading.Thread.__init__(self)

    def run(self):
        send_html_email(
            subject=self.subject,
            recipient_list=self.recipient_list,
            template=self.template_name,
            context=self.context,
        )


def send_new_account_email(user, password):
    if user.is_student:
        template_name = "accounts/email/new_student_account_confirmation.html"
    else:
        template_name = "accounts/email/new_lecturer_account_confirmation.html"
    email = {
        "subject": "Account Created Successfully",
        "recipient_list": [user.email],
        "template_name": template_name,
        "context": {"user": user, "password": password},
    }
    EmailThread(**email).start()