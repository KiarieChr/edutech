from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
import threading

class EmailThread(threading.Thread):
    def __init__(self, email):
        self.email = email
        threading.Thread.__init__(self)

    def run(self):
        self.email.send()

def send_admission_email(application, student_user, student_password, parent_user, parent_password):
    """
    Send an email to the guardian with student and parent credentials.
    """
    subject = f"Admission Successful - {application.first_name} {application.last_name}"
    
    context = {
        'parent_name': application.guardian_name,
        'student_name': f"{application.first_name} {application.last_name}",
        'school_name': "Fahari Academia", # Could be dynamic from settings
        'intake_name': application.intake.name,
        'student_username': student_user.username,
        'student_password': student_password,
        'parent_username': parent_user.username,
        'parent_password': parent_password,
        'login_url': "http://localhost:5173/auth/login", # Should be from settings
        'current_year': settings.TIME_ZONE, # Just a placeholder
    }
    
    html_content = render_to_string('student_management/email/admission_confirmation.html', context)
    
    # Recipient: Application email is stored in 'email' field.
    # We assume 'email' field in Application model is the Guardian's email as per form.
    recipient_list = [application.email]
    
    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list
    )
    email.content_subtype = "html"
    
    EmailThread(email).start()
