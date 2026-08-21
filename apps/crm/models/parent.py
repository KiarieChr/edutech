from django.db import models
from django.conf import settings

class ParentGuardian(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    first_name = models.CharField(max_length=120)
    middle_name = models.CharField(max_length=120, blank=True, null=True)
    last_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=60, blank=True, null=True)
    whatsapp_number = models.CharField(max_length=60, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    national_id = models.CharField(max_length=50, blank=True, null=True)
    occupation = models.CharField(max_length=120, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    preferred_language = models.CharField(max_length=10, default='en')
    status = models.CharField(max_length=20, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_parent_guardian"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
