# pyrefly: ignore [missing-import]
from django.contrib import admin
from .models import User
from student_management.models import Student, Parent


class UserAdmin(admin.ModelAdmin):
    list_display = [
        "get_full_name",
        "username",
        "email",
        "is_active",
        "is_student",
        "is_lecturer",
        "is_parent",
        "is_staff",
    ]
    search_fields = [
        "username",
        "first_name",
        "last_name",
        "email",
        "is_active",
        "is_lecturer",
        "is_parent",
        "is_staff",
    ]

    class Meta:
        managed = True
        verbose_name = "User"
        verbose_name_plural = "Users"


admin.site.register(User, UserAdmin)
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("get_full_name", "admission_number")
    search_fields = ("student__username", "student__first_name", "student__last_name", "admission_number")

    def get_full_name(self, obj):
        return obj.student.get_full_name
    get_full_name.short_description = 'Name'
admin.site.register(Parent)
