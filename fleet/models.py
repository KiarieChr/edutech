from django.conf import settings
from django.db import models


class FleetAuditedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated',
    )

    class Meta:
        abstract = True


class Vehicle(FleetAuditedModel):
    class VehicleType(models.TextChoices):
        BUS = 'bus', 'Bus'
        VAN = 'van', 'Van'
        PICKUP = 'pickup', 'Pickup'
        SALOON = 'saloon', 'Saloon'
        TRUCK = 'truck', 'Truck'
        MOTORBIKE = 'motorbike', 'Motorbike'
        AMBULANCE = 'ambulance', 'Ambulance'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        MAINTENANCE = 'maintenance', 'Under Maintenance'
        GROUNDED = 'grounded', 'Grounded'
        DISPOSED = 'disposed', 'Disposed'

    registration_number = models.CharField(max_length=30, unique=True, db_index=True)
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveIntegerField(null=True, blank=True)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.OTHER)
    fuel_type = models.CharField(max_length=30, blank=True)
    capacity = models.PositiveIntegerField(default=0)
    chassis_number = models.CharField(max_length=100, blank=True)
    engine_number = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=50, blank=True)

    campus = models.ForeignKey(
        'workforce.Campus',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fleet_vehicles'
    )
    assigned_department = models.ForeignKey(
        'workforce.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fleet_vehicles'
    )

    acquisition_date = models.DateField(null=True, blank=True)
    purchase_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    current_odometer_km = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    insurance_expiry = models.DateField(null=True, blank=True)
    inspection_expiry = models.DateField(null=True, blank=True)
    road_license_expiry = models.DateField(null=True, blank=True)

    next_service_odometer_km = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_service_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['registration_number']

    def __str__(self):
        return f'{self.registration_number} - {self.make} {self.model}'


class DriverProfile(FleetAuditedModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        INACTIVE = 'inactive', 'Inactive'

    employee = models.OneToOneField(
        'workforce.Employee',
        on_delete=models.CASCADE,
        related_name='driver_profile'
    )
    license_number = models.CharField(max_length=100, unique=True)
    license_class = models.CharField(max_length=20)
    license_expiry = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['employee__employee_no']

    def __str__(self):
        return f'{self.employee.employee_no} - {self.license_number}'


class VehicleAssignment(FleetAuditedModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='assignments')
    driver = models.ForeignKey(DriverProfile, on_delete=models.CASCADE, related_name='assignments')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.vehicle.registration_number} -> {self.driver.employee.employee_no}'


class TripLog(FleetAuditedModel):
    class Status(models.TextChoices):
        PLANNED = 'planned', 'Planned'
        APPROVED = 'approved', 'Approved'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELED = 'canceled', 'Canceled'

    reference_number = models.CharField(max_length=50, unique=True, db_index=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='trips')
    driver = models.ForeignKey(DriverProfile, on_delete=models.PROTECT, related_name='trips')

    requested_by = models.ForeignKey(
        'workforce.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fleet_trip_requests'
    )
    department = models.ForeignKey(
        'workforce.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fleet_trips'
    )

    purpose = models.CharField(max_length=255)
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    departure_time = models.DateTimeField()
    expected_return_time = models.DateTimeField(null=True, blank=True)
    actual_return_time = models.DateTimeField(null=True, blank=True)

    start_odometer_km = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    end_odometer_km = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    approval_notes = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-departure_time']

    def __str__(self):
        return self.reference_number


class FuelLog(FleetAuditedModel):
    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        CARD = 'card', 'Fuel Card'
        VOUCHER = 'voucher', 'Voucher'
        OTHER = 'other', 'Other'

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='fuel_logs')
    driver = models.ForeignKey(DriverProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='fuel_logs')
    trip = models.ForeignKey(TripLog, on_delete=models.SET_NULL, null=True, blank=True, related_name='fuel_logs')
    filled_at = models.DateTimeField()
    station_name = models.CharField(max_length=200, blank=True)
    odometer_km = models.DecimalField(max_digits=12, decimal_places=2)
    liters = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-filled_at']

    def __str__(self):
        return f'{self.vehicle.registration_number} {self.filled_at:%Y-%m-%d}'


class MaintenanceRecord(FleetAuditedModel):
    class MaintenanceType(models.TextChoices):
        PREVENTIVE = 'preventive', 'Preventive Service'
        CORRECTIVE = 'corrective', 'Corrective Repair'
        INSPECTION = 'inspection', 'Inspection'
        TIRE = 'tire', 'Tire Service'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELED = 'canceled', 'Canceled'

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='maintenance_records')
    maintenance_type = models.CharField(max_length=20, choices=MaintenanceType.choices, default=MaintenanceType.PREVENTIVE)
    service_provider = models.ForeignKey(
        'payables.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fleet_maintenance_records'
    )
    scheduled_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    odometer_km = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    next_service_date = models.DateField(null=True, blank=True)
    next_service_odometer_km = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    description = models.TextField()
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    parts_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-scheduled_date', '-created_at']

    def __str__(self):
        return f'{self.vehicle.registration_number} - {self.maintenance_type}'


class VehicleExpense(FleetAuditedModel):
    class ExpenseType(models.TextChoices):
        FUEL = 'fuel', 'Fuel'
        SERVICE = 'service', 'Service'
        REPAIR = 'repair', 'Repair'
        TIRES = 'tires', 'Tires'
        INSURANCE = 'insurance', 'Insurance'
        LICENSE = 'license', 'License/Inspection'
        ALLOWANCE = 'allowance', 'Driver Allowance'
        OTHER = 'other', 'Other'

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='expenses')
    trip = models.ForeignKey(TripLog, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    expense_type = models.CharField(max_length=20, choices=ExpenseType.choices)
    expense_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    vendor = models.ForeignKey('payables.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='fleet_expenses')
    description = models.CharField(max_length=255)
    finance_account = models.ForeignKey(
        'finance.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fleet_expenses',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-expense_date', '-created_at']

    def __str__(self):
        return f'{self.vehicle.registration_number} {self.expense_type} {self.amount}'


class VehicleDocument(FleetAuditedModel):
    class DocumentType(models.TextChoices):
        INSURANCE = 'insurance', 'Insurance'
        INSPECTION = 'inspection', 'Inspection'
        LICENSE = 'license', 'Road License'
        LOGBOOK = 'logbook', 'Logbook'
        OTHER = 'other', 'Other'

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    reference_number = models.CharField(max_length=100, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to='fleet/documents/', null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-expiry_date']

    def __str__(self):
        return f'{self.vehicle.registration_number} {self.document_type}'
