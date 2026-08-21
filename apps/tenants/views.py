from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework import status
from django.db import transaction
from django_tenants.utils import schema_context, get_public_schema_name
from .models import Client, Domain, PublicConfiguration
from core.models import InstitutionProfile
from workforce.models import Campus
from django.contrib.auth import get_user_model
import re
import traceback

class TenantCreationThrottle(AnonRateThrottle):
    rate = '5/hour'

class CreateTenantView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [TenantCreationThrottle]

    def post(self, request, *args, **kwargs):
        schema_name = request.data.get('schema_name')
        institution_data = request.data.get('institution_profile', {})
        campuses_data = request.data.get('campuses', [])
        admin_data = request.data.get('admin_user', {})

        if not schema_name:
            return Response({"error": "schema_name is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate schema_name (alphanumeric and underscores only)
        if not re.match(r'^[a-zA-Z0-9_]+$', schema_name):
            return Response({"error": "schema_name can only contain alphanumeric characters and underscores"}, status=status.HTTP_400_BAD_REQUEST)

        if Client.objects.filter(schema_name=schema_name).exists():
            return Response({"error": "Tenant with this schema_name already exists"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with schema_context(get_public_schema_name()):
                with transaction.atomic():
                    # 1. Create Tenant
                    tenant = Client(schema_name=schema_name, name=institution_data.get('name', schema_name))
                    tenant.save() # This triggers schema creation and migrations

                    # 2. Create Domain
                    config = PublicConfiguration.get_instance()
                    domain_name = f"{schema_name}.{config.base_domain}"
                    domain = Domain(domain=domain_name, tenant=tenant, is_primary=True)
                    domain.save()

            # 3. Seed Tenant Data
            with schema_context(schema_name):
                    # Update Institution Profile
                    profile = InstitutionProfile.get_instance()
                    for attr, value in institution_data.items():
                        if hasattr(profile, attr):
                            setattr(profile, attr, value)
                    profile.save()

                    # Create Campuses
                    for campus_data in campuses_data:
                        campus_code = campus_data.get('code', '').strip()
                        if not campus_code:
                            continue
                        Campus.objects.create(
                            institution=profile,
                            code=campus_code,
                            name=campus_data.get('name', ''),
                            location=campus_data.get('location', ''),
                            phone=campus_data.get('phone', ''),
                            email=campus_data.get('email', '')
                        )

                    # Create Initial Admin User
                    User = get_user_model()
                    email = admin_data.get('email')
                    password = admin_data.get('password')
                    if email and password:
                        user = User.objects.create_superuser(
                            email=email,
                            password=password,
                            first_name=admin_data.get('first_name', ''),
                            last_name=admin_data.get('last_name', '')
                        )

            return Response({
                "message": "Institution created successfully",
                "domain": domain_name
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            traceback.print_exc()
            return Response({"error": f"Internal Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TenantInfoView(APIView):
    """
    Returns information about the current tenant based on the subdomain.
    """
    permission_classes = [AllowAny]
    
    def get(self, request, *args, **kwargs):
        tenant = request.tenant
        return Response({
            "schema_name": tenant.schema_name,
            "name": tenant.name,
            "description": tenant.description,
            "settings": tenant.settings,
            "domain": tenant.domain_url,
        })

class DashboardStatsView(APIView):
    """
    Returns high-level statistics for the current tenant dashboard.
    Requires authentication.
    """
    def get(self, request, *args, **kwargs):
        # Example stats, to be expanded based on business logic
        from student_management.models import Student
        from workforce.models import Employee
        
        student_count = Student.objects.all().count()
        employee_count = Employee.objects.all().count()
        
        return Response({
            "total_students": student_count,
            "total_employees": employee_count,
            "active_courses": 0, # Placeholder
            "recent_revenue": 0, # Placeholder
        })


