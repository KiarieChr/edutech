"""
Timetable Analytics — Statistics, reports, and workload analysis.

This service provides:
1. Teacher workload summaries and balance analysis
2. Room utilization statistics
3. Class schedule completeness reports
4. Allocation coverage tracking
5. Conflict summary reports
6. Data for dashboards and printable reports

Architecture:
-----------
Analytics are read-only and operate on the current database state.
All methods return dict/JSON-serializable data suitable for:
- API responses
- PDF/Excel report generation
- Dashboard widgets

Usage:
------
    from timetable.services import TimetableAnalytics
    
    analytics = TimetableAnalytics()
    
    # Get teacher workload summary
    workload = analytics.get_teacher_workloads()
    
    # Get class schedule completeness
    coverage = analytics.get_class_coverage(class_session)
    
    # Room utilization
    utilization = analytics.get_room_utilization()
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import time, date, timedelta
from collections import defaultdict
from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import Coalesce


class TimetableAnalytics:
    """
    Analytics and reporting service for timetable data.
    
    Design Principles:
    1. Read-only operations
    2. Optimized queries (avoid N+1)
    3. JSON-serializable outputs
    4. Reusable across reports and APIs
    """
    
    # Day names for display
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    def __init__(self):
        """Initialize analytics service."""
        from timetable.models import (
            TimetableSlot, TimePeriod, WorkAllocation, Room, Subject
        )
        from academics.models import ClassSession
        
        self.TimetableSlot = TimetableSlot
        self.TimePeriod = TimePeriod
        self.WorkAllocation = WorkAllocation
        self.Room = Room
        self.Subject = Subject
        self.ClassSession = ClassSession
    
    # =========================================================================
    # TEACHER WORKLOAD ANALYTICS
    # =========================================================================
    
    def get_teacher_workloads(
        self,
        academic_year=None,
        term=None,
    ) -> Dict[str, Any]:
        """
        Get workload summary for all teachers.
        
        Returns:
            {
                'teachers': [...],
                'average_weekly_lessons': 22.5,
                'max_weekly_lessons': 30,
                'min_weekly_lessons': 15,
                'workload_distribution': {...}
            }
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Build filter for slots
        slot_filter = Q(is_active=True)
        if academic_year and term:
            slot_filter &= Q(class_session__term=term)
            slot_filter &= Q(class_session__term__academic_year=academic_year)
        
        # Aggregate by teacher
        teacher_stats = self.TimetableSlot.objects.filter(
            slot_filter
        ).values(
            'teacher_id',
            'teacher__first_name',
            'teacher__last_name',
            'teacher__username',
        ).annotate(
            total_lessons=Count('id'),
            unique_classes=Count('class_session', distinct=True),
            unique_subjects=Count('subject', distinct=True),
        ).order_by('-total_lessons')
        
        teachers = []
        lesson_counts = []
        
        for stat in teacher_stats:
            name = f"{stat['teacher__first_name']} {stat['teacher__last_name']}".strip()
            if not name:
                name = stat['teacher__username']
            
            daily_breakdown = self._get_teacher_daily_breakdown(stat['teacher_id'])
            
            teachers.append({
                'id': stat['teacher_id'],
                'name': name,
                'total_lessons': stat['total_lessons'],
                'unique_classes': stat['unique_classes'],
                'unique_subjects': stat['unique_subjects'],
                'daily_breakdown': daily_breakdown,
                'busiest_day': max(daily_breakdown.items(), key=lambda x: x[1])[0] if daily_breakdown else None,
                'workload_level': self._categorize_workload(stat['total_lessons']),
            })
            lesson_counts.append(stat['total_lessons'])
        
        # Calculate distribution
        distribution = self._calculate_distribution(lesson_counts)
        
        return {
            'teachers': teachers,
            'total_teachers': len(teachers),
            'average_weekly_lessons': round(sum(lesson_counts) / len(lesson_counts), 1) if lesson_counts else 0,
            'max_weekly_lessons': max(lesson_counts) if lesson_counts else 0,
            'min_weekly_lessons': min(lesson_counts) if lesson_counts else 0,
            'workload_distribution': distribution,
        }
    
    def get_teacher_detail(self, teacher_id: int) -> Dict[str, Any]:
        """
        Get detailed workload for a specific teacher.
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(pk=teacher_id)
        except User.DoesNotExist:
            return {'error': 'Teacher not found'}
        
        slots = self.TimetableSlot.objects.filter(
            teacher=user,
            is_active=True,
        ).select_related('class_session', 'subject', 'room')
        
        # Organize by day
        schedule = {day: [] for day in range(6)}
        for slot in slots:
            schedule[slot.day_of_week].append({
                'id': slot.id,
                'class': slot.class_session.name,
                'subject': slot.subject.name,
                'subject_code': slot.subject.code,
                'room': slot.room.name if slot.room else None,
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
            })
        
        # Sort each day by time
        for day in schedule:
            schedule[day].sort(key=lambda x: x['start_time'])
        
        # Calculate gaps and consecutive lessons
        analysis = self._analyze_teacher_schedule(schedule)
        
        # Get allocations
        allocations = self.WorkAllocation.objects.filter(
            teacher=user,
            is_active=True,
        ).select_related('subject', 'class_session')
        
        allocation_status = []
        for alloc in allocations:
            allocation_status.append({
                'id': alloc.id,
                'class': alloc.class_session.name,
                'subject': alloc.subject.name,
                'required': alloc.lessons_per_week,
                'scheduled': alloc.scheduled_lessons,
                'remaining': alloc.remaining_lessons,
                'complete': alloc.is_fully_allocated,
            })
        
        return {
            'teacher': {
                'id': user.id,
                'name': user.get_full_name or user.username,
                'email': user.email,
            },
            'summary': {
                'total_lessons': slots.count(),
                'classes_taught': len(set(s.class_session_id for s in slots)),
                'subjects_taught': len(set(s.subject_id for s in slots)),
            },
            'schedule': {
                self.DAY_NAMES[day]: lessons for day, lessons in schedule.items()
            },
            'analysis': analysis,
            'allocations': allocation_status,
        }
    
    # =========================================================================
    # CLASS COVERAGE ANALYTICS
    # =========================================================================
    
    def get_class_coverage(self, class_session) -> Dict[str, Any]:
        """
        Get schedule completeness for a class.
        
        Shows how well the timetable covers all required subjects.
        """
        allocations = self.WorkAllocation.objects.filter(
            class_session=class_session,
            is_active=True,
        ).select_related('teacher', 'subject')
        
        subjects = []
        total_required = 0
        total_scheduled = 0
        
        for alloc in allocations:
            total_required += alloc.lessons_per_week
            total_scheduled += alloc.scheduled_lessons
            
            subjects.append({
                'subject_id': alloc.subject_id,
                'subject_code': alloc.subject.code,
                'subject_name': alloc.subject.name,
                'teacher_id': alloc.teacher_id,
                'teacher_name': alloc.teacher.get_full_name or alloc.teacher.username,
                'required': alloc.lessons_per_week,
                'scheduled': alloc.scheduled_lessons,
                'remaining': alloc.remaining_lessons,
                'percentage': alloc.allocation_percentage,
                'status': 'complete' if alloc.is_fully_allocated else (
                    'partial' if alloc.scheduled_lessons > 0 else 'none'
                ),
            })
        
        subjects.sort(key=lambda x: x['percentage'])
        
        return {
            'class_session': {
                'id': class_session.id,
                'name': class_session.name,
            },
            'summary': {
                'total_subjects': len(subjects),
                'complete_subjects': sum(1 for s in subjects if s['status'] == 'complete'),
                'partial_subjects': sum(1 for s in subjects if s['status'] == 'partial'),
                'unscheduled_subjects': sum(1 for s in subjects if s['status'] == 'none'),
                'total_required_lessons': total_required,
                'total_scheduled_lessons': total_scheduled,
                'overall_percentage': round(total_scheduled / total_required * 100, 1) if total_required > 0 else 0,
            },
            'subjects': subjects,
        }
    
    def get_all_classes_coverage(self) -> Dict[str, Any]:
        """
        Get coverage summary for all classes.
        """
        classes = self.ClassSession.objects.filter(
            status__in=['scheduled', 'active']
        ).select_related('grade')
        
        results = []
        for cls in classes:
            coverage = self.get_class_coverage(cls)
            results.append({
                'class_id': cls.id,
                'class_name': cls.name,
                'grade': cls.grade.name if cls.grade else None,
                'coverage_percentage': coverage['summary']['overall_percentage'],
                'complete': coverage['summary']['complete_subjects'],
                'total': coverage['summary']['total_subjects'],
            })
        
        results.sort(key=lambda x: x['coverage_percentage'])
        
        return {
            'classes': results,
            'fully_scheduled': sum(1 for c in results if c['coverage_percentage'] >= 100),
            'partially_scheduled': sum(1 for c in results if 0 < c['coverage_percentage'] < 100),
            'not_scheduled': sum(1 for c in results if c['coverage_percentage'] == 0),
        }
    
    # =========================================================================
    # ROOM UTILIZATION ANALYTICS
    # =========================================================================
    
    def get_room_utilization(self) -> Dict[str, Any]:
        """
        Get utilization statistics for all rooms.
        """
        # Get all periods for calculating total available slots
        periods = self.TimePeriod.objects.filter(
            is_schedulable=True,
            is_active=True,
        )
        total_periods = periods.count()
        total_available_slots = total_periods * 6  # 6 days
        
        rooms = self.Room.objects.filter(is_active=True).annotate(
            scheduled_slots=Count(
                'timetableslot',
                filter=Q(timetableslot__is_active=True)
            )
        )
        
        results = []
        for room in rooms:
            utilization = round(
                room.scheduled_slots / total_available_slots * 100, 1
            ) if total_available_slots > 0 else 0
            
            results.append({
                'id': room.id,
                'name': room.name,
                'room_type': room.room_type,
                'room_type_display': room.get_room_type_display() if hasattr(room, 'get_room_type_display') else room.room_type,
                'capacity': room.capacity,
                'scheduled_slots': room.scheduled_slots,
                'available_slots': total_available_slots,
                'utilization_percentage': utilization,
                'utilization_level': self._categorize_utilization(utilization),
            })
        
        results.sort(key=lambda x: x['utilization_percentage'], reverse=True)
        
        avg_utilization = sum(r['utilization_percentage'] for r in results) / len(results) if results else 0
        
        return {
            'rooms': results,
            'total_rooms': len(results),
            'average_utilization': round(avg_utilization, 1),
            'underutilized': sum(1 for r in results if r['utilization_percentage'] < 30),
            'optimal': sum(1 for r in results if 30 <= r['utilization_percentage'] < 80),
            'overutilized': sum(1 for r in results if r['utilization_percentage'] >= 80),
        }
    
    def get_room_schedule(self, room_id: int) -> Dict[str, Any]:
        """
        Get detailed schedule for a room.
        """
        try:
            room = self.Room.objects.get(pk=room_id)
        except self.Room.DoesNotExist:
            return {'error': 'Room not found'}
        
        slots = self.TimetableSlot.objects.filter(
            room=room,
            is_active=True,
        ).select_related('class_session', 'subject', 'teacher')
        
        schedule = {day: [] for day in range(6)}
        for slot in slots:
            schedule[slot.day_of_week].append({
                'id': slot.id,
                'class': slot.class_session.name,
                'subject': slot.subject.name,
                'teacher': slot.teacher.get_full_name or slot.teacher.username,
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
            })
        
        for day in schedule:
            schedule[day].sort(key=lambda x: x['start_time'])
        
        return {
            'room': {
                'id': room.id,
                'name': room.name,
                'room_type': room.room_type,
                'capacity': room.capacity,
            },
            'schedule': {
                self.DAY_NAMES[day]: lessons for day, lessons in schedule.items()
            },
            'total_slots': slots.count(),
        }
    
    # =========================================================================
    # PERIOD ANALYTICS
    # =========================================================================
    
    def get_period_utilization(self) -> Dict[str, Any]:
        """
        Analyze which periods are most/least used.
        
        Useful for identifying scheduling patterns and constraints.
        """
        periods = self.TimePeriod.objects.filter(
            is_schedulable=True,
            is_active=True,
        ).order_by('order')
        
        results = []
        for period in periods:
            slots = self.TimetableSlot.objects.filter(
                start_time=period.start_time,
                end_time=period.end_time,
                is_active=True,
            )
            
            by_day = defaultdict(int)
            for slot in slots:
                by_day[slot.day_of_week] += 1
            
            results.append({
                'id': period.id,
                'name': period.name,
                'time_range': f"{period.start_time.strftime('%H:%M')}-{period.end_time.strftime('%H:%M')}",
                'total_slots': slots.count(),
                'by_day': {self.DAY_NAMES[d]: c for d, c in sorted(by_day.items())},
                'busiest_day': self.DAY_NAMES[max(by_day.items(), key=lambda x: x[1])[0]] if by_day else None,
            })
        
        return {
            'periods': results,
            'busiest_period': max(results, key=lambda x: x['total_slots'])['name'] if results else None,
            'least_busy_period': min(results, key=lambda x: x['total_slots'])['name'] if results else None,
        }
    
    # =========================================================================
    # CONFLICT SUMMARY
    # =========================================================================
    
    def get_conflict_summary(self) -> Dict[str, Any]:
        """
        Scan for any existing conflicts in the timetable.
        
        Note: This shouldn't find any if the system is working correctly,
        but useful for audit/validation.
        """
        conflicts = []
        
        # Check teacher double-booking
        teacher_conflicts = self.TimetableSlot.objects.filter(
            is_active=True
        ).values(
            'teacher_id', 'day_of_week', 'start_time'
        ).annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        for tc in teacher_conflicts:
            conflicts.append({
                'type': 'teacher_double_booking',
                'teacher_id': tc['teacher_id'],
                'day': self.DAY_NAMES[tc['day_of_week']],
                'time': tc['start_time'].strftime('%H:%M'),
                'count': tc['count'],
            })
        
        # Check room double-booking
        room_conflicts = self.TimetableSlot.objects.filter(
            is_active=True,
            room__isnull=False
        ).values(
            'room_id', 'day_of_week', 'start_time'
        ).annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        for rc in room_conflicts:
            conflicts.append({
                'type': 'room_double_booking',
                'room_id': rc['room_id'],
                'day': self.DAY_NAMES[rc['day_of_week']],
                'time': rc['start_time'].strftime('%H:%M'),
                'count': rc['count'],
            })
        
        # Check class double-booking
        class_conflicts = self.TimetableSlot.objects.filter(
            is_active=True
        ).values(
            'class_session_id', 'day_of_week', 'start_time'
        ).annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        for cc in class_conflicts:
            conflicts.append({
                'type': 'class_double_booking',
                'class_session_id': cc['class_session_id'],
                'day': self.DAY_NAMES[cc['day_of_week']],
                'time': cc['start_time'].strftime('%H:%M'),
                'count': cc['count'],
            })
        
        return {
            'total_conflicts': len(conflicts),
            'teacher_conflicts': sum(1 for c in conflicts if c['type'] == 'teacher_double_booking'),
            'room_conflicts': sum(1 for c in conflicts if c['type'] == 'room_double_booking'),
            'class_conflicts': sum(1 for c in conflicts if c['type'] == 'class_double_booking'),
            'conflicts': conflicts,
            'status': 'clean' if not conflicts else 'has_conflicts',
        }
    
    # =========================================================================
    # DASHBOARD SUMMARY
    # =========================================================================
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Get high-level summary for admin dashboard.
        """
        total_slots = self.TimetableSlot.objects.filter(is_active=True).count()
        total_classes = self.ClassSession.objects.filter(status__in=['scheduled', 'active']).count()
        total_rooms = self.Room.objects.filter(is_active=True).count()
        
        # Get teacher count with slots
        from django.contrib.auth import get_user_model
        User = get_user_model()
        teachers_with_slots = self.TimetableSlot.objects.filter(
            is_active=True
        ).values('teacher_id').distinct().count()
        
        # Allocation stats
        allocations = self.WorkAllocation.objects.filter(is_active=True)
        total_allocations = allocations.count()
        complete_allocations = sum(1 for a in allocations if a.is_fully_allocated)
        
        coverage = self.get_all_classes_coverage()
        conflict_summary = self.get_conflict_summary()
        
        return {
            'overview': {
                'total_scheduled_slots': total_slots,
                'active_classes': total_classes,
                'active_rooms': total_rooms,
                'active_teachers': teachers_with_slots,
            },
            'allocations': {
                'total': total_allocations,
                'complete': complete_allocations,
                'incomplete': total_allocations - complete_allocations,
                'completion_rate': round(complete_allocations / total_allocations * 100, 1) if total_allocations > 0 else 0,
            },
            'class_coverage': {
                'fully_scheduled': coverage['fully_scheduled'],
                'partially_scheduled': coverage['partially_scheduled'],
                'not_scheduled': coverage['not_scheduled'],
            },
            'system_health': {
                'conflicts': conflict_summary['total_conflicts'],
                'status': conflict_summary['status'],
            },
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_teacher_daily_breakdown(self, teacher_id: int) -> Dict[str, int]:
        """Get lesson count by day for a teacher."""
        slots = self.TimetableSlot.objects.filter(
            teacher_id=teacher_id,
            is_active=True,
        ).values('day_of_week').annotate(count=Count('id'))
        
        return {
            self.DAY_NAMES[s['day_of_week']]: s['count']
            for s in slots
        }
    
    def _categorize_workload(self, lessons: int) -> str:
        """Categorize teacher workload level."""
        if lessons < 15:
            return 'light'
        elif lessons < 25:
            return 'normal'
        elif lessons < 30:
            return 'heavy'
        else:
            return 'overloaded'
    
    def _categorize_utilization(self, percentage: float) -> str:
        """Categorize room utilization level."""
        if percentage < 20:
            return 'underutilized'
        elif percentage < 50:
            return 'low'
        elif percentage < 75:
            return 'optimal'
        elif percentage < 90:
            return 'high'
        else:
            return 'overutilized'
    
    def _calculate_distribution(self, values: List[int]) -> Dict[str, int]:
        """Calculate distribution buckets for workload."""
        if not values:
            return {}
        
        return {
            'light_0_14': sum(1 for v in values if v < 15),
            'normal_15_24': sum(1 for v in values if 15 <= v < 25),
            'heavy_25_29': sum(1 for v in values if 25 <= v < 30),
            'overloaded_30_plus': sum(1 for v in values if v >= 30),
        }
    
    def _analyze_teacher_schedule(self, schedule: Dict[int, List]) -> Dict[str, Any]:
        """Analyze teacher schedule for gaps and patterns."""
        total_gaps = 0
        max_consecutive = 0
        
        for day, lessons in schedule.items():
            if len(lessons) < 2:
                continue
            
            # Count gaps
            for i in range(1, len(lessons)):
                prev_end = lessons[i - 1]['end_time']
                curr_start = lessons[i]['start_time']
                
                from datetime import datetime as dt
                dummy = date.today()
                prev_end_dt = dt.strptime(prev_end, '%H:%M')
                curr_start_dt = dt.strptime(curr_start, '%H:%M')
                gap_minutes = (curr_start_dt - prev_end_dt).total_seconds() / 60
                
                if gap_minutes > 15:
                    total_gaps += 1
            
            # Count consecutive
            consecutive = 1
            for i in range(1, len(lessons)):
                prev_end = lessons[i - 1]['end_time']
                curr_start = lessons[i]['start_time']
                
                prev_end_dt = dt.strptime(prev_end, '%H:%M')
                curr_start_dt = dt.strptime(curr_start, '%H:%M')
                gap_minutes = (curr_start_dt - prev_end_dt).total_seconds() / 60
                
                if gap_minutes <= 15:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 1
        
        return {
            'total_gaps': total_gaps,
            'max_consecutive_lessons': max_consecutive,
            'schedule_efficiency': 'good' if total_gaps < 3 else (
                'fair' if total_gaps < 6 else 'needs_improvement'
            ),
        }
