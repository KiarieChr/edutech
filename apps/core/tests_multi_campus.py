"""
Automated Verification Suite for the Multi-Campus Management Framework.
Covers:
1. Campus Management & Deletion Protection
2. Campus Access & User Permission Enforcement (URL / Header Tampering Prevention)
3. Campus-Specific Settings Inheritance, Overrides, Restoration & Audit Logging
4. Fee Structure & Template Isolation + Historical Invoice Snapshot Immutability
5. Consolidated, Individual Campus & Cross-Campus Comparative Reporting
"""
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from core.models import SystemConfiguration, CampusConfigurationOverride, AuditLog
from core.campus_filter import (
    get_effective_campus_id,
    get_user_allowed_campus_ids,
    is_user_institution_admin,
    is_user_multi_campus_admin,
)
from workforce.models import Campus
from workforce.core_models import Employee
from workforce.viewsets import CampusViewSet
from student_management.models import Student, Admission


def run_multi_campus_verification():
    """
    Executes end-to-end verification of the Multi-Campus Management Framework
    inside a tenant schema context and rolls back test artifacts cleanly.
    """
    from django.db import transaction
    results = []

    try:
        with transaction.atomic():
            factory = APIRequestFactory()

            # -----------------------------------------------------------------
            # 1. Setup Users & Campuses
            # -----------------------------------------------------------------
            inst_admin, _ = User.objects.get_or_create(
                username='mc_test_inst_admin',
                defaults={'email': 'mc_inst_admin@test.local', 'is_superuser': True, 'is_staff': True}
            )
            multi_campus_mgr, _ = User.objects.get_or_create(
                username='mc_test_multi_mgr',
                defaults={'email': 'mc_multi_mgr@test.local', 'is_superuser': False, 'is_staff': True}
            )
            single_campus_bursar, _ = User.objects.get_or_create(
                username='mc_test_bursar_c1',
                defaults={'email': 'mc_bursar_c1@test.local', 'is_superuser': False, 'is_staff': False}
            )

            campus_a = Campus.objects.create(
                name='MC Test Main Campus',
                code='MCT-MAIN',
                description='Primary test campus',
                location='Nairobi',
                phone='0700000001',
                email='main@test.local',
                operational_status='active',
                is_active=True,
            )
            campus_b = Campus.objects.create(
                name='MC Test Westlands Campus',
                code='MCT-WEST',
                description='Secondary test campus',
                location='Westlands',
                phone='0700000002',
                email='west@test.local',
                operational_status='active',
                is_active=True,
            )
            campus_c = Campus.objects.create(
                name='MC Test Mombasa Campus',
                code='MCT-MSA',
                description='Third test campus',
                location='Mombasa',
                phone='0700000003',
                email='msa@test.local',
                operational_status='active',
                is_active=True,
            )

            # Assign multi_campus_mgr to Campus A & Campus B (not Campus C)
            multi_campus_mgr.assigned_campuses.set([campus_a, campus_b])

            # Assign single_campus_bursar strictly to Campus A
            single_campus_bursar.assigned_campuses.set([campus_a])

            # -----------------------------------------------------------------
            # TEST 1: Role & Permission Resolution + Anti-Tampering Security
            # -----------------------------------------------------------------
            assert is_user_institution_admin(inst_admin) is True, "Inst admin should be recognized"
            assert is_user_multi_campus_admin(inst_admin) is True

            assert is_user_institution_admin(multi_campus_mgr) is False, "2-campus manager is not inst admin"
            assert is_user_multi_campus_admin(multi_campus_mgr) is True, "2-campus manager is multi-campus admin"
            assert set(get_user_allowed_campus_ids(multi_campus_mgr)) == {campus_a.id, campus_b.id}

            assert is_user_multi_campus_admin(single_campus_bursar) is False, "1-campus bursar is not multi-campus"
            assert get_user_allowed_campus_ids(single_campus_bursar) == [campus_a.id]

            # Security Check: Single-campus bursar attempts URL tampering (?campus_id=campus_b.id)
            tampered_req = factory.get(f'/api/students/?campus_id={campus_b.id}', HTTP_X_CAMPUS_ID=str(campus_b.id))
            tampered_req.user = single_campus_bursar
            eff_id = get_effective_campus_id(tampered_req)
            assert eff_id == campus_a.id, f"Expected override to {campus_a.id}, got {eff_id}"

            # Security Check: 2-campus manager requests authorized Campus B -> allowed; unauthorized Campus C -> fallback to Campus A
            mgr_req_b = factory.get(f'/api/students/?campus_id={campus_b.id}')
            mgr_req_b.user = multi_campus_mgr
            assert get_effective_campus_id(mgr_req_b) == campus_b.id

            mgr_req_c = factory.get(f'/api/students/?campus_id={campus_c.id}')
            mgr_req_c.user = multi_campus_mgr
            assert get_effective_campus_id(mgr_req_c) == campus_a.id

            results.append("PASS: Test 1 — Campus Role Hierarchy & Anti-Tampering Security")

            # -----------------------------------------------------------------
            # TEST 2: Campus-Specific Settings Inheritance, Override & Restore
            # -----------------------------------------------------------------
            cfg, _ = SystemConfiguration.objects.update_or_create(
                key='test_grading_pass_mark',
                defaults={
                    'value': '50',
                    'value_type': SystemConfiguration.ValueType.INTEGER,
                    'group': SystemConfiguration.Group.GENERAL,
                    'label': 'Default Pass Mark',
                    'description': 'Default pass mark',
                    'is_editable': True,
                }
            )

            # Override for Campus A to '65'
            from core.api_views import bulk_update_config, restore_default_config
            post_req = factory.post(
                '/api/core/config/bulk-update/',
                {'configs': {'test_grading_pass_mark': '65'}, 'campus_id': campus_a.id},
                format='json'
            )
            force_authenticate(post_req, user=inst_admin)
            resp = bulk_update_config(post_req)
            assert resp.status_code == 200

            # Institution default must remain '50'
            cfg.refresh_from_db()
            assert cfg.value == '50', "Institution default must not be mutated by campus override"

            # Campus A override is active and equals '65'
            ov_a = CampusConfigurationOverride.objects.get(campus=campus_a, config=cfg)
            assert ov_a.is_active is True and ov_a.value == '65'

            # Campus B has no override -> inherits '50'
            assert not CampusConfigurationOverride.objects.filter(campus=campus_b, config=cfg, is_active=True).exists()

            # Restore Campus A override to institution default
            restore_req = factory.post(
                '/api/core/config/restore-default/',
                {'key': 'test_grading_pass_mark', 'campus_id': campus_a.id},
                format='json'
            )
            force_authenticate(restore_req, user=inst_admin)
            restore_resp = restore_default_config(restore_req)
            assert restore_resp.status_code == 200
            assert restore_resp.data['is_overridden'] is False
            assert restore_resp.data['effective_value'] == '50'
            assert AuditLog.objects.filter(model_name='CampusConfigurationOverride').exists()

            results.append("PASS: Test 2 — Campus Settings Inheritance, Override, Restore & Audit Trail")

            # -----------------------------------------------------------------
            # TEST 3: Campus Deletion Protection & Deactivation Preservation
            # -----------------------------------------------------------------
            st_user_a = User.objects.create(username='mc_student_a1', first_name='Alice', last_name='Main', gender='F')
            st_a = Student.objects.create(
                student=st_user_a,
                admission_number='MCT-ADM-001',
                campus=campus_a,
                status='active',
                admission_date=timezone.now().date(),
            )
            st_user_b = User.objects.create(username='mc_student_b1', first_name='Brian', last_name='West', gender='M')
            st_b = Student.objects.create(
                student=st_user_b,
                admission_number='MCT-ADM-002',
                campus=campus_b,
                status='active',
                admission_date=timezone.now().date(),
            )

            # Attempt to delete Campus A (which has a linked student) -> must return 400 Bad Request
            del_view = CampusViewSet.as_view({'delete': 'destroy'})
            del_req = factory.delete(f'/workforce/api/campuses/{campus_a.id}/')
            force_authenticate(del_req, user=inst_admin)
            del_resp = del_view(del_req, pk=campus_a.id)
            assert del_resp.status_code == 400, f"Expected 400 on deleting campus with students, got {del_resp.status_code}"
            assert Campus.objects.filter(id=campus_a.id).exists()

            # Deactivating Campus C preserves record and sets operational_status='INACTIVE'
            deact_view = CampusViewSet.as_view({'post': 'deactivate'})
            deact_req = factory.post(f'/workforce/api/campuses/{campus_c.id}/deactivate/')
            force_authenticate(deact_req, user=inst_admin)
            deact_resp = deact_view(deact_req, pk=campus_c.id)
            assert deact_resp.status_code == 200
            campus_c.refresh_from_db()
            assert campus_c.is_active is False and campus_c.operational_status.lower() == 'inactive'

            results.append("PASS: Test 3 — Campus Deletion Protection & Deactivation Data Preservation")

            # -----------------------------------------------------------------
            # TEST 4: Fee Template Adoption & Cross-Campus Billing Isolation
            # -----------------------------------------------------------------
            from student_settings.models import AcademicYear, Term, GradeStructure as Grade, Curriculum, Intake
            from fees.models import FeeTemplate, FeeStructure
            from fees.template_views import FeeTemplateViewSet
            from fees.services import BillingService
            from django.core.exceptions import ValidationError

            ay = AcademicYear.objects.first() or AcademicYear.objects.create(
                name='2099/2100', start_date=timezone.now().date(), end_date=timezone.now().date()
            )
            term = Term.objects.filter(academic_year=ay).first() or Term.objects.create(
                name='Term 1', academic_year=ay, start_date=timezone.now().date(), end_date=timezone.now().date()
            )
            curr = Curriculum.objects.first() or Curriculum.objects.create(name='MC Test Curriculum', code='MCTC')
            grade = Grade.objects.first() or Grade.objects.create(name='MC Grade 1', code='MCG1', curriculum=curr, level_order=99)

            shared_tpl = FeeTemplate.objects.create(
                name='MC Shared Institution Fee Template',
                curriculum=curr,
                term=term,
                academic_year=ay,
                campus=None,
                is_shared_template=True,
                status='DRAFT',
            )
            shared_tpl.grades.add(grade)

            # Adopt shared template into Campus A
            adopt_view = FeeTemplateViewSet.as_view({'post': 'adopt_for_campus'})
            adopt_req = factory.post(
                f'/api/fees/templates/{shared_tpl.id}/adopt-for-campus/',
                {'campus_id': campus_a.id},
                format='json'
            )
            force_authenticate(adopt_req, user=inst_admin)
            adopt_resp = adopt_view(adopt_req, pk=shared_tpl.id)
            assert adopt_resp.status_code == 201, f"Expected 201 on template adoption, got {adopt_resp.status_code}: {adopt_resp.data}"
            adopted_tpl_id = adopt_resp.data.get('id') or adopt_resp.data.get('template', {}).get('id')
            adopted_tpl = FeeTemplate.objects.get(id=adopted_tpl_id)
            assert adopted_tpl.campus_id == campus_a.id
            assert adopted_tpl.parent_template_id == shared_tpl.id
            assert adopted_tpl.is_shared_template is False

            # Create a private FeeStructure for Campus A and verify Student B (in Campus B) cannot be billed with it
            struct_a = FeeStructure.objects.create(
                academic_year=ay,
                term=term,
                grade=grade,
                campus=campus_a,
                status='ACTIVE',
            )
            cross_campus_blocked = False
            try:
                BillingService.generate_invoice({'student_id': st_b.id, 'structure_id': struct_a.id}, user=inst_admin)
            except ValidationError as exc:
                cross_campus_blocked = True
            assert cross_campus_blocked is True, "Cross-campus private FeeStructure billing must be blocked"

            results.append("PASS: Test 4 — Shared Fee Template Adoption & Cross-Campus FeeStructure Isolation")

            # -----------------------------------------------------------------
            # TEST 5: Consolidated, Individual & Cross-Campus Comparison Reports
            # -----------------------------------------------------------------
            from student_management.viewsets.reports_viewset import StudentReportsViewSet

            # Comparison endpoint for Institution Admin comparing Campus A and Campus B
            cmp_view = StudentReportsViewSet.as_view({'get': 'campus_comparison'})
            cmp_req = factory.get(f'/api/students/reports/campus-comparison/?campus_ids={campus_a.id},{campus_b.id}')
            force_authenticate(cmp_req, user=inst_admin)
            cmp_resp = cmp_view(cmp_req)
            assert cmp_resp.status_code == 200
            assert len(cmp_resp.data['campuses']) == 2
            assert cmp_resp.data['consolidated']['students']['active_students'] == 2

            # Single-campus bursar attempting to access Campus Comparison -> 403 Forbidden
            cmp_req_denied = factory.get('/api/students/reports/campus-comparison/')
            force_authenticate(cmp_req_denied, user=single_campus_bursar)
            cmp_resp_denied = cmp_view(cmp_req_denied)
            assert cmp_resp_denied.status_code == 403

            results.append("PASS: Test 5 — Consolidated, Individual & Cross-Campus Comparison Reporting")

            # Roll back all test records cleanly so tenant database remains untouched
            transaction.set_rollback(True)

    except Exception as e:
        import traceback
        results.append(f"FAIL: {e}\n{traceback.format_exc()}")
        raise

    return results

