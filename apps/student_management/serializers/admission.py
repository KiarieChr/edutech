from rest_framework import serializers
from student_management.models.admission import Admission
from student_management.models.profiles import Student, Parent
from accounts.models import User
from student_settings.models import Intake, Enrollment
from django.utils import timezone

try:
    from transport.models import StudentAssignment, Route, Stop
    HAS_TRANSPORT = True
except ImportError:
    HAS_TRANSPORT = False


class AdmissionSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    student_name = serializers.CharField(source='student.student.get_full_name', read_only=True)
    
    # Enrollment details - writable
    intake = serializers.PrimaryKeyRelatedField(queryset=Intake.objects.all(), source='student.intake', required=False, allow_null=True)
    grade_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    stream_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    academic_year_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    term_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    curriculum_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    curriculum_level_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    stay_status = serializers.CharField(write_only=True, required=False, allow_null=True)

    # Student Personal & Biodata fields - writable
    first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    gender = serializers.CharField(write_only=True, required=False, allow_blank=True)
    student_email = serializers.EmailField(write_only=True, required=False, allow_null=True, allow_blank=True)
    student_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(write_only=True, required=False, allow_null=True)
    nationality = serializers.CharField(write_only=True, required=False, allow_blank=True)
    religion = serializers.CharField(write_only=True, required=False, allow_blank=True)
    birth_certificate_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    home_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    blood_group = serializers.CharField(write_only=True, required=False, allow_blank=True)
    medical_conditions = serializers.CharField(write_only=True, required=False, allow_blank=True)
    allergies = serializers.CharField(write_only=True, required=False, allow_blank=True)
    special_needs = serializers.CharField(write_only=True, required=False, allow_blank=True)
    emergency_contact_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    emergency_contact_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    emergency_contact_relationship = serializers.CharField(write_only=True, required=False, allow_blank=True)
    previous_school_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    previous_school_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    previous_class = serializers.CharField(write_only=True, required=False, allow_blank=True)
    status = serializers.CharField(source='student.status', required=False)

    # Parent & Guardian fields - writable
    guardian_first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    guardian_last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    guardian_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    guardian_email = serializers.EmailField(write_only=True, required=False, allow_null=True, allow_blank=True)
    guardian_relationship = serializers.CharField(write_only=True, required=False, allow_blank=True)

    secondary_guardian_first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    secondary_guardian_last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    secondary_guardian_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    secondary_guardian_email = serializers.EmailField(write_only=True, required=False, allow_null=True, allow_blank=True)
    secondary_guardian_relationship = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # Transport fields - writable
    transport_enabled = serializers.BooleanField(write_only=True, required=False)
    route_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    stop_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    transport_type = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # Read-only display fields
    grade = serializers.SerializerMethodField()
    stream = serializers.SerializerMethodField()
    academic_year = serializers.SerializerMethodField()
    curriculum = serializers.SerializerMethodField()
    curriculum_level = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    entry_type = serializers.SerializerMethodField()
    passport_photo_url = serializers.SerializerMethodField()
    applying_for_grade_name = serializers.SerializerMethodField()
    applying_for_curriculum_name = serializers.SerializerMethodField()

    class Meta:
        model = Admission
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')

    def get_applicant_name(self, obj):
        if hasattr(obj, 'application') and obj.application:
            return f"{obj.application.first_name} {obj.application.last_name}".strip()
        user = obj.student.student
        return f"{user.first_name} {user.last_name}".strip() or user.username

    def get_passport_photo_url(self, obj):
        request = self.context.get('request')
        photo = getattr(getattr(obj, 'application', None), 'passport_photo', None)
        if photo and photo.name:
            return request.build_absolute_uri(photo.url) if request else photo.url
        return None

    def get_applying_for_grade_name(self, obj):
        grade = getattr(getattr(obj, 'application', None), 'applying_for_grade', None)
        return grade.name if grade else ''

    def get_applying_for_curriculum_name(self, obj):
        curriculum = getattr(getattr(obj, 'application', None), 'applying_for_curriculum', None)
        return curriculum.name if curriculum else ''

    def get_grade(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.grade.id if active_enrollment and active_enrollment.grade else None

    def get_stream(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.stream.id if active_enrollment and active_enrollment.stream else None

    def get_class_name(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        if active_enrollment and active_enrollment.grade:
            return f"{active_enrollment.grade.name} {active_enrollment.stream.name if active_enrollment.stream else ''}".strip()
        return "N/A"

    def get_entry_type(self, obj):
        if getattr(getattr(obj, 'application', None), 'is_transfer', False):
            return "Transfer In"
        return "New Admission"

    def get_academic_year(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.academic_year_id if active_enrollment else None

    def get_curriculum(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.curriculum_id if active_enrollment else None

    def get_curriculum_level(self, obj):
        active_enrollment = obj.student.enrollments.filter(status='active', is_active=True).last()
        return active_enrollment.curriculum_level_id if active_enrollment else None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        student = instance.student
        user = student.student

        # Biodata & Identity
        ret['student_id'] = student.id
        ret['first_name'] = user.first_name
        ret['last_name'] = user.last_name
        ret['gender'] = user.gender
        ret['student_email'] = user.email
        ret['student_phone'] = getattr(user, 'phone', '')
        ret['date_of_birth'] = student.date_of_birth
        ret['nationality'] = student.nationality or 'Kenyan'
        ret['religion'] = student.religion or ''
        ret['birth_certificate_number'] = student.birth_certificate_number or ''
        ret['home_address'] = student.home_address or ''
        ret['blood_group'] = student.blood_group or ''
        ret['medical_conditions'] = student.medical_conditions or ''
        ret['allergies'] = student.allergies or ''
        ret['special_needs'] = student.special_needs or ''
        ret['emergency_contact_name'] = student.emergency_contact_name or ''
        ret['emergency_contact_phone'] = student.emergency_contact_phone or ''
        ret['emergency_contact_relationship'] = student.emergency_contact_relationship or ''
        ret['previous_school_name'] = student.previous_school_name or ''
        ret['previous_school_address'] = student.previous_school_address or ''
        ret['previous_class'] = student.previous_class or ''
        ret['status'] = student.status

        # Academic / Enrollment
        active_enr = student.enrollments.filter(status='active', is_active=True).last()
        ret['stay_status'] = getattr(active_enr, 'stay_status', 'day_scholar') if active_enr else 'day_scholar'
        ret['academic_year_id'] = active_enr.academic_year_id if active_enr else None
        ret['term_id'] = active_enr.term_id if active_enr else None
        ret['grade_id'] = active_enr.grade_id if active_enr else None
        ret['stream_id'] = active_enr.stream_id if active_enr else None
        ret['curriculum_id'] = active_enr.curriculum_id if active_enr else None
        ret['curriculum_level_id'] = active_enr.curriculum_level_id if active_enr else None
        ret['intake_id'] = student.intake_id

        # Parent / Guardian details
        parents = list(student.parents.all())
        primary_parent = parents[0] if parents else None
        secondary_parent = parents[1] if len(parents) > 1 else None

        app = getattr(instance, 'application', None)
        if primary_parent:
            ret['guardian_first_name'] = primary_parent.first_name
            ret['guardian_last_name'] = primary_parent.last_name
            ret['guardian_phone'] = primary_parent.phone or ''
            ret['guardian_email'] = primary_parent.email or ''
            ret['guardian_relationship'] = primary_parent.relation_ship or ''
        else:
            g_name = getattr(app, 'guardian_name', '') or ''
            parts = g_name.split()
            ret['guardian_first_name'] = parts[0] if parts else ''
            ret['guardian_last_name'] = " ".join(parts[1:]) if len(parts) > 1 else ''
            ret['guardian_phone'] = getattr(app, 'phone_number', '') or ''
            ret['guardian_email'] = getattr(app, 'email', '') or ''
            ret['guardian_relationship'] = getattr(app, 'guardian_relationship', '') or ''

        ret['secondary_guardian_first_name'] = secondary_parent.first_name if secondary_parent else ''
        ret['secondary_guardian_last_name'] = secondary_parent.last_name if secondary_parent else ''
        ret['secondary_guardian_phone'] = secondary_parent.phone if secondary_parent else ''
        ret['secondary_guardian_email'] = secondary_parent.email if secondary_parent else ''
        ret['secondary_guardian_relationship'] = secondary_parent.relation_ship if secondary_parent else ''

        # Transport assignment
        if HAS_TRANSPORT:
            assignment = student.transport_assignments.filter(is_active=True).first()
            if assignment:
                ret['transport_enabled'] = True
                ret['assignment_id'] = assignment.id
                ret['route_id'] = assignment.route_id
                ret['stop_id'] = assignment.stop_id
                ret['transport_type'] = assignment.transport_type
                ret['route_name'] = assignment.route.route_name if assignment.route else ''
                ret['stop_name'] = assignment.stop.stop_name if assignment.stop else ''
            else:
                ret['transport_enabled'] = False
                ret['assignment_id'] = None
                ret['route_id'] = None
                ret['stop_id'] = None
                ret['transport_type'] = 'two_way'
                ret['route_name'] = ''
                ret['stop_name'] = ''
        else:
            ret['transport_enabled'] = False

        return ret

    def update(self, instance, validated_data):
        student = instance.student
        user = student.student

        # ── 1. Update User Identity ───────────────────────────────────────────
        user_updated = False
        for field in ['first_name', 'last_name', 'gender']:
            val = validated_data.pop(field, None)
            if val is not None:
                setattr(user, field, val)
                user_updated = True

        email_val = validated_data.pop('student_email', None)
        if email_val is not None:
            user.email = email_val
            user_updated = True

        phone_val = validated_data.pop('student_phone', None)
        if phone_val is not None and hasattr(user, 'phone'):
            user.phone = phone_val
            user_updated = True

        if user_updated:
            user.save()

        # ── 2. Update Student Biodata ─────────────────────────────────────────
        student_data = validated_data.pop('student', {})
        student_status = student_data.get('status') or validated_data.pop('status', None)
        if student_status:
            student.status = student_status

        intake_obj = student_data.get('intake')
        if intake_obj is not None:
            student.intake = intake_obj

        student_fields = [
            'date_of_birth', 'nationality', 'religion', 'birth_certificate_number',
            'home_address', 'blood_group', 'medical_conditions', 'allergies',
            'special_needs', 'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relationship', 'previous_school_name',
            'previous_school_address', 'previous_class'
        ]
        student_updated = False
        for field in student_fields:
            val = validated_data.pop(field, None)
            if val is not None:
                setattr(student, field, val)
                student_updated = True

        # Sync admission number / date if provided
        adm_no = validated_data.get('admission_number')
        if adm_no and adm_no != instance.admission_number:
            student.admission_number = adm_no
            student_updated = True

        adm_date = validated_data.get('admission_date')
        if adm_date:
            student.admission_date = adm_date
            student_updated = True

        if student_status or intake_obj or student_updated:
            student.save()

        # ── 3. Update Parent / Guardian ───────────────────────────────────────
        g_first = validated_data.pop('guardian_first_name', None)
        g_last = validated_data.pop('guardian_last_name', None)
        g_phone = validated_data.pop('guardian_phone', None)
        g_email = validated_data.pop('guardian_email', None)
        g_rel = validated_data.pop('guardian_relationship', None)

        if any(v is not None for v in [g_first, g_last, g_phone, g_email, g_rel]):
            existing_parent = student.parents.first()
            if existing_parent:
                if g_first is not None:
                    existing_parent.first_name = g_first
                    existing_parent.user.first_name = g_first
                if g_last is not None:
                    existing_parent.last_name = g_last
                    existing_parent.user.last_name = g_last
                if g_phone is not None:
                    existing_parent.phone = g_phone
                if g_email is not None:
                    existing_parent.email = g_email
                    existing_parent.user.email = g_email
                if g_rel is not None:
                    existing_parent.relation_ship = g_rel
                existing_parent.user.save()
                existing_parent.save()
            else:
                # Create parent user and record
                p_user = User.objects.create_user(
                    username=f"P_{student.admission_number or student.id}",
                    first_name=g_first or 'Parent',
                    last_name=g_last or '',
                    email=g_email or '',
                    is_parent=True
                )
                Parent.objects.create(
                    user=p_user,
                    student=student,
                    first_name=g_first or 'Parent',
                    last_name=g_last or '',
                    phone=g_phone or '',
                    email=g_email or '',
                    relation_ship=g_rel or 'Other'
                )

            # Sync with application record if attached
            if hasattr(instance, 'application') and instance.application:
                app = instance.application
                full_g_name = f"{g_first or ''} {g_last or ''}".strip()
                if full_g_name:
                    app.guardian_name = full_g_name
                if g_phone:
                    app.phone_number = g_phone
                if g_email:
                    app.email = g_email
                if g_rel:
                    app.guardian_relationship = g_rel
                app.save()

        # Handle secondary guardian
        sec_first = validated_data.pop('secondary_guardian_first_name', None)
        sec_last = validated_data.pop('secondary_guardian_last_name', None)
        sec_phone = validated_data.pop('secondary_guardian_phone', None)
        sec_email = validated_data.pop('secondary_guardian_email', None)
        sec_rel = validated_data.pop('secondary_guardian_relationship', None)

        if any(v is not None for v in [sec_first, sec_last, sec_phone, sec_email, sec_rel]):
            all_parents = list(student.parents.all())
            if len(all_parents) > 1:
                sec_parent = all_parents[1]
                if sec_first is not None:
                    sec_parent.first_name = sec_first
                if sec_last is not None:
                    sec_parent.last_name = sec_last
                if sec_phone is not None:
                    sec_parent.phone = sec_phone
                if sec_email is not None:
                    sec_parent.email = sec_email
                if sec_rel is not None:
                    sec_parent.relation_ship = sec_rel
                sec_parent.save()
            elif any(v for v in [sec_first, sec_last, sec_phone]):
                sec_user = User.objects.create_user(
                    username=f"P2_{student.admission_number or student.id}",
                    first_name=sec_first or 'Guardian',
                    last_name=sec_last or '',
                    email=sec_email or '',
                    is_parent=True
                )
                Parent.objects.create(
                    user=sec_user,
                    student=student,
                    first_name=sec_first or 'Guardian',
                    last_name=sec_last or '',
                    phone=sec_phone or '',
                    email=sec_email or '',
                    relation_ship=sec_rel or 'Other'
                )

        # ── 4. Update Academic & Enrollment ───────────────────────────────────
        grade_id = validated_data.pop('grade_id', None)
        stream_id = validated_data.pop('stream_id', None)
        academic_year_id = validated_data.pop('academic_year_id', None)
        term_id = validated_data.pop('term_id', None)
        curriculum_id = validated_data.pop('curriculum_id', None)
        curriculum_level_id = validated_data.pop('curriculum_level_id', None)
        stay_status = validated_data.pop('stay_status', None)

        enrollment_updates = {}
        if grade_id is not None:
            enrollment_updates['grade_id'] = grade_id
        if stream_id is not None:
            enrollment_updates['stream_id'] = stream_id
        if academic_year_id is not None:
            enrollment_updates['academic_year_id'] = academic_year_id
        if term_id is not None:
            enrollment_updates['term_id'] = term_id
        if curriculum_id is not None:
            enrollment_updates['curriculum_id'] = curriculum_id
        if curriculum_level_id is not None:
            enrollment_updates['curriculum_level_id'] = curriculum_level_id
        if stay_status is not None:
            enrollment_updates['stay_status'] = stay_status

        if enrollment_updates:
            active_enrollment = student.enrollments.filter(status='active', is_active=True).last()
            if active_enrollment:
                # If academic year changed and no explicit term provided, pick matching term
                new_year_id = enrollment_updates.get('academic_year_id')
                if new_year_id and not term_id and new_year_id != active_enrollment.academic_year_id:
                    from student_settings.models import Term as TermModel
                    matching_term = TermModel.objects.filter(
                        academic_year_id=new_year_id, is_current=True, is_deleted=False
                    ).first()
                    if not matching_term:
                        matching_term = TermModel.objects.filter(
                            academic_year_id=new_year_id, is_deleted=False
                        ).order_by('start_date').first()
                    if matching_term:
                        enrollment_updates['term_id'] = matching_term.id

                for field, value in enrollment_updates.items():
                    setattr(active_enrollment, field, value)
                active_enrollment.save()
            else:
                from student_settings.models import AcademicYear, Term
                year_id = enrollment_updates.get('academic_year_id')
                if not year_id:
                    year = AcademicYear.objects.filter(is_current=True).first()
                    year_id = year.pk if year else None

                t_id = enrollment_updates.get('term_id')
                term = Term.objects.filter(id=t_id).first() if t_id else (
                    Term.objects.filter(academic_year_id=year_id, is_current=True).first()
                )
                final_grade_id = enrollment_updates.get('grade_id')

                req_user = self.context['request'].user if 'request' in self.context else None
                if year_id and term and final_grade_id:
                    Enrollment.objects.create(
                        student=student,
                        intake=intake_obj or getattr(student, 'intake', None),
                        academic_year_id=year_id,
                        term=term,
                        grade_id=final_grade_id,
                        stream_id=enrollment_updates.get('stream_id'),
                        campus=instance.campus,
                        curriculum_id=enrollment_updates.get('curriculum_id') or getattr(getattr(instance, 'application', None), 'applying_for_curriculum_id', None),
                        curriculum_level_id=enrollment_updates.get('curriculum_level_id'),
                        stay_status=enrollment_updates.get('stay_status', 'day_scholar'),
                        enrollment_type='new_admission',
                        status='active',
                        is_active=True,
                        enrollment_date=timezone.now().date(),
                        created_by=req_user,
                        updated_by=req_user
                    )

        # ── 5. Update Transport Route Assignment ──────────────────────────────
        transport_enabled = validated_data.pop('transport_enabled', None)
        route_id = validated_data.pop('route_id', None)
        stop_id = validated_data.pop('stop_id', None)
        trans_type = validated_data.pop('transport_type', None)

        if HAS_TRANSPORT and (transport_enabled is not None or route_id is not None):
            active_assignment = student.transport_assignments.filter(is_active=True).first()

            if transport_enabled is False or (transport_enabled is None and route_id is None and active_assignment):
                if transport_enabled is False and active_assignment:
                    active_assignment.is_active = False
                    active_assignment.end_date = timezone.now().date()
                    active_assignment.save()
            elif transport_enabled is True or route_id:
                if route_id and stop_id:
                    if active_assignment:
                        active_assignment.route_id = route_id
                        active_assignment.stop_id = stop_id
                        if trans_type:
                            active_assignment.transport_type = trans_type
                        active_assignment.is_active = True
                        active_assignment.save()
                    else:
                        StudentAssignment.objects.create(
                            student=student,
                            route_id=route_id,
                            stop_id=stop_id,
                            transport_type=trans_type or 'two_way',
                            start_date=timezone.now().date(),
                            is_active=True
                        )

        return super().update(instance, validated_data)
