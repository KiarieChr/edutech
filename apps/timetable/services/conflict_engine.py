"""
Conflict Engine — Core constraint validation for the timetabling system.

This service is responsible for:
1. Detecting scheduling conflicts BEFORE they occur (pre-validation)
2. Validating existing timetable entries
3. Providing detailed conflict messages for the UI
4. Supporting both hard constraints (must satisfy) and soft constraints (should satisfy)

Architecture:
-----------
The ConflictEngine is stateless and operates on provided data.
It returns ConflictResult objects containing:
- is_valid: Boolean indicating if the operation can proceed
- conflicts: List of Conflict objects with details
- warnings: List of Warning objects for soft constraint violations

Usage:
------
    from timetable.services import ConflictEngine
    
    engine = ConflictEngine()
    
    # Check if a slot can be created
    result = engine.check_slot_creation(
        class_session=session,
        subject=subject,
        teacher=teacher,
        room=room,
        day_of_week=1,
        start_time=datetime.time(8, 0),
        end_time=datetime.time(8, 40)
    )
    
    if not result.is_valid:
        for conflict in result.conflicts:
            print(f"CONFLICT: {conflict.type} - {conflict.message}")

Future Extensions:
-----------------
This engine can be extended for:
- Exam timetable validation
- Resource booking conflicts
- Church/event scheduling
- Tertiary (multi-room, multi-instructor) scenarios
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import time, date, datetime, timedelta
from enum import Enum
from django.db.models import Q
from django.conf import settings


class ConflictType(Enum):
    """Types of conflicts that can occur."""
    TEACHER_DOUBLE_BOOKING = "teacher_double_booking"
    ROOM_DOUBLE_BOOKING = "room_double_booking"
    CLASS_DOUBLE_BOOKING = "class_double_booking"
    TEACHER_UNAVAILABLE = "teacher_unavailable"
    ROOM_TYPE_MISMATCH = "room_type_mismatch"
    ROOM_CAPACITY_EXCEEDED = "room_capacity_exceeded"
    WORKLOAD_EXCEEDED = "workload_exceeded"
    CONSECUTIVE_LIMIT = "consecutive_limit"
    ALLOCATION_MISMATCH = "allocation_mismatch"
    TIME_OVERLAP = "time_overlap"
    INVALID_TIME = "invalid_time"
    LOCK_VIOLATION = "lock_violation"


class WarningSeverity(Enum):
    """Severity levels for warnings (soft constraints)."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Conflict:
    """Represents a hard constraint violation."""
    type: ConflictType
    message: str
    entity_type: str  # 'teacher', 'room', 'class', etc.
    entity_id: Optional[int] = None
    entity_name: Optional[str] = None
    conflicting_slot_id: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type.value,
            'message': self.message,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'entity_name': self.entity_name,
            'conflicting_slot_id': self.conflicting_slot_id,
            'details': self.details,
        }


@dataclass
class Warning:
    """Represents a soft constraint violation (recommendation)."""
    severity: WarningSeverity
    message: str
    suggestion: str
    entity_type: str
    entity_id: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'severity': self.severity.value,
            'message': self.message,
            'suggestion': self.suggestion,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'details': self.details,
        }


@dataclass
class ConflictResult:
    """Result of conflict checking."""
    is_valid: bool
    conflicts: List[Conflict] = field(default_factory=list)
    warnings: List[Warning] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'is_valid': self.is_valid,
            'conflicts': [c.to_dict() for c in self.conflicts],
            'warnings': [w.to_dict() for w in self.warnings],
            'conflict_count': len(self.conflicts),
            'warning_count': len(self.warnings),
        }

    def add_conflict(self, conflict: Conflict):
        self.conflicts.append(conflict)
        self.is_valid = False

    def add_warning(self, warning: Warning):
        self.warnings.append(warning)


class ConflictEngine:
    """
    Core conflict detection and validation engine.
    
    Design Principles:
    1. Stateless - all data passed as arguments
    2. Testable - no side effects
    3. Extensible - easy to add new constraint types
    4. Performant - optimized queries with prefetching
    """

    # Configuration constants
    MAX_DAILY_LESSONS_PER_TEACHER = 8
    MAX_CONSECUTIVE_LESSONS = 3
    MAX_WEEKLY_LESSONS_PER_TEACHER = 30

    def __init__(self):
        """Initialize the conflict engine."""
        # Lazy import to avoid circular dependencies
        from timetable.models import (
            TimetableSlot, Room, Subject, TeacherAvailability,
            WorkAllocation, TimetableLock
        )
        self.TimetableSlot = TimetableSlot
        self.Room = Room
        self.Subject = Subject
        self.TeacherAvailability = TeacherAvailability
        self.WorkAllocation = WorkAllocation
        self.TimetableLock = TimetableLock

    def check_slot_creation(
        self,
        class_session,
        subject,
        teacher,
        day_of_week: int,
        start_time: time,
        end_time: time,
        room=None,
        effective_from: date = None,
        exclude_slot_id: int = None,
    ) -> ConflictResult:
        """
        Comprehensive check for creating or updating a timetable slot.
        
        Args:
            class_session: ClassSession instance
            subject: Subject instance
            teacher: User instance
            day_of_week: 0-5 (Mon-Sat)
            start_time: Start time of the slot
            end_time: End time of the slot
            room: Room instance (optional)
            effective_from: Date from which slot is effective
            exclude_slot_id: Slot ID to exclude (for updates)
        
        Returns:
            ConflictResult with validation status and any conflicts/warnings
        """
        result = ConflictResult(is_valid=True)
        effective_from = effective_from or date.today()

        # 1. Basic time validation
        self._check_time_validity(start_time, end_time, result)
        if not result.is_valid:
            return result

        # 2. Check timetable lock
        self._check_timetable_lock(class_session, result)
        if not result.is_valid:
            return result

        # 3. Check teacher conflicts
        self._check_teacher_conflicts(
            teacher, day_of_week, start_time, end_time,
            effective_from, exclude_slot_id, result
        )

        # 4. Check class conflicts
        self._check_class_conflicts(
            class_session, day_of_week, start_time, end_time,
            effective_from, exclude_slot_id, result
        )

        # 5. Check room conflicts (if room specified)
        if room:
            self._check_room_conflicts(
                room, day_of_week, start_time, end_time,
                effective_from, exclude_slot_id, result
            )
            self._check_room_compatibility(room, subject, class_session, result)

        # 6. Check teacher availability
        self._check_teacher_availability(
            teacher, day_of_week, start_time, end_time, result
        )

        # 7. Soft constraints - warnings only
        self._check_teacher_workload(teacher, day_of_week, result)
        self._check_consecutive_lessons(
            teacher, day_of_week, start_time, end_time, exclude_slot_id, result
        )

        return result

    def check_bulk_slots(
        self,
        slots_data: List[Dict[str, Any]]
    ) -> Dict[int, ConflictResult]:
        """
        Check multiple slots at once for bulk import/generation.
        
        Returns dict mapping slot index to ConflictResult.
        """
        results = {}
        for idx, slot_data in enumerate(slots_data):
            results[idx] = self.check_slot_creation(**slot_data)
        return results

    def get_available_slots(
        self,
        class_session,
        teacher,
        subject,
        room=None,
        effective_from: date = None,
    ) -> List[Dict[str, Any]]:
        """
        Find all available time slots where a lesson could be scheduled.
        
        Used by the auto-scheduler and UI to show valid options.
        
        Returns list of dicts:
        [
            {'day_of_week': 0, 'start_time': '08:00', 'end_time': '08:40', 'conflicts': []},
            ...
        ]
        """
        from timetable.models import TimePeriod
        
        effective_from = effective_from or date.today()
        available = []

        # Get all schedulable periods
        periods = TimePeriod.objects.filter(
            is_schedulable=True,
            is_active=True
        ).order_by('order')

        # Check each day and period combination
        for day in range(6):  # Monday to Saturday
            for period in periods:
                if not period.applies_to_day(day):
                    continue

                result = self.check_slot_creation(
                    class_session=class_session,
                    subject=subject,
                    teacher=teacher,
                    day_of_week=day,
                    start_time=period.start_time,
                    end_time=period.end_time,
                    room=room,
                    effective_from=effective_from,
                )

                slot_info = {
                    'day_of_week': day,
                    'day_name': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][day],
                    'period_id': period.id,
                    'period_name': period.name,
                    'start_time': period.start_time.strftime('%H:%M'),
                    'end_time': period.end_time.strftime('%H:%M'),
                    'is_available': result.is_valid,
                    'conflicts': [c.to_dict() for c in result.conflicts],
                    'warnings': [w.to_dict() for w in result.warnings],
                }
                available.append(slot_info)

        return available

    def validate_work_allocation_coverage(
        self,
        class_session,
    ) -> Dict[str, Any]:
        """
        Check if all work allocations for a class have been satisfied.
        
        Returns summary of allocation status with under/over allocation details.
        """
        allocations = self.WorkAllocation.objects.filter(
            class_session=class_session,
            is_active=True
        ).select_related('teacher', 'subject')

        results = {
            'class_session_id': class_session.id,
            'class_session_name': class_session.name,
            'total_allocations': allocations.count(),
            'fully_allocated': 0,
            'under_allocated': [],
            'over_allocated': [],
            'summary': [],
        }

        for alloc in allocations:
            status = {
                'allocation_id': alloc.id,
                'teacher_id': alloc.teacher_id,
                'teacher_name': alloc.teacher.get_full_name or alloc.teacher.username,
                'subject_id': alloc.subject_id,
                'subject_code': alloc.subject.code,
                'subject_name': alloc.subject.name,
                'required': alloc.lessons_per_week,
                'scheduled': alloc.scheduled_lessons,
                'remaining': alloc.remaining_lessons,
                'percentage': alloc.allocation_percentage,
                'status': 'complete' if alloc.is_fully_allocated else 'incomplete',
            }

            results['summary'].append(status)

            if alloc.is_fully_allocated:
                results['fully_allocated'] += 1
                if alloc.scheduled_lessons > alloc.lessons_per_week:
                    results['over_allocated'].append(status)
            else:
                results['under_allocated'].append(status)

        results['allocation_percentage'] = round(
            (results['fully_allocated'] / results['total_allocations'] * 100)
            if results['total_allocations'] > 0 else 0,
            1
        )

        return results

    # =========================================================================
    # PRIVATE VALIDATION METHODS
    # =========================================================================

    def _check_time_validity(
        self,
        start_time: time,
        end_time: time,
        result: ConflictResult
    ):
        """Validate that times are logically correct."""
        if start_time >= end_time:
            result.add_conflict(Conflict(
                type=ConflictType.INVALID_TIME,
                message="End time must be after start time.",
                entity_type='time',
                details={'start_time': str(start_time), 'end_time': str(end_time)}
            ))

        # Check reasonable school hours (configurable)
        earliest = time(6, 0)
        latest = time(20, 0)
        if start_time < earliest or end_time > latest:
            result.add_warning(Warning(
                severity=WarningSeverity.MEDIUM,
                message=f"Lesson time ({start_time}-{end_time}) is outside normal school hours.",
                suggestion="Consider scheduling between 6:00 and 20:00.",
                entity_type='time',
            ))

    def _check_timetable_lock(
        self,
        class_session,
        result: ConflictResult
    ):
        """Check if timetable is locked for editing."""
        try:
            lock = class_session.timetable_lock
            if not lock.is_editable:
                result.add_conflict(Conflict(
                    type=ConflictType.LOCK_VIOLATION,
                    message=f"Timetable is {lock.get_lock_level_display()}. Cannot modify.",
                    entity_type='timetable',
                    entity_id=class_session.id,
                    entity_name=class_session.name,
                    details={'lock_level': lock.lock_level}
                ))
        except self.TimetableLock.DoesNotExist:
            pass  # No lock exists, can edit

    def _check_teacher_conflicts(
        self,
        teacher,
        day_of_week: int,
        start_time: time,
        end_time: time,
        effective_from: date,
        exclude_slot_id: int,
        result: ConflictResult
    ):
        """Check for teacher double-booking."""
        query = Q(
            teacher=teacher,
            day_of_week=day_of_week,
            is_active=True,
        ) & (
            Q(effective_until__isnull=True) |
            Q(effective_until__gte=effective_from)
        ) & Q(effective_from__lte=effective_from)

        if exclude_slot_id:
            query &= ~Q(pk=exclude_slot_id)

        conflicting = self.TimetableSlot.objects.filter(query).filter(
            # Time overlap: start1 < end2 AND start2 < end1
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).select_related('class_session', 'subject').first()

        if conflicting:
            result.add_conflict(Conflict(
                type=ConflictType.TEACHER_DOUBLE_BOOKING,
                message=(
                    f"Teacher is already scheduled for "
                    f"{conflicting.class_session.name} - {conflicting.subject.name} "
                    f"at {conflicting.start_time:%H:%M}-{conflicting.end_time:%H:%M}."
                ),
                entity_type='teacher',
                entity_id=teacher.id,
                entity_name=teacher.get_full_name or teacher.username,
                conflicting_slot_id=conflicting.id,
                details={
                    'conflicting_class': conflicting.class_session.name,
                    'conflicting_subject': conflicting.subject.name,
                    'conflicting_time': f"{conflicting.start_time}-{conflicting.end_time}",
                }
            ))

    def _check_class_conflicts(
        self,
        class_session,
        day_of_week: int,
        start_time: time,
        end_time: time,
        effective_from: date,
        exclude_slot_id: int,
        result: ConflictResult
    ):
        """Check for class double-booking (class already has a lesson)."""
        query = Q(
            class_session=class_session,
            day_of_week=day_of_week,
            is_active=True,
        ) & (
            Q(effective_until__isnull=True) |
            Q(effective_until__gte=effective_from)
        ) & Q(effective_from__lte=effective_from)

        if exclude_slot_id:
            query &= ~Q(pk=exclude_slot_id)

        conflicting = self.TimetableSlot.objects.filter(query).filter(
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).select_related('subject', 'teacher').first()

        if conflicting:
            result.add_conflict(Conflict(
                type=ConflictType.CLASS_DOUBLE_BOOKING,
                message=(
                    f"Class already has {conflicting.subject.name} with "
                    f"{conflicting.teacher.get_full_name or conflicting.teacher.username} "
                    f"at {conflicting.start_time:%H:%M}-{conflicting.end_time:%H:%M}."
                ),
                entity_type='class',
                entity_id=class_session.id,
                entity_name=class_session.name,
                conflicting_slot_id=conflicting.id,
                details={
                    'conflicting_subject': conflicting.subject.name,
                    'conflicting_teacher': conflicting.teacher.get_full_name,
                    'conflicting_time': f"{conflicting.start_time}-{conflicting.end_time}",
                }
            ))

    def _check_room_conflicts(
        self,
        room,
        day_of_week: int,
        start_time: time,
        end_time: time,
        effective_from: date,
        exclude_slot_id: int,
        result: ConflictResult
    ):
        """Check for room double-booking."""
        query = Q(
            room=room,
            day_of_week=day_of_week,
            is_active=True,
        ) & (
            Q(effective_until__isnull=True) |
            Q(effective_until__gte=effective_from)
        ) & Q(effective_from__lte=effective_from)

        if exclude_slot_id:
            query &= ~Q(pk=exclude_slot_id)

        conflicting = self.TimetableSlot.objects.filter(query).filter(
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).select_related('class_session', 'subject').first()

        if conflicting:
            result.add_conflict(Conflict(
                type=ConflictType.ROOM_DOUBLE_BOOKING,
                message=(
                    f"Room '{room.name}' is already booked for "
                    f"{conflicting.class_session.name} - {conflicting.subject.name} "
                    f"at {conflicting.start_time:%H:%M}-{conflicting.end_time:%H:%M}."
                ),
                entity_type='room',
                entity_id=room.id,
                entity_name=room.name,
                conflicting_slot_id=conflicting.id,
                details={
                    'conflicting_class': conflicting.class_session.name,
                    'conflicting_subject': conflicting.subject.name,
                }
            ))

    def _check_room_compatibility(
        self,
        room,
        subject,
        class_session,
        result: ConflictResult
    ):
        """Check if room type matches subject requirements."""
        # Check if subject requires specific room type (via WorkAllocation)
        try:
            allocation = self.WorkAllocation.objects.get(
                subject=subject,
                class_session=class_session,
                is_active=True
            )
            if allocation.required_room_type and room.room_type != allocation.required_room_type:
                result.add_conflict(Conflict(
                    type=ConflictType.ROOM_TYPE_MISMATCH,
                    message=(
                        f"Subject '{subject.name}' requires a {allocation.get_required_room_type_display()} "
                        f"but '{room.name}' is a {room.get_room_type_display()}."
                    ),
                    entity_type='room',
                    entity_id=room.id,
                    entity_name=room.name,
                    details={
                        'required_type': allocation.required_room_type,
                        'room_type': room.room_type,
                    }
                ))
        except self.WorkAllocation.DoesNotExist:
            pass  # No specific requirement

        # Check capacity (soft constraint)
        try:
            from academics.models import StudentSessionEnrollment
            student_count = StudentSessionEnrollment.objects.filter(
                session=class_session,
                is_active=True,
                status='active'
            ).count()
            if student_count > room.capacity:
                result.add_warning(Warning(
                    severity=WarningSeverity.HIGH,
                    message=(
                        f"Room '{room.name}' has capacity {room.capacity} "
                        f"but class has {student_count} students."
                    ),
                    suggestion="Consider a larger room.",
                    entity_type='room',
                    entity_id=room.id,
                    details={
                        'room_capacity': room.capacity,
                        'student_count': student_count,
                    }
                ))
        except Exception:
            pass

    def _check_teacher_availability(
        self,
        teacher,
        day_of_week: int,
        start_time: time,
        end_time: time,
        result: ConflictResult
    ):
        """Check if teacher is available at the proposed time."""
        availabilities = self.TeacherAvailability.objects.filter(
            teacher=teacher,
            is_active=True,
            availability_type='unavailable',
        )

        for avail in availabilities:
            if avail.conflicts_with(day_of_week, start_time, end_time):
                result.add_conflict(Conflict(
                    type=ConflictType.TEACHER_UNAVAILABLE,
                    message=(
                        f"Teacher is marked unavailable: {avail.reason or 'No reason specified'}."
                    ),
                    entity_type='teacher',
                    entity_id=teacher.id,
                    entity_name=teacher.get_full_name or teacher.username,
                    details={
                        'availability_type': avail.availability_type,
                        'reason': avail.reason,
                    }
                ))
                break

    def _check_teacher_workload(
        self,
        teacher,
        day_of_week: int,
        result: ConflictResult
    ):
        """Check teacher's daily lesson count (soft constraint)."""
        daily_count = self.TimetableSlot.objects.filter(
            teacher=teacher,
            day_of_week=day_of_week,
            is_active=True,
        ).count()

        if daily_count >= self.MAX_DAILY_LESSONS_PER_TEACHER:
            result.add_warning(Warning(
                severity=WarningSeverity.HIGH,
                message=(
                    f"Teacher already has {daily_count} lessons on this day "
                    f"(max recommended: {self.MAX_DAILY_LESSONS_PER_TEACHER})."
                ),
                suggestion="Consider scheduling on another day.",
                entity_type='teacher',
                entity_id=teacher.id,
                details={
                    'current_daily_count': daily_count,
                    'max_recommended': self.MAX_DAILY_LESSONS_PER_TEACHER,
                }
            ))
        elif daily_count >= self.MAX_DAILY_LESSONS_PER_TEACHER - 2:
            result.add_warning(Warning(
                severity=WarningSeverity.MEDIUM,
                message=f"Teacher has {daily_count} lessons on this day.",
                suggestion="Consider distributing workload across days.",
                entity_type='teacher',
                entity_id=teacher.id,
            ))

    def _check_consecutive_lessons(
        self,
        teacher,
        day_of_week: int,
        start_time: time,
        end_time: time,
        exclude_slot_id: int,
        result: ConflictResult
    ):
        """
        Check if this would create too many consecutive lessons.
        
        A 'consecutive' lesson is one that starts within 5 minutes of the
        previous lesson ending (allowing for transition time).
        """
        # Get all slots for this teacher on this day
        query = Q(
            teacher=teacher,
            day_of_week=day_of_week,
            is_active=True,
        )
        if exclude_slot_id:
            query &= ~Q(pk=exclude_slot_id)

        slots = list(self.TimetableSlot.objects.filter(query).order_by('start_time'))

        # Add the proposed slot
        from types import SimpleNamespace
        proposed = SimpleNamespace(start_time=start_time, end_time=end_time)
        slots.append(proposed)
        slots.sort(key=lambda s: s.start_time)

        # Count maximum consecutive sequence
        max_consecutive = 1
        current_consecutive = 1

        for i in range(1, len(slots)):
            prev_end = slots[i - 1].end_time
            curr_start = slots[i].start_time

            # Calculate gap in minutes
            from datetime import datetime as dt
            dummy = date(2000, 1, 1)
            prev_end_dt = dt.combine(dummy, prev_end)
            curr_start_dt = dt.combine(dummy, curr_start)
            gap_minutes = (curr_start_dt - prev_end_dt).total_seconds() / 60

            if gap_minutes <= 15:  # 15 minutes or less = consecutive
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1

        if max_consecutive > self.MAX_CONSECUTIVE_LESSONS:
            result.add_warning(Warning(
                severity=WarningSeverity.HIGH,
                message=(
                    f"This would create {max_consecutive} consecutive lessons "
                    f"(max recommended: {self.MAX_CONSECUTIVE_LESSONS})."
                ),
                suggestion="Consider adding a break between lessons.",
                entity_type='teacher',
                entity_id=teacher.id,
                details={
                    'consecutive_count': max_consecutive,
                    'max_recommended': self.MAX_CONSECUTIVE_LESSONS,
                }
            ))

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_teacher_daily_schedule(
        self,
        teacher,
        day_of_week: int,
    ) -> List[Dict[str, Any]]:
        """Get teacher's schedule for a specific day."""
        slots = self.TimetableSlot.objects.filter(
            teacher=teacher,
            day_of_week=day_of_week,
            is_active=True,
        ).select_related(
            'class_session', 'subject', 'room'
        ).order_by('start_time')

        return [
            {
                'id': slot.id,
                'class': slot.class_session.name,
                'subject': slot.subject.name,
                'room': slot.room.name if slot.room else None,
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
            }
            for slot in slots
        ]

    def get_room_daily_schedule(
        self,
        room,
        day_of_week: int,
    ) -> List[Dict[str, Any]]:
        """Get room's schedule for a specific day."""
        slots = self.TimetableSlot.objects.filter(
            room=room,
            day_of_week=day_of_week,
            is_active=True,
        ).select_related(
            'class_session', 'subject', 'teacher'
        ).order_by('start_time')

        return [
            {
                'id': slot.id,
                'class': slot.class_session.name,
                'subject': slot.subject.name,
                'teacher': slot.teacher.get_full_name or slot.teacher.username,
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
            }
            for slot in slots
        ]

    def get_class_daily_schedule(
        self,
        class_session,
        day_of_week: int,
    ) -> List[Dict[str, Any]]:
        """Get class's schedule for a specific day."""
        slots = self.TimetableSlot.objects.filter(
            class_session=class_session,
            day_of_week=day_of_week,
            is_active=True,
        ).select_related(
            'subject', 'teacher', 'room'
        ).order_by('start_time')

        return [
            {
                'id': slot.id,
                'subject': slot.subject.name,
                'subject_color': slot.subject.color_hex,
                'teacher': slot.teacher.get_full_name or slot.teacher.username,
                'room': slot.room.name if slot.room else None,
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
            }
            for slot in slots
        ]
