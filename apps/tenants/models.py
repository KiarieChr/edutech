# pyrefly: ignore [missing-import]
from django.db import models
# pyrefly: ignore [missing-import]
from django_tenants.models import TenantMixin, DomainMixin

class PublicConfiguration(models.Model):
    """
    Singleton configuration for the public schema.
    Stores the base domain (e.g. localhost, myapp.com) to use when dynamically creating tenants.
    """
    base_domain = models.CharField(max_length=255, default="localhost")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_instance(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self):
        return f"Public Config (Base Domain: {self.base_domain})"

class Client(TenantMixin):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    settings = models.JSONField(default=dict, blank=True)
    created_on = models.DateField(auto_now_add=True)
    
    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True
    
    def __str__(self):
        return self.name

class Domain(DomainMixin):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('suspended', 'Suspended'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    def __str__(self):
        return self.domain


class Installation(models.Model):
    installation_id = models.CharField(max_length=100, unique=True, db_index=True)
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="installations")
    name = models.CharField(max_length=150)
    public_key = models.TextField(help_text="Ed25519 public key in PEM or Hex format")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    software_version = models.CharField(max_length=50, null=True, blank=True)
    sync_schema_version = models.CharField(max_length=10, default="1.0")

    def __str__(self):
        return f"{self.name} ({self.installation_id})"
