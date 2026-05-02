from django.contrib import admin

from .models import (
    DriverProfile,
    FuelLog,
    MaintenanceRecord,
    TripLog,
    Vehicle,
    VehicleAssignment,
    VehicleDocument,
    VehicleExpense,
)

admin.site.register(Vehicle)
admin.site.register(DriverProfile)
admin.site.register(VehicleAssignment)
admin.site.register(TripLog)
admin.site.register(FuelLog)
admin.site.register(MaintenanceRecord)
admin.site.register(VehicleExpense)
admin.site.register(VehicleDocument)
