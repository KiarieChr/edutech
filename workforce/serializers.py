"""
HR & Payroll Django REST Framework Serializers
Part 1: Core Serializers for API
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    
    # Education
    EducationLevel, Institution, FieldOfStudy,
    EmployeeEducation, ProfessionalCertification,
    ContinuousProfessionalDevelopment,
    # Job Management
    Campus, Faculty, Department, JobGrade, JobTitle,
    EmployeeJobAssignment, ReportingLine,
    # Attendance
    AttendancePolicy, WorkSchedule, AttendanceRecord,
    TeachingSessionAttendance, OvertimeRequest,
    # Leave
    LeaveType, EmployeeLeaveBalance, LeaveApplication,
    LeaveEncashment,
    # Performance
    PerformanceMetric, AppraisalCycle, EmployeeAppraisal,
    AcademicProductivity, Publication, ResearchGrant,
    # Payroll
    PayrollPeriod, EarningType, DeductionType,
    EmployeeEarning, EmployeeDeduction, PayrollCalculation,
    Payslip
)
from django.utils import timezone
from .core_models import(
    Employee, Country, County, SubCounty, Village,
    EmployeeAddress, EmergencyContact,
)


# ============================================================================
# USER SERIALIZERS
# ============================================================================

class UserSerializer(serializers.ModelSerializer):
    """User serializer"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


# ============================================================================
# CORE SERIALIZERS
# ============================================================================

class CountrySerializer(serializers.ModelSerializer):
    """Country serializer"""
    class Meta:
        model = Country
        fields = '__all__'


class SubCountySerializer(serializers.ModelSerializer):
    """SubCounty serializer"""
    county_name = serializers.CharField(source='county.name', read_only=True)
    
    class Meta:
        model = SubCounty
        fields = '__all__'


class CountySerializer(serializers.ModelSerializer):
    """County serializer with subcounties"""
    country_name = serializers.CharField(source='country.name', read_only=True)
    subcounties = SubCountySerializer(many=True, read_only=True)
    
    class Meta:
        model = County
        fields = '__all__'


class VillageSerializer(serializers.ModelSerializer):
    """Village serializer"""
    subcounty_name = serializers.CharField(source='subcounty.name', read_only=True)
    
    class Meta:
        model = Village
        fields = '__all__'


class EmergencyContactSerializer(serializers.ModelSerializer):
    """Emergency contact serializer"""
    class Meta:
        model = EmergencyContact
        fields = '__all__'


class EmployeeAddressSerializer(serializers.ModelSerializer):
    """Employee address serializer"""
    country_name = serializers.CharField(source='country.name', read_only=True)
    county_name = serializers.CharField(source='county.name', read_only=True)
    address_type_display = serializers.CharField(
        source='get_address_type_display', 
        read_only=True
    )
    
    class Meta:
        model = EmployeeAddress
        fields = '__all__'


# ============================================================================
# JOB MANAGEMENT SERIALIZERS
# ============================================================================

class CampusSerializer(serializers.ModelSerializer):
    """Campus serializer"""
    class Meta:
        model = Campus
        fields = '__all__'


class FacultySerializer(serializers.ModelSerializer):
    """Faculty serializer"""
    dean_name = serializers.CharField(
        source='dean.get_full_name', 
        read_only=True
    )
    campus_name = serializers.CharField(source='campus.name', read_only=True)
    
    class Meta:
        model = Faculty
        fields = '__all__'


class DepartmentSerializer(serializers.ModelSerializer):
    """Department serializer"""
    faculty_name = serializers.CharField(source='faculty.name', read_only=True)
    hod_name = serializers.CharField(
        source='head_of_department.get_full_name', 
        read_only=True
    )
    campus_name = serializers.CharField(source='campus.name', read_only=True)
    employee_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Department
        fields = '__all__'
    
    def get_employee_count(self, obj):
        return obj.employeejobassignment_set.filter(
            is_primary_assignment=True
        ).count()


class JobGradeSerializer(serializers.ModelSerializer):
    """Job grade serializer"""
    salary_range = serializers.SerializerMethodField()
    
    class Meta:
        model = JobGrade
        fields = '__all__'
    
    def get_salary_range(self, obj):
        return f"{obj.currency} {obj.min_salary:,.2f} - {obj.max_salary:,.2f}"


class JobTitleSerializer(serializers.ModelSerializer):
    """Job title serializer"""
    job_grade_name = serializers.CharField(
        source='job_grade.name', 
        read_only=True
    )
    
    class Meta:
        model = JobTitle
        fields = '__all__'


class EmployeeJobAssignmentSerializer(serializers.ModelSerializer):
    """Employee job assignment serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    job_title_name = serializers.CharField(
        source='job_title.title', 
        read_only=True
    )
    department_name = serializers.CharField(
        source='department.name', 
        read_only=True
    )
    supervisor_name = serializers.CharField(
        source='reports_to.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = EmployeeJobAssignment
        fields = '__all__'


class ReportingLineSerializer(serializers.ModelSerializer):
    """Reporting line serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    supervisor_name = serializers.CharField(
        source='supervisor.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = ReportingLine
        fields = '__all__'


class EmployeeListSerializer(serializers.ModelSerializer):
    """Employee list serializer (summary)"""
    full_name = serializers.SerializerMethodField()
    department = DepartmentSerializer(read_only=True)
    job_title = serializers.SerializerMethodField()
    email = serializers.CharField(source='official_email', read_only=True)
    phone = serializers.CharField(source='phone_primary', read_only=True)
    employment_status_display = serializers.CharField(
        source='get_employment_status_display', 
        read_only=True
    )
    employment_type = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id', 'employee_no', 'first_name', 'last_name', 'full_name',
            'email', 'phone', 'employee_category', 'employment_status',
            'employment_status_display', 'department', 'job_title',
            'hire_date', 'employment_type'
        ]
    
    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_job_title(self, obj):
        # Determine job title from primary assignment
        # We need to import EmployeeJobAssignment locally to avoid circular imports if any
        # Check if job assignments are prefetched or filtered
        assignment = obj.job_assignments.filter(is_primary_assignment=True, effective_to__isnull=True).first()
        if assignment and assignment.job_title:
            return {'id': assignment.job_title.id, 'title': assignment.job_title.title}
        return None

    def get_employment_type(self, obj):
        assignment = obj.job_assignments.filter(is_primary_assignment=True, effective_to__isnull=True).first()
        if assignment:
            return assignment.employment_type
        return None


class EmployeeDetailSerializer(serializers.ModelSerializer):
    """Employee detail serializer (full information)"""
    full_name = serializers.SerializerMethodField()
    addresses = EmployeeAddressSerializer(many=True, read_only=True)
    emergency_contacts = EmergencyContactSerializer(many=True, read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    
    # Write-only fields for frontend compatibility
    job_title_id = serializers.IntegerField(write_only=True, required=False)
    email = serializers.EmailField(source='official_email', required=False)
    phone = serializers.CharField(source='phone_primary', required=False)
    employment_date = serializers.DateField(source='hire_date', required=False)
    status = serializers.CharField(source='employment_status', required=False)
    
    # Write-only fields for job assignment creation
    employment_type = serializers.ChoiceField(
        choices=[
            ('full_time', 'Full-Time'),
            ('part_time', 'Part-Time'),
            ('visiting', 'Visiting'),
            ('adjunct', 'Adjunct')
        ],
        write_only=True,
        required=False,
        default='full_time'
    )
    assignment_type = serializers.ChoiceField(
        choices=[
            ('permanent', 'Permanent'),
            ('acting', 'Acting'),
            ('temporary', 'Temporary'),
            ('secondment', 'Secondment')
        ],
        write_only=True,
        required=False,
        default='permanent'
    )

    class Meta:
        model = Employee
        fields = '__all__'
        extra_kwargs = {
            'official_email': {'required': False},
            'phone_primary': {'required': False},
            'hire_date': {'required': False},
            'employment_status': {'required': False},
            'employee_no': {'required': False}, # allowing auto-generation if needed, though frontend sends it
        }
    
    def get_full_name(self, obj):
        return obj.get_full_name()

    def create(self, validated_data):
        job_title_id = validated_data.pop('job_title_id', None)
        employment_type = validated_data.pop('employment_type', 'full_time')
        assignment_type = validated_data.pop('assignment_type', 'permanent')
        # Fields are already mapped by source=... in the serializer fields above
        
        employee = super().create(validated_data)
        
        if job_title_id:
            from .models import EmployeeJobAssignment, JobTitle
            try:
                job_title = JobTitle.objects.get(id=job_title_id)
                EmployeeJobAssignment.objects.create(
                    employee=employee,
                    job_title=job_title,
                    department=employee.department,
                    effective_from=employee.hire_date,
                    is_primary_assignment=True,
                    employment_type=employment_type,
                    assignment_type=assignment_type,
                    fte=1.00 # Default full FTE
                )
            except JobTitle.DoesNotExist:
                pass
        
        return employee

    def update(self, instance, validated_data):
        job_title_id = validated_data.pop('job_title_id', None)
        employment_type = validated_data.pop('employment_type', None)
        assignment_type = validated_data.pop('assignment_type', 'permanent')
        
        employee = super().update(instance, validated_data)
        
        if job_title_id:
            from .models import EmployeeJobAssignment, JobTitle
            # Check if current primary assignment matches
            current_assignment = employee.job_assignments.filter(is_primary_assignment=True, effective_to__isnull=True).first()
            
            if not current_assignment or current_assignment.job_title_id != job_title_id:
                # End current assignment
                if current_assignment:
                    current_assignment.effective_to = timezone.now().date()
                    current_assignment.is_primary_assignment = False
                    current_assignment.save()
                
                # Create new assignment
                try:
                    job_title = JobTitle.objects.get(id=job_title_id)
                    EmployeeJobAssignment.objects.create(
                        employee=employee,
                        job_title=job_title,
                        department=employee.department, # potentially updated department
                        effective_from=timezone.now().date(),
                        is_primary_assignment=True,
                        employment_type=employment_type or 'full_time',
                        assignment_type=assignment_type,
                        fte=1.00
                    )
                except JobTitle.DoesNotExist:
                    pass
        
        return employee


# ============================================================================
# EDUCATION SERIALIZERS
# ============================================================================

class EducationLevelSerializer(serializers.ModelSerializer):
    """Education level serializer"""
    class Meta:
        model = EducationLevel
        fields = '__all__'


class InstitutionSerializer(serializers.ModelSerializer):
    """Institution serializer"""
    country_name = serializers.CharField(source='country.name', read_only=True)
    
    class Meta:
        model = Institution
        fields = '__all__'


class FieldOfStudySerializer(serializers.ModelSerializer):
    """Field of study serializer"""
    class Meta:
        model = FieldOfStudy
        fields = '__all__'


class EmployeeEducationSerializer(serializers.ModelSerializer):
    """Employee education serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    education_level_name = serializers.CharField(
        source='education_level.name', 
        read_only=True
    )
    institution_name = serializers.CharField(
        source='institution.name', 
        read_only=True
    )
    field_of_study_name = serializers.CharField(
        source='field_of_study.name', 
        read_only=True
    )
    
    class Meta:
        model = EmployeeEducation
        fields = '__all__'


class ProfessionalCertificationSerializer(serializers.ModelSerializer):
    """Professional certification serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = ProfessionalCertification
        fields = '__all__'
    
    def get_is_expired(self, obj):
        from django.utils import timezone
        if obj.expiry_date:
            return obj.expiry_date < timezone.now().date()
        return False


class CPDSerializer(serializers.ModelSerializer):
    """CPD serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = ContinuousProfessionalDevelopment
        fields = '__all__'




# ============================================================================
# ATTENDANCE SERIALIZERS
# ============================================================================

class AttendancePolicySerializer(serializers.ModelSerializer):
    """Attendance policy serializer"""
    class Meta:
        model = AttendancePolicy
        fields = '__all__'


class WorkScheduleSerializer(serializers.ModelSerializer):
    """Work schedule serializer"""
    policy_name = serializers.CharField(
        source='attendance_policy.name', 
        read_only=True
    )
    
    class Meta:
        model = WorkSchedule
        fields = '__all__'


class AttendanceRecordSerializer(serializers.ModelSerializer):
    """Attendance record serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    employee_no = serializers.CharField(
        source='employee.employee_no', 
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display', 
        read_only=True
    )
    
    class Meta:
        model = AttendanceRecord
        fields = '__all__'


class TeachingSessionAttendanceSerializer(serializers.ModelSerializer):
    """Teaching session attendance serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    substitute_name = serializers.CharField(
        source='substitute_lecturer.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = TeachingSessionAttendance
        fields = '__all__'


class OvertimeRequestSerializer(serializers.ModelSerializer):
    """Overtime request serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    department_name = serializers.CharField(
        source='department.name', 
        read_only=True
    )
    
    class Meta:
        model = OvertimeRequest
        fields = '__all__'


# ============================================================================
# LEAVE SERIALIZERS
# ============================================================================

class LeaveTypeSerializer(serializers.ModelSerializer):
    """Leave type serializer"""
    class Meta:
        model = LeaveType
        fields = '__all__'


class EmployeeLeaveBalanceSerializer(serializers.ModelSerializer):
    """Employee leave balance serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    leave_type_name = serializers.CharField(
        source='leave_type.name', 
        read_only=True
    )
    available_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = EmployeeLeaveBalance
        fields = '__all__'
    
    def get_available_balance(self, obj):
        return obj.closing_balance - obj.pending_days


class LeaveApplicationSerializer(serializers.ModelSerializer):
    """Leave application serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    employee_no = serializers.CharField(
        source='employee.employee_no', 
        read_only=True
    )
    leave_type_name = serializers.CharField(
        source='leave_type.name', 
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display', 
        read_only=True
    )
    acting_employee_name = serializers.CharField(
        source='acting_employee.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = LeaveApplication
        fields = '__all__'


class LeaveEncashmentSerializer(serializers.ModelSerializer):
    """Leave encashment serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    leave_type_name = serializers.CharField(
        source='leave_type.name', 
        read_only=True
    )
    
    class Meta:
        model = LeaveEncashment
        fields = '__all__'


# ============================================================================
# PERFORMANCE SERIALIZERS
# ============================================================================

class PerformanceMetricSerializer(serializers.ModelSerializer):
    """Performance metric serializer"""
    class Meta:
        model = PerformanceMetric
        fields = '__all__'


class AppraisalCycleSerializer(serializers.ModelSerializer):
    """Appraisal cycle serializer"""
    appraisal_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AppraisalCycle
        fields = '__all__'
    
    def get_appraisal_count(self, obj):
        return obj.employeeappraisal_set.count()


class EmployeeAppraisalSerializer(serializers.ModelSerializer):
    """Employee appraisal serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    appraiser_name = serializers.CharField(
        source='appraiser.get_full_name', 
        read_only=True
    )
    cycle_name = serializers.CharField(
        source='appraisal_cycle.name', 
        read_only=True
    )
    
    class Meta:
        model = EmployeeAppraisal
        fields = '__all__'


class AcademicProductivitySerializer(serializers.ModelSerializer):
    """Academic productivity serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = AcademicProductivity
        fields = '__all__'


class PublicationSerializer(serializers.ModelSerializer):
    """Publication serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = Publication
        fields = '__all__'


class ResearchGrantSerializer(serializers.ModelSerializer):
    """Research grant serializer"""
    pi_name = serializers.CharField(
        source='principal_investigator.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = ResearchGrant
        fields = '__all__'


# ============================================================================
# PAYROLL SERIALIZERS
# ============================================================================

class PayrollPeriodSerializer(serializers.ModelSerializer):
    """Payroll period serializer"""
    status_display = serializers.CharField(
        source='get_status_display', 
        read_only=True
    )
    
    class Meta:
        model = PayrollPeriod
        fields = '__all__'


class EarningTypeSerializer(serializers.ModelSerializer):
    """Earning type serializer"""
    class Meta:
        model = EarningType
        fields = '__all__'


class DeductionTypeSerializer(serializers.ModelSerializer):
    """Deduction type serializer"""
    class Meta:
        model = DeductionType
        fields = '__all__'


class EmployeeEarningSerializer(serializers.ModelSerializer):
    """Employee earning serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    earning_type_name = serializers.CharField(
        source='earning_type.name', 
        read_only=True
    )
    
    class Meta:
        model = EmployeeEarning
        fields = '__all__'


class EmployeeDeductionSerializer(serializers.ModelSerializer):
    """Employee deduction serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    deduction_type_name = serializers.CharField(
        source='deduction_type.name', 
        read_only=True
    )
    
    class Meta:
        model = EmployeeDeduction
        fields = '__all__'


class PayrollCalculationSerializer(serializers.ModelSerializer):
    """Payroll calculation serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    employee_no = serializers.CharField(
        source='employee.employee_no', 
        read_only=True
    )
    period_name = serializers.CharField(
        source='payroll_period.period_name', 
        read_only=True
    )
    department_name = serializers.CharField(
        source='employee.department.name', 
        read_only=True
    )
    
    class Meta:
        model = PayrollCalculation
        fields = '__all__'


class PayslipSerializer(serializers.ModelSerializer):
    """Payslip serializer"""
    employee_name = serializers.CharField(
        source='employee.get_full_name', 
        read_only=True
    )
    employee_no = serializers.CharField(
        source='employee.employee_no', 
        read_only=True
    )
    period_name = serializers.CharField(
        source='payroll_period.period_name', 
        read_only=True
    )
    
    class Meta:
        model = Payslip
        fields = '__all__'