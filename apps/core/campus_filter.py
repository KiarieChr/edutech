"""
Global Campus Filter Engine & Security Scoping
Fahari Academia Multi-Campus Scoping & Access Control

Provides:
- get_user_assigned_campus_id(user)
- get_user_allowed_campus_ids(user)
- is_user_institution_admin(user)
- is_user_multi_campus_admin(user)
- get_request_campus_id(request)
- get_effective_campus_id(request)
- get_effective_campus_id_for_user(user, params=None)
- scope_queryset_by_campus(queryset, request, campus_field=None)
- CampusPermissionMixin (DRF ViewSet mixin)
- CampusFilterBackend (DRF FilterBackend)
"""

from rest_framework.filters import BaseFilterBackend
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q


def get_user_assigned_campus_id(user):
    """
    Extracts the assigned primary campus ID for a given user.
    Checks user.campus_id, user.campus, user.employee_profile, assigned_campuses, and staff_profile.
    Returns integer ID or None.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    # 1. Direct campus_id or campus attribute on User
    cid = getattr(user, 'campus_id', None)
    if cid is not None:
        try:
            return int(cid)
        except (ValueError, TypeError):
            pass

    campus_obj = getattr(user, 'campus', None)
    if campus_obj is not None and hasattr(campus_obj, 'id'):
        return campus_obj.id

    # 2. Linked Employee profile
    employee_profile = getattr(user, 'employee_profile', None)
    if employee_profile:
        emp_campus_id = getattr(employee_profile, 'campus_id', None)
        if emp_campus_id is not None:
            return emp_campus_id
        emp_campus = getattr(employee_profile, 'campus', None)
        if emp_campus is not None and hasattr(emp_campus, 'id'):
            return emp_campus.id

    # 3. Linked staff_profile (legacy/alias fallback)
    staff_profile = getattr(user, 'staff_profile', None)
    if staff_profile:
        sp_campus_id = getattr(staff_profile, 'campus_id', None)
        if sp_campus_id is not None:
            return sp_campus_id

    return None


def get_user_allowed_campus_ids(user):
    """
    Returns sorted list of Campus IDs explicitly assigned to this user
    (via employee_profile, assigned_campuses M2M, or administered_campuses).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return []
    if hasattr(user, 'get_allowed_campus_ids') and callable(user.get_allowed_campus_ids):
        try:
            return user.get_allowed_campus_ids()
        except Exception:
            pass
    cid = get_user_assigned_campus_id(user)
    return [cid] if cid is not None else []


def is_user_institution_admin(user):
    """
    Determines if user is an Institution Administrator with full cross-campus visibility,
    consolidated reporting ('All Campuses'), and institution-wide configuration rights.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if getattr(user, 'is_superuser', False):
        return True

    if hasattr(user, 'is_institution_admin') and isinstance(user.is_institution_admin, bool):
        return user.is_institution_admin

    for perm in [
        'accounts.is_multi_campus_admin',
        'workforce.is_multi_campus_admin',
        'accounts.can_view_all_campuses',
        'workforce.can_view_all_campuses',
        'core.view_all_campuses'
    ]:
        if user.has_perm(perm):
            return True

    group_names = []
    try:
        group_names = [g.name.lower() for g in user.groups.all()]
        if any(role in group_names for role in [
            'super admin', 'super_admin', 'institution admin', 'institution_admin',
            'director', 'administrator', 'system admin', 'hq admin'
        ]):
            return True
    except Exception:
        pass

    if get_user_allowed_campus_ids(user):
        return False

    if getattr(user, 'is_staff', False) or any('admin' in g for g in group_names):
        return True

    return False


def is_user_multi_campus_admin(user):
    """
    Determines if user can switch across campuses:
      - True for Institution Administrators (all campuses)
      - True for Campus Administrators assigned to > 1 campus
      - False for single-campus users (e.g. Campus Bursar)
    """
    if is_user_institution_admin(user):
        return True
    return len(get_user_allowed_campus_ids(user)) > 1


def get_request_campus_id(request):
    """
    Extracts raw campus_id from query parameters, request headers, or body.
    Returns integer ID, or None if omitted, empty, or 'all'.
    """
    if not request:
        return None

    raw_id = None
    query_params = getattr(request, 'query_params', getattr(request, 'GET', {}))
    if query_params:
        raw_id = query_params.get('campus_id') or query_params.get('campus')

    if raw_id is None and hasattr(request, 'headers'):
        raw_id = request.headers.get('X-Campus-Id')

    if raw_id is None and hasattr(request, 'META'):
        raw_id = request.META.get('HTTP_X_CAMPUS_ID')

    if raw_id is None and hasattr(request, 'data') and isinstance(request.data, dict):
        raw_id = request.data.get('campus_id') or request.data.get('campus')

    if raw_id is None or str(raw_id).strip().lower() in ['all', 'none', '', 'null', 'undefined']:
        return None

    try:
        return int(raw_id)
    except (ValueError, TypeError):
        return None


def get_effective_campus_id(request):
    """
    Determines the effective campus_id that MUST be enforced for this request:
    1. If the user is an Institution Administrator:
       Respects the requested campus_id if provided, or returns None ('All Campuses').
    2. If the user is assigned to specific campus(es) (NOT an Institution Administrator):
       - If assigned to a single campus: strictly forces that campus_id, overriding any URL tampering.
       - If assigned to multiple campuses: allows switching among their assigned campuses;
         if requested campus_id is unauthorized or omitted, defaults to their primary assigned campus.
    """
    if not request:
        return None

    requested_id = get_request_campus_id(request)
    user = getattr(request, 'user', None)

    if user and getattr(user, 'is_authenticated', False):
        if is_user_institution_admin(user):
            return requested_id

        allowed_ids = get_user_allowed_campus_ids(user)
        if allowed_ids:
            if requested_id is not None and requested_id in allowed_ids:
                return requested_id
            # Override unauthorized or omitted campus_id with primary assigned campus
            return allowed_ids[0]

    return requested_id


def get_effective_campus_id_for_user(user, params=None):
    """
    Determines effective campus ID for report services or background tasks
    where only user and parameter dictionary are provided.
    """
    requested_id = None
    if params:
        raw = params.get('campus_id') or params.get('campus')
        if raw is not None and str(raw).strip().lower() not in ['all', 'none', '', 'null', 'undefined']:
            try:
                requested_id = int(raw)
            except (ValueError, TypeError):
                requested_id = None

    if user and getattr(user, 'is_authenticated', False):
        if is_user_institution_admin(user):
            return requested_id

        allowed_ids = get_user_allowed_campus_ids(user)
        if allowed_ids:
            if requested_id is not None and requested_id in allowed_ids:
                return requested_id
            return allowed_ids[0]

    return requested_id


def scope_queryset_by_campus(queryset, request, campus_field=None):
    """
    Scopes a Django QuerySet to the effective campus_id.
    - Non-institution admins are strictly scoped to their authorized campus.
    - Institution admins are scoped to their requested campus (or all if omitted).
    Automatically resolves model field relationships (campus, student__campus, etc.)
    """
    effective_campus_id = get_effective_campus_id(request)
    if effective_campus_id is None:
        return queryset

    # If explicit field path provided, use it
    if campus_field:
        try:
            return queryset.filter(**{f"{campus_field}_id": effective_campus_id})
        except Exception:
            try:
                return queryset.filter(**{campus_field: effective_campus_id})
            except Exception:
                pass

    # Inspect model fields for direct or related campus links
    model = getattr(queryset, 'model', None)
    if not model:
        return queryset

    model_field_names = [f.name for f in model._meta.get_fields()]

    # 1. Direct 'campus' FK
    if 'campus' in model_field_names:
        return queryset.filter(campus_id=effective_campus_id)

    # 2. Linked via 'student'
    if 'student' in model_field_names:
        return queryset.filter(student__campus_id=effective_campus_id)

    # 3. Linked via 'admission'
    if 'admission' in model_field_names:
        return queryset.filter(admission__campus_id=effective_campus_id)

    # 4. Linked via 'employee'
    if 'employee' in model_field_names:
        return queryset.filter(employee__campus_id=effective_campus_id)

    # 5. Linked via 'room' (Timetabling)
    if 'room' in model_field_names:
        return queryset.filter(room__campus_id=effective_campus_id)

    # 6. Linked via 'class_session'
    if 'class_session' in model_field_names:
        return queryset.filter(class_session__campus_id=effective_campus_id)

    return queryset


class CampusPermissionMixin:
    """
    Reusable DRF ViewSet mixin that enforces institutional campus security:
    - Scopes queryset to user's authorized campus (or requested campus for multi-campus admins).
    - Prevents tampering with campus_id in query parameters, URL, or request payload.
    - Automatically stamps and validates campus on object creation and update for restricted users.
    """
    campus_filter_field = None

    def get_queryset(self):
        qs = super().get_queryset()
        return scope_queryset_by_campus(qs, self.request, campus_field=self.campus_filter_field)

    def perform_create(self, serializer):
        user = getattr(self.request, 'user', None)
        model = getattr(getattr(serializer, 'Meta', None), 'model', None)
        has_campus_field = bool(model and 'campus' in [f.name for f in model._meta.get_fields()])

        if user and getattr(user, 'is_authenticated', False) and not is_user_institution_admin(user):
            allowed_ids = get_user_allowed_campus_ids(user)
            if allowed_ids and has_campus_field:
                effective_cid = get_effective_campus_id(self.request) or allowed_ids[0]
                if effective_cid not in allowed_ids:
                    raise PermissionDenied("You do not have permission to create records for this campus.")
                serializer.save(campus_id=effective_cid)
                return

        if has_campus_field:
            # For institution admins, if no campus was explicitly set in validated_data, use active header/query campus
            validated = getattr(serializer, 'validated_data', {})
            if not validated.get('campus') and not validated.get('campus_id'):
                req_cid = get_request_campus_id(self.request)
                if req_cid:
                    serializer.save(campus_id=req_cid)
                    return

        super().perform_create(serializer)

    def perform_update(self, serializer):
        user = getattr(self.request, 'user', None)
        model = getattr(getattr(serializer, 'Meta', None), 'model', None)
        has_campus_field = bool(model and 'campus' in [f.name for f in model._meta.get_fields()])

        if user and getattr(user, 'is_authenticated', False) and not is_user_institution_admin(user):
            allowed_ids = get_user_allowed_campus_ids(user)
            if allowed_ids and has_campus_field:
                validated = getattr(serializer, 'validated_data', {})
                target_campus = validated.get('campus')
                target_cid = target_campus.id if hasattr(target_campus, 'id') else validated.get('campus_id')
                if target_cid is not None and int(target_cid) not in allowed_ids:
                    raise PermissionDenied("You cannot reassign records to an unauthorized campus.")

        super().perform_update(serializer)


class CampusFilterBackend(BaseFilterBackend):
    """
    DRF filter backend that automatically scopes queries to effective campus_id.
    Add to `filter_backends = [..., CampusFilterBackend]`.
    Optionally set `campus_filter_field = 'custom_path'` on the ViewSet.
    """
    def filter_queryset(self, request, queryset, view):
        field = getattr(view, 'campus_filter_field', None)
        return scope_queryset_by_campus(queryset, request, campus_field=field)
