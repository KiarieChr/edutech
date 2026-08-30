# Student Management Module - Technical Documentation

## Overview

The Student Management module handles the complete lifecycle of student admission and enrollment in the school management system. It provides APIs for managing applications, admissions, and student placements.

**Base URL:** `/api/student-management/`

---

## Architecture


---

## Data Models

### 1. Application

Tracks prospective students before they become enrolled students.

| Field | Type | Description |
|-------|------|-------------|
| `first_name` | CharField | Student's first name |
| `last_name` | CharField | Student's last name |
| `middle_name` | CharField | Optional middle name |
| `date_of_birth` | DateField | Date of birth |
| `gender` | CharField | M/F |
| `birth_certificate_number` | CharField | Kenya birth certificate number |
| `nationality` | CharField | Default: "Kenyan" |
| `religion` | CharField | Religious affiliation |
| `home_address` | TextField | Physical address |
| `county` | CharField | County of residence |
| `sub_county` | CharField | Sub-county |
| `intake` | FK → Intake | Target intake cohort |
| `applying_for_curriculum` | FK → Curriculum | Target curriculum (CBC, 8-4-4, etc.) |
| `applying_for_level` | FK → CurriculumLevel | Target level |
| `applying_for_grade` | FK → GradeStructure | Target class/grade |
| `guardian_name` | CharField | Primary guardian name |
| `guardian_relationship` | CharField | Relationship to student |
| `guardian_id_number` | CharField | National ID/Passport |
| `guardian_occupation` | CharField | Guardian's occupation |
| `phone_number` | CharField | Primary contact phone |
| `email` | EmailField | Guardian email |
| `guardian2_name` | CharField | Secondary guardian name |
| `guardian2_phone` | CharField | Secondary guardian phone |
| `emergency_contact_name` | CharField | Emergency contact |
| `emergency_contact_phone` | CharField | Emergency phone |
| `medical_conditions` | TextField | Known medical conditions |
| `allergies` | TextField | Known allergies |
| `special_needs` | TextField | Special educational needs |
| `blood_group` | CharField | Blood type |
| `previous_school_name` | CharField | Previous school |
| `previous_class` | CharField | Previous class attended |
| `transfer_reason` | TextField | Reason for transfer |
| `is_transfer` | BooleanField | Transfer student flag |
| `application_status` | CharField | pending/interview/accepted/rejected/waitlist |
| `referral_source` | CharField | How they learned about school |

**File Upload Fields:**
- `birth_certificate` - Birth certificate document
- `previous_report_card` - Previous school report
- `transfer_letter` - Transfer letter
- `passport_photo` - Student photo
- `medical_report` - Medical clearance

---

### 2. Admission

Bridges the Application to a Student record. Created when an application is accepted.

| Field | Type | Description |
|-------|------|-------------|
| `application` | OneToOne → Application | Source application |
| `student` | OneToOne → Student | Created student record |
| `admission_number` | CharField | Unique admission number |
| `admission_date` | DateField | Date of admission |
| `admitted_by` | FK → User | Staff who processed admission |
| `notes` | TextField | Admission notes |

---

### 3. StudentPlacement

Tracks a student's placement in a specific class for a specific academic period.

| Field | Type | Description |
|-------|------|-------------|
| `student` | FK → Student | The enrolled student |
| `intake` | FK → Intake | Intake cohort |
| `academic_year` | FK → AcademicYear | Academic year |
| `term` | FK → Term | Academic term |
| `curriculum` | FK → Curriculum | Curriculum (CBC, 8-4-4) |
| `curriculum_level` | FK → CurriculumLevel | Level within curriculum |
| `grade` | FK → GradeStructure | Class/Grade |
| `stream` | FK → Stream | Stream (optional) |
| `session_type` | CharField | admission/reporting/promotion/repeat/transfer |
| `session_status` | CharField | active/completed/transferred/dropped |
| `start_date` | DateField | Placement start date |
| `end_date` | DateField | Placement end date |
| `previous_placement` | OneToOne → self | Link to previous placement |

---

## API Endpoints

### Applications

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/applications/` | List all applications |
| POST | `/applications/` | Create new application |
| GET | `/applications/{id}/` | Get application details |
| PUT | `/applications/{id}/` | Update application |
| DELETE | `/applications/{id}/` | Delete application |
| POST | `/applications/{id}/admit/` | **Admit applicant** |
| GET | `/applications/dashboard_stats/` | Get dashboard statistics |

### Admissions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admissions/` | List all admissions |
| POST | `/admissions/` | Create admission record |
| GET | `/admissions/{id}/` | Get admission details |
| PUT | `/admissions/{id}/` | Update admission |
| DELETE | `/admissions/{id}/` | Delete admission |

### Placements

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/placements/` | List all placements |
| POST | `/placements/` | Create placement |
| GET | `/placements/{id}/` | Get placement details |
| PUT | `/placements/{id}/` | Update placement |
| DELETE | `/placements/{id}/` | Delete placement |

**Placement Filters:**
- `academic_year` - Filter by academic year ID
- `term` - Filter by term ID
- `curriculum` - Filter by curriculum ID
- `grade` - Filter by grade ID
- `session_status` - Filter by status (active, completed, etc.)
- `session_type` - Filter by type (admission, promotion, etc.)

---

## Admission Workflow

```
┌─────────────────┐
│  Application    │
│  (pending)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Review/        │
│  Interview      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     POST /applications/{id}/admit/
│  Admit Action   │◄────────────────────────────────
└────────┬────────┘
         │
         ├── 1. Create User account
         │
         ├── 2. Create Student record
         │
         ├── 3. Create Parent account
         │
         ├── 4. Create Admission record
         │
         ├── 5. Create StudentPlacement
         │
         └── 6. Send admission email
         │
         ▼
┌─────────────────┐
│  Application    │
│  (accepted)     │
└─────────────────┘
```

---

## Admit Action Details

**Endpoint:** `POST /api/student-management/applications/{id}/admit/`

**Request Body:**
```json
{
    "admission_number": "ADM/2026/001",  // Optional - auto-generated if not provided
    "stream_id": 5                       // Optional - assign to stream
}
```

**Response:**
```json
{
    "success": true,
    "student_id": 123,
    "admission_number": "ADM/2026/001",
    "username": "john.doe",
    "password": "ADM/2026/001"
}
```

**What happens during admit:**

1. **User Account Created**
   - Username: `{first_name}.{last_name}` (auto-incremented if exists)
   - Password: Same as admission number
   - Role: `is_student = True`

2. **Student Record Created**
   - Linked to User account
   - Copies demographics from application

3. **Parent Account Created**
   - Username: `P{admission_number}`
   - Password: Same as username
   - Role: `is_parent = True`

4. **Admission Record Created**
   - Links Application → Student
   - Records admission date and processing staff

5. **StudentPlacement Created**
   - Places student in target grade
   - Session type: `admission`
   - Session status: `active`

6. **Email Notification**
   - Sends credentials to guardian email

---

## Dashboard Statistics

**Endpoint:** `GET /api/student-management/applications/dashboard_stats/`

**Response:**
```json
{
    "metrics": {
        "total_apps": 150,
        "admitted": 85,
        "pending": 45,
        "repeaters": 10,
        "transfers": 5
    },
    "trends": [
        {"name": "Jan", "apps": 20, "admitted": 15},
        {"name": "Feb", "apps": 25, "admitted": 20}
    ],
    "status_distribution": [
        {"name": "Admitted", "value": 85, "color": "#16a34a"},
        {"name": "Pending", "value": 45, "color": "#ca8a04"}
    ],
    "class_distribution": [
        {"name": "Grade 1", "boys": 20, "girls": 18},
        {"name": "Grade 2", "boys": 22, "girls": 25}
    ]
}
```

---

## Related Models (from other modules)

### accounts.Student

| Field | Type | Description |
|-------|------|-------------|
| `student` | OneToOne → User | User account |
| `admission_number` | CharField | Unique admission number |
| `date_of_birth` | DateField | DOB |
| `nationality` | CharField | Nationality |
| `religion` | CharField | Religion |
| `birth_certificate_number` | CharField | Birth certificate |
| `home_address` | TextField | Address |
| `medical_conditions` | TextField | Medical info |
| `allergies` | TextField | Allergies |
| `special_needs` | TextField | Special needs |
| `blood_group` | CharField | Blood type |
| `emergency_contact_name` | CharField | Emergency contact |
| `emergency_contact_phone` | CharField | Emergency phone |
| `previous_school_name` | CharField | Previous school |
| `previous_class` | CharField | Previous class |
| `transfer_reason` | TextField | Transfer reason |
| `intake` | FK → Intake | Intake cohort |
| `status` | CharField | active/alumni/suspended/expelled/transferred/withdrawn |

### student_settings Models

- **Intake** - Student cohorts (e.g., "January 2026 Intake")
- **AcademicYear** - Academic years with start/end dates
- **Term** - Terms within academic years
- **Curriculum** - Curriculum types (CBC, 8-4-4, IGCSE)
- **CurriculumLevel** - Levels within curriculum (Lower Primary, etc.)
- **GradeStructure** - Classes/Grades
- **Stream** - Class streams (A, B, C)

---

## Authentication

All endpoints require authentication via Token:

```
Authorization: Token <token>
```

---

## Search & Filtering

### Applications Search Fields:
- `first_name`
- `last_name`
- `email`
- `guardian_name`
- `phone_number`

### Admissions Search Fields:
- `admission_number`
- `student__student__first_name`
- `student__student__last_name`

### Placements Search Fields:
- `student__student__first_name`
- `student__student__last_name`
- `student__admission_number`

---

## Error Handling

| Status Code | Description |
|-------------|-------------|
| 400 | Bad Request - Invalid data or application already accepted |
| 401 | Unauthorized - Missing or invalid token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource does not exist |
| 500 | Server Error |

---

## Best Practices

1. **Always use transactions** - The admit action is wrapped in `@transaction.atomic` to ensure all records are created or none.

2. **Validate grade assignment** - Applications must have `applying_for_grade` set before admission.

3. **Handle email failures gracefully** - Email sending failures don't rollback the admission transaction.

4. **Check for duplicate usernames** - The system auto-increments usernames to avoid conflicts.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Mar 2026 | Initial implementation |
| 1.1 | Mar 2026 | Extended with Kenyan admission fields |
