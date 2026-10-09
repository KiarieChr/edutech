from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid

class Route(models.Model):
    FEE_MODEL_CHOICES = (
        ('flat_per_route', 'Flat Per Route'),
        ('per_zone', 'Per Zone'),
        ('one_way_two_way', 'One Way vs Two Way'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('seasonal', 'Seasonal'),
    )
    DIRECTION_CHOICES = (
        ('two_way', 'Two Way'),
        ('morning_only', 'Morning Only'),
        ('evening_only', 'Evening Only'),
    )

    route_code = models.CharField(max_length=50, unique=True, db_index=True)
    route_name = models.CharField(max_length=200)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, default='two_way')
    vehicle_registration = models.CharField(max_length=50, blank=True)
    driver_name = models.CharField(max_length=100, blank=True)
    driver_phone = models.CharField(max_length=20, blank=True)
    capacity = models.PositiveIntegerField(default=0)
    fee_model = models.CharField(max_length=20, choices=FEE_MODEL_CHOICES, default='flat_per_route')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Route')
        verbose_name_plural = _('Routes')
        ordering = ['route_name']

    def __str__(self):
        return f"{self.route_code} - {self.route_name}"

class Stop(models.Model):
    ZONE_CHOICES = (
        ('near', 'Near'),
        ('mid', 'Mid'),
        ('far', 'Far'),
    )

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='stops')
    stop_name = models.CharField(max_length=200)
    stop_order = models.PositiveIntegerField(default=1)
    pickup_time = models.TimeField(null=True, blank=True)
    dropoff_time = models.TimeField(null=True, blank=True)
    zone = models.CharField(max_length=20, choices=ZONE_CHOICES, default='near')
    landmark_description = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Stop')
        verbose_name_plural = _('Stops')
        ordering = ['route', 'stop_order']
        unique_together = ('route', 'stop_name')

    def __str__(self):
        return f"{self.stop_name} ({self.route.route_name})"

class FeeStructure(models.Model):
    FEE_TYPE_CHOICES = (
        ('flat', 'Flat Rate'),
        ('near_zone', 'Near Zone'),
        ('mid_zone', 'Mid Zone'),
        ('far_zone', 'Far Zone'),
        ('one_way', 'One Way'),
        ('two_way', 'Two Way'),
    )
    BILLING_CYCLE_CHOICES = (
        ('per_term', 'Per Term'),
        ('per_month', 'Per Month'),
    )

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='fee_structures')
    fee_type = models.CharField(max_length=20, choices=FEE_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, default='per_term')
    academic_year = models.ForeignKey('student_settings.AcademicYear', on_delete=models.CASCADE, related_name='transport_fees')
    term = models.ForeignKey('student_settings.Term', on_delete=models.CASCADE, related_name='transport_fees')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Fee Structure')
        verbose_name_plural = _('Fee Structures')
        unique_together = ('route', 'fee_type', 'academic_year', 'term')

    def __str__(self):
        return f"{self.route.route_name} - {self.get_fee_type_display()} - {self.amount}"

class StudentAssignment(models.Model):
    TRANSPORT_TYPE_CHOICES = (
        ('two_way', 'Two Way'),
        ('morning_only', 'Morning Only'),
        ('evening_only', 'Evening Only'),
    )

    student = models.ForeignKey('student_management.Student', on_delete=models.CASCADE, related_name='transport_assignments', db_index=True)
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='student_assignments')
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name='student_assignments')
    transport_type = models.CharField(max_length=20, choices=TRANSPORT_TYPE_CHOICES, default='two_way')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Student Assignment')
        verbose_name_plural = _('Student Assignments')

    def __str__(self):
        return f"{self.student} - {self.route.route_name}"

class FeeCharge(models.Model):
    student = models.ForeignKey('student_management.Student', on_delete=models.CASCADE, related_name='transport_charges')
    assignment = models.ForeignKey(StudentAssignment, on_delete=models.CASCADE, related_name='charges')
    academic_year = models.ForeignKey('student_settings.AcademicYear', on_delete=models.CASCADE)
    term = models.ForeignKey('student_settings.Term', on_delete=models.CASCADE)
    amount_charged = models.DecimalField(max_digits=10, decimal_places=2)
    fee_label = models.CharField(max_length=255)
    linked_to_main_fee_ledger = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Fee Charge')
        verbose_name_plural = _('Fee Charges')
        unique_together = ('assignment', 'academic_year', 'term')

    def __str__(self):
        return f"{self.student} - {self.fee_label} - {self.amount_charged}"
