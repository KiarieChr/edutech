# HRMS Enhancement Architecture Proposal

## Document Information
- **Version**: 1.0
- **Date**: 2025-01-XX
- **Status**: Awaiting Approval
- **Author**: System Architect

---

## Executive Summary

This document outlines the proposed architecture enhancements to transform the existing HR module into a complete Human Resource Management System (HRMS). The approach is **incremental** and **non-destructive** - all existing models, tables, and logic remain intact.

---

## Current System Analysis

### ✅ What Already Exists (Excellent Foundation)

| Module | Existing Models | Status |
|--------|-----------------|--------|
| **Employee Core** | `Employee` with EmployeeCategory, PayrollType, EmploymentStatus | Complete |
| **Organization** | `Department` (with hierarchy via `parent_department`), `Campus`, `Faculty` | Needs extension |
| **Job Structure** | `JobGrade`, `JobTitle`, `JobDescription` (versioned) | Complete |
| **Recruitment** | `JobOpening`, `JobApplication`, `InterviewRound`, `InterviewSchedule`, `InterviewEvaluation`, `OfferLetter`, `BackgroundCheck`, `OnboardingProcess`, `ProbationReview` | Complete |
| **Attendance** | `AttendancePolicy`, `WorkSchedule`, `AttendanceRecord`, `BiometricDevice` | Complete |
| **Leave** | `LeaveType`, `LeavePolicyByCategory`, `EmployeeLeaveBalance`, `LeaveApplication`, `LeaveApprovalWorkflow` | Complete |
| **Performance** | `PerformanceMetric`, `AppraisalCycle`, `EmployeeAppraisal`, `Peer360Feedback`, `StudentFeedback` | Complete |
| **Payroll** | `PayrollPeriod`, `PayProfile`, `EarningType`, `DeductionType`, `PayrollCalculation`, `Payslip` | Complete |
| **Job Assignments** | `EmployeeJobAssignment`, `ReportingLine`, `SuccessionPlan` | Complete |

### 🔧 Gaps Identified (What's Missing)

1. **Position Management** - Separate from JobTitle for headcount/budget control
2. **Employee Lifecycle Audit Trail** - Comprehensive status change logging
3. **Bulk Import Framework** - Excel upload with validation/preview
4. **Document Management** - Centralized employee documents
5. **Org Chart API** - Tree structure generation for visualization
6. **HR Automation Service** - Event-driven triggers for notifications/workflows
7. **Fine-grained RBAC** - HR-specific permission groups

---

## Proposed Schema Extensions

### Phase 1: Organization Structure Enhancement

#### New Model: `Position`
```python
# WHY: JobTitle defines the "role" (e.g., "Senior Lecturer"), but Position defines 
# the actual "seat" in the org chart with budget allocation and headcount.

class Position(AuditedModel):
    """
    Funded positions in the organization - separate from job titles.
    A JobTitle can have multiple Positions across departments.
    """
    class PositionType(models.TextChoices):
        PERMANENT = 'permanent', _('Permanent')
        CONTRACT = 'contract', _('Contract')
        TEMPORARY = 'temporary', _('Temporary')
        GRANT_FUNDED = 'grant_funded', _('Grant Funded')
    
    class FundingStatus(models.TextChoices):
        FUNDED = 'funded', _('Funded')
        UNFUNDED = 'unfunded', _('Unfunded')
        FROZEN = 'frozen', _('Frozen')
    
    class VacancyStatus(models.TextChoices):
        VACANT = 'vacant', _('Vacant')
        OCCUPIED = 'occupied', _('Occupied')
        ON_HOLD = 'on_hold', _('On Hold')
    
    position_code = models.CharField(max_length=50, unique=True)  # e.g., POS-ACAD-001
    title = models.CharField(max_length=200)  # Display name
    
    job_title = models.ForeignKey('JobTitle', on_delete=models.PROTECT, related_name='positions')
    department = models.ForeignKey('Department', on_delete=models.PROTECT, related_name='positions')
    campus = models.ForeignKey('Campus', on_delete=models.PROTECT)
    
    reports_to_position = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='subordinate_positions'
    )
    
    position_type = models.CharField(max_length=20, choices=PositionType.choices)
    funding_status = models.CharField(max_length=20, choices=FundingStatus.choices, default='funded')
    vacancy_status = models.CharField(max_length=20, choices=VacancyStatus.choices, default='vacant')
    
    # Budget allocation
    budgeted_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    budget_code = models.CharField(max_length=50, blank=True)  # Links to finance
    fiscal_year = models.PositiveIntegerField(null=True, blank=True)
    
    # Dates
    created_date = models.DateField(auto_now_add=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    
    # Current holder (denormalized for performance)
    current_employee = models.ForeignKey(
        'Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='held_positions'
    )
    
    is_critical = models.BooleanField(default=False, help_text="Key position requiring succession plan")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_position'
        ordering = ['department', 'position_code']
        indexes = [
            models.Index(fields=['department', 'vacancy_status']),
            models.Index(fields=['position_code']),
        ]
```

#### Enhancement: Department Model
**No structural changes needed** - existing `parent_department` FK already supports hierarchy.
Add helper methods only:

```python
# Add to Department class (new methods, not model changes)
def get_org_tree(self):
    """Returns hierarchical tree structure for org chart"""
    pass

def get_all_descendants(self):
    """Returns all sub-departments recursively"""
    pass

def get_headcount(self):
    """Returns count of active employees including sub-departments"""
    pass
```

---

### Phase 2: Employee Lifecycle Management

#### New Model: `EmployeeLifecycleLog`
```python
class EmployeeLifecycleLog(TimestampedModel):
    """
    Comprehensive audit trail of all employee lifecycle events.
    WHY: Provides complete historical record for compliance and analytics.
    """
    class EventType(models.TextChoices):
        HIRED = 'hired', _('Hired')
        PROMOTION = 'promotion', _('Promotion')
        TRANSFER = 'transfer', _('Transfer')
        DEMOTION = 'demotion', _('Demotion')
        SALARY_CHANGE = 'salary_change', _('Salary Change')
        STATUS_CHANGE = 'status_change', _('Status Change')
        PROBATION_CONFIRMED = 'probation_confirmed', _('Probation Confirmed')
        PROBATION_EXTENDED = 'probation_extended', _('Probation Extended')
        SUSPENDED = 'suspended', _('Suspended')
        REINSTATED = 'reinstated', _('Reinstated')
        RESIGNED = 'resigned', _('Resigned')
        TERMINATED = 'terminated', _('Terminated')
        RETIRED = 'retired', _('Retired')
        CONTRACT_RENEWED = 'contract_renewed', _('Contract Renewed')
        CONTRACT_ENDED = 'contract_ended', _('Contract Ended')
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='lifecycle_logs')
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    event_date = models.DateField()
    effective_date = models.DateField()
    
    # Before/After snapshots
    old_status = models.CharField(max_length=50, blank=True)
    new_status = models.CharField(max_length=50)
    old_department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lifecycle_logs_old_dept'
    )
    new_department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lifecycle_logs_new_dept'
    )
    old_position = models.ForeignKey(
        'Position', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lifecycle_logs_old_pos'
    )
    new_position = models.ForeignKey(
        'Position', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lifecycle_logs_new_pos'
    )
    old_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    new_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Documentation
    reason = models.TextField()
    supporting_document = models.FileField(upload_to='lifecycle_docs/%Y/%m/', blank=True)
    reference_number = models.CharField(max_length=100, blank=True)  # e.g., termination letter no.
    
    # Approval
    initiated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='initiated_lifecycle_events')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_lifecycle_events')
    approval_date = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional event-specific data")
    
    class Meta:
        db_table = 'hr_employee_lifecycle_log'
        ordering = ['-event_date', '-created_at']
        indexes = [
            models.Index(fields=['employee', 'event_type']),
            models.Index(fields=['event_date']),
            models.Index(fields=['event_type']),
        ]
```

#### Enhancement: Employee Model
**Add new fields** (no existing field changes):

```python
# NEW FIELDS TO ADD to Employee model
# These extend without breaking existing logic

# Lifecycle tracking
probation_end_date = models.DateField(null=True, blank=True)
confirmation_date = models.DateField(null=True, blank=True)
last_promotion_date = models.DateField(null=True, blank=True)
previous_employer = models.CharField(max_length=255, blank=True)
termination_date = models.DateField(null=True, blank=True)
termination_reason = models.TextField(blank=True)
resignation_date = models.DateField(null=True, blank=True)
notice_period_days = models.PositiveIntegerField(default=30)
last_working_day = models.DateField(null=True, blank=True)
exit_interview_completed = models.BooleanField(default=False)
rehire_eligible = models.BooleanField(default=True)

# Emergency contact (currently missing)
emergency_contact_name = models.CharField(max_length=200, blank=True)
emergency_contact_phone = models.CharField(max_length=20, blank=True)
emergency_contact_relationship = models.CharField(max_length=100, blank=True)
blood_group = models.CharField(max_length=10, blank=True)

# System flags
is_system_user = models.BooleanField(default=True, help_text="Has login credentials")
profile_completion_percentage = models.PositiveIntegerField(default=0)
```

---

### Phase 3: Excel Bulk Import Framework

#### New Models: `BulkImportSession`, `BulkImportRecord`
```python
class BulkImportSession(AuditedModel):
    """
    Tracks Excel import sessions with validation and preview.
    """
    class ImportType(models.TextChoices):
        EMPLOYEES = 'employees', _('Employees')
        DEPARTMENTS = 'departments', _('Departments')
        POSITIONS = 'positions', _('Positions')
        ATTENDANCE = 'attendance', _('Attendance')
        LEAVE_BALANCES = 'leave_balances', _('Leave Balances')
    
    class Status(models.TextChoices):
        UPLOADED = 'uploaded', _('Uploaded')
        VALIDATING = 'validating', _('Validating')
        VALIDATED = 'validated', _('Validated')
        VALIDATION_FAILED = 'validation_failed', _('Validation Failed')
        IMPORTING = 'importing', _('Importing')
        COMPLETED = 'completed', _('Completed')
        FAILED = 'failed', _('Failed')
        CANCELLED = 'cancelled', _('Cancelled')
    
    import_type = models.CharField(max_length=30, choices=ImportType.choices)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.UPLOADED)
    
    # File tracking
    original_filename = models.CharField(max_length=255)
    uploaded_file = models.FileField(upload_to='bulk_imports/%Y/%m/')
    file_size_bytes = models.PositiveIntegerField()
    
    # Statistics
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    
    # Processing timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    validation_started_at = models.DateTimeField(null=True, blank=True)
    validation_completed_at = models.DateTimeField(null=True, blank=True)
    import_started_at = models.DateTimeField(null=True, blank=True)
    import_completed_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bulk_imports')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_imports')
    
    # Error log
    error_log = models.TextField(blank=True)
    error_file = models.FileField(upload_to='bulk_imports/errors/%Y/%m/', blank=True)
    
    class Meta:
        db_table = 'hr_bulk_import_session'
        ordering = ['-uploaded_at']


class BulkImportRecord(models.Model):
    """
    Individual row from Excel with validation status.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending Validation')
        VALID = 'valid', _('Valid')
        INVALID = 'invalid', _('Invalid')
        IMPORTED = 'imported', _('Imported')
        FAILED = 'failed', _('Import Failed')
    
    import_session = models.ForeignKey(BulkImportSession, on_delete=models.CASCADE, related_name='records')
    row_number = models.PositiveIntegerField()
    
    # Raw data from Excel
    raw_data = models.JSONField()
    
    # Validation results
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    validation_errors = models.JSONField(default=list, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)
    
    # Processed data (after transformation)
    processed_data = models.JSONField(null=True, blank=True)
    
    # Reference to created record
    created_employee_id = models.PositiveIntegerField(null=True, blank=True)
    created_object_id = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'hr_bulk_import_record'
        ordering = ['row_number']
        unique_together = ['import_session', 'row_number']
```

---

### Phase 4: Document Management

#### New Model: `EmployeeDocument`
```python
class EmployeeDocument(AuditedModel):
    """
    Centralized document storage for employees.
    """
    class DocumentCategory(models.TextChoices):
        IDENTIFICATION = 'identification', _('Identification')
        EDUCATION = 'education', _('Education')
        EMPLOYMENT = 'employment', _('Employment')
        CERTIFICATION = 'certification', _('Certification')
        MEDICAL = 'medical', _('Medical')
        LEGAL = 'legal', _('Legal')
        CONTRACT = 'contract', _('Contract')
        PERFORMANCE = 'performance', _('Performance')
        DISCIPLINARY = 'disciplinary', _('Disciplinary')
        OTHER = 'other', _('Other')
    
    class VerificationStatus(models.TextChoices):
        PENDING = 'pending', _('Pending Verification')
        VERIFIED = 'verified', _('Verified')
        REJECTED = 'rejected', _('Rejected')
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    
    document_name = models.CharField(max_length=255)
    document_category = models.CharField(max_length=30, choices=DocumentCategory.choices)
    document_type = models.CharField(max_length=100, help_text="e.g., Passport, Degree Certificate")
    
    file = models.FileField(upload_to='employee_documents/%Y/%m/')
    file_size_bytes = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=100)
    
    # Document metadata
    document_number = models.CharField(max_length=100, blank=True, help_text="e.g., Passport Number")
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    issuing_authority = models.CharField(max_length=255, blank=True)
    
    # Verification
    verification_status = models.CharField(max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_documents')
    verification_date = models.DateField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)
    
    # Access control
    is_confidential = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Alert settings
    expiry_alert_sent = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'hr_employee_document'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee', 'document_category']),
            models.Index(fields=['expiry_date']),
        ]
```

---

### Phase 5: HR Automation Service

#### New Model: `HRAutomationRule`
```python
class HRAutomationRule(AuditedModel):
    """
    Configurable automation rules for HR events.
    """
    class TriggerEvent(models.TextChoices):
        PROBATION_ENDING = 'probation_ending', _('Probation Ending Soon')
        CONTRACT_ENDING = 'contract_ending', _('Contract Ending Soon')
        DOCUMENT_EXPIRING = 'document_expiring', _('Document Expiring')
        BIRTHDAY = 'birthday', _('Employee Birthday')
        WORK_ANNIVERSARY = 'work_anniversary', _('Work Anniversary')
        APPRAISAL_DUE = 'appraisal_due', _('Appraisal Due')
        LEAVE_BALANCE_LOW = 'leave_balance_low', _('Leave Balance Low')
        NEW_HIRE_ONBOARDING = 'new_hire_onboarding', _('New Hire Onboarding')
        STATUS_CHANGE = 'status_change', _('Employment Status Change')
    
    class ActionType(models.TextChoices):
        SEND_EMAIL = 'send_email', _('Send Email')
        SEND_NOTIFICATION = 'send_notification', _('Send In-App Notification')
        CREATE_TASK = 'create_task', _('Create Task')
        UPDATE_STATUS = 'update_status', _('Update Status')
        TRIGGER_WORKFLOW = 'trigger_workflow', _('Trigger Workflow')
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    trigger_event = models.CharField(max_length=30, choices=TriggerEvent.choices)
    trigger_conditions = models.JSONField(default=dict, help_text="Additional conditions in JSON")
    trigger_days_before = models.PositiveIntegerField(default=7, help_text="Days before event to trigger")
    
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    action_config = models.JSONField(default=dict, help_text="Action configuration in JSON")
    
    # Recipients
    notify_employee = models.BooleanField(default=True)
    notify_supervisor = models.BooleanField(default=False)
    notify_hr = models.BooleanField(default=True)
    additional_recipients = models.JSONField(default=list, blank=True)
    
    # Email template
    email_template = models.ForeignKey(
        'recruitment.RecruitmentEmailTemplate', 
        on_delete=models.SET_NULL, 
        null=True, blank=True
    )
    
    is_active = models.BooleanField(default=True)
    last_run = models.DateTimeField(null=True, blank=True)
    run_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'hr_automation_rule'
        ordering = ['name']


class HRAutomationLog(TimestampedModel):
    """
    Log of automation executions.
    """
    rule = models.ForeignKey(HRAutomationRule, on_delete=models.CASCADE, related_name='logs')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='automation_logs')
    
    triggered_at = models.DateTimeField(auto_now_add=True)
    action_taken = models.CharField(max_length=255)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'hr_automation_log'
        ordering = ['-triggered_at']
```

---

## API Endpoints Plan

### Organization Structure APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/hr/positions/` | GET, POST | List/Create positions |
| `/api/v1/hr/positions/{id}/` | GET, PUT, DELETE | Position detail |
| `/api/v1/hr/positions/vacant/` | GET | List vacant positions only |
| `/api/v1/hr/positions/by-department/{dept_id}/` | GET | Positions in department |
| `/api/v1/hr/departments/{id}/org-tree/` | GET | Org chart tree structure |
| `/api/v1/hr/departments/{id}/headcount/` | GET | Headcount statistics |
| `/api/v1/hr/org-chart/` | GET | Full organization chart |

### Employee Lifecycle APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/hr/employees/{id}/lifecycle/` | GET | Employee lifecycle history |
| `/api/v1/hr/employees/{id}/promote/` | POST | Initiate promotion |
| `/api/v1/hr/employees/{id}/transfer/` | POST | Initiate transfer |
| `/api/v1/hr/employees/{id}/confirm/` | POST | Confirm probation |
| `/api/v1/hr/employees/{id}/terminate/` | POST | Initiate termination |
| `/api/v1/hr/employees/{id}/resign/` | POST | Record resignation |
| `/api/v1/hr/employees/{id}/reinstate/` | POST | Reinstate employee |

### Bulk Import APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/hr/bulk-import/upload/` | POST | Upload Excel file |
| `/api/v1/hr/bulk-import/{id}/validate/` | POST | Trigger validation |
| `/api/v1/hr/bulk-import/{id}/preview/` | GET | Preview validated data |
| `/api/v1/hr/bulk-import/{id}/import/` | POST | Execute import |
| `/api/v1/hr/bulk-import/{id}/status/` | GET | Check import status |
| `/api/v1/hr/bulk-import/template/{type}/` | GET | Download Excel template |

### Document Management APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/hr/employees/{id}/documents/` | GET, POST | List/Upload documents |
| `/api/v1/hr/documents/{id}/` | GET, PUT, DELETE | Document detail |
| `/api/v1/hr/documents/{id}/verify/` | POST | Verify document |
| `/api/v1/hr/documents/expiring/` | GET | List expiring documents |

### HR Analytics APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/hr/analytics/headcount/` | GET | Headcount by department |
| `/api/v1/hr/analytics/turnover/` | GET | Turnover rate |
| `/api/v1/hr/analytics/tenure/` | GET | Average tenure |
| `/api/v1/hr/analytics/demographics/` | GET | Age, gender breakdown |
| `/api/v1/hr/analytics/recruitment/` | GET | Recruitment metrics |

---

## Services Architecture

### New Service Classes

```
workforce/
├── services/
│   ├── __init__.py
│   ├── employee_lifecycle_service.py    # Lifecycle state machine
│   ├── position_service.py              # Position management
│   ├── bulk_import_service.py           # Excel import logic
│   ├── org_chart_service.py             # Org chart generation
│   ├── hr_automation_service.py         # Automation runner
│   ├── document_service.py              # Document management
│   └── hr_analytics_service.py          # Analytics calculations
```

### Key Service: EmployeeLifecycleService

```python
class EmployeeLifecycleService:
    """
    Handles all employee state transitions with validation and logging.
    """
    
    VALID_TRANSITIONS = {
        'probation': ['active', 'terminated'],
        'active': ['suspended', 'resigned', 'terminated', 'retired'],
        'suspended': ['active', 'terminated'],
        'resigned': [],  # Terminal state
        'terminated': [],  # Terminal state
        'retired': [],  # Terminal state
    }
    
    def promote(self, employee, new_position, new_salary, effective_date, reason, approved_by):
        """Execute promotion with all required validations and logging."""
        pass
    
    def transfer(self, employee, new_department, new_position, effective_date, reason, approved_by):
        """Execute transfer with validation and logging."""
        pass
    
    def confirm_probation(self, employee, confirmation_date, remarks, approved_by):
        """Confirm employee after probation period."""
        pass
    
    def terminate(self, employee, termination_type, termination_date, reason, approved_by):
        """Terminate employee with exit workflow."""
        pass
```

---

## Permission Groups

### New Django Groups for RBAC

| Group | Permissions |
|-------|-------------|
| `hr_admin` | Full CRUD on all HR models |
| `hr_manager` | CRUD on employees, positions, lifecycle; view payroll |
| `hr_officer` | CRUD on employees, attendance, leave; view-only positions |
| `hr_viewer` | Read-only access to all HR data |
| `department_head` | Manage own department employees, approve leave/attendance |
| `supervisor` | View/manage direct reports only |

---

## Migration Strategy

### Phase Order

1. **Phase 1**: Position model + Department enhancements (Week 1)
2. **Phase 2**: EmployeeLifecycleLog + Employee field additions (Week 1-2)
3. **Phase 3**: Bulk Import framework (Week 2)
4. **Phase 4**: Document Management (Week 2-3)
5. **Phase 5**: HR Automation (Week 3)
6. **Frontend Integration**: Throughout all phases

### Backward Compatibility Guarantees

✅ All existing tables remain unchanged
✅ All existing API endpoints continue working
✅ All existing foreign keys preserved
✅ New fields are nullable or have defaults
✅ New models use separate db_table names

---

## Questions for Stakeholder

Before proceeding, please confirm:

1. **Position vs JobTitle**: Should Position be a strict 1:1 with Employee, or can one Employee hold multiple Positions (for split roles)?

2. **Bulk Import**: What fields are required for employee Excel import? Should I generate the template?

3. **Automation Priority**: Which automation triggers are most important to implement first?

4. **Document Storage**: Should documents be stored locally or integrated with cloud storage (S3/Azure Blob)?

5. **Org Chart**: Any specific visualization requirements (vertical tree, horizontal, matrix)?

---

## Approval

| Stakeholder | Decision | Date | Notes |
|-------------|----------|------|-------|
| Project Owner | ⏳ Pending | - | - |
| Technical Lead | ⏳ Pending | - | - |

---

**Upon approval, I will begin implementation starting with Phase 1.**
