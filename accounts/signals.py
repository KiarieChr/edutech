from .utils import (
    generate_student_credentials,
    generate_lecturer_credentials,
    send_new_account_email,
)


def post_save_account_receiver(instance=None, created=False, *args, **kwargs):
    """
    Send email notification
    """
    if created:
        if getattr(instance, '_skip_account_creation_signal', False):
            return

        if instance.is_student:
            from django.conf import settings
            if hasattr(settings, 'STUDENT_ID_PREFIX'):
                username, password = generate_student_credentials()
                instance.username = username
                instance.set_password(password)
                instance.save()
                # Send email with the generated credentials
                send_new_account_email(instance, password)

        if instance.is_lecturer:
            username, password = generate_lecturer_credentials()
            instance.username = username
            instance.set_password(password)
            instance.save()
            # Send email with the generated credentials
            send_new_account_email(instance, password)
