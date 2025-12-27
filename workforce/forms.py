from django import forms
from django.utils.translation import gettext_lazy as _
from .models import *


class EmployeeForm(forms.ModelForm):
    """Employee form"""
    
    class Meta:
        model = Employee
        fields = [
            'employee_no', 'first_name', 'middle_name', 'last_name',
            'date_of_birth', 'gender', 'national_id', 'passport_number',
            'personal_email', 'official_email', 'phone_primary', 'phone_secondary',
            'employee_category', 'payroll_type', 'employment_status',
            'hire_date', 'confirmation_date', 'department', 'job_grade'
        ]
        widgets = {
            'employee_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'EMP001'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_number': forms.TextInput(attrs={'class': 'form-control'}),
            'personal_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'official_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+254...'}),
            'phone_secondary': forms.TextInput(attrs={'class': 'form-control'}),
            'employee_category': forms.Select(attrs={'class': 'form-select'}),
            'payroll_type': forms.Select(attrs={'class': 'form-select'}),
            'employment_status': forms.Select(attrs={'class': 'form-select'}),
            'hire_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'confirmation_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'job_grade': forms.Select(attrs={'class': 'form-select'}),
        }


class LeaveApplicationForm(forms.ModelForm):
    """Leave application form"""
    
    class Meta:
        model = LeaveApplication
        fields = [
            'employee', 'leave_type', 'start_date', 'end_date',
            'total_days', 'working_days', 'reason',
            'emergency_contact_during_leave', 'emergency_phone',
            'acting_employee', 'supporting_document_path'
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_days': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'working_days': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'emergency_contact_during_leave': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'acting_employee': forms.Select(attrs={'class': 'form-select'}),
            'supporting_document_path': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = Employee.objects.filter(employment_status='active')
        self.fields['acting_employee'].queryset = Employee.objects.filter(employment_status='active')


class AttendanceForm(forms.ModelForm):
    """Attendance form"""
    
    class Meta:
        model = AttendanceRecord
        fields = [
            'employee', 'attendance_date', 'check_in_time', 'check_out_time',
            'status', 'notes'
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'attendance_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'check_in_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'check_out_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
