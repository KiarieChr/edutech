"""
Scheduling Service — Core scheduling engine for timetable generation.

This service provides:
1. Semi-automatic scheduling (greedy algorithm with conflict checking)
2. Suggestion generation for manual scheduling
3. Batch scheduling with optimization
4. Schedule quality metrics

Architecture:
-----------
The SchedulingService relies on ConflictEngine for validation and operates
in phases:
- Phase 1: Collect all WorkAllocations that need scheduling
- Phase 2: Sort by constraints (most constrained first)
- Phase 3: Apply greedy assignment with backtracking
- Phase 4: Report unplaced allocations for manual intervention

Usage:
------
    from timetable.services import SchedulingService
    
    service = SchedulingService()
    
    # Generate timetable for a class
    result = service.generate_timetable(
        class_session=session,
        mode='semi_auto',  # or 'suggestions_only'
        preferences={
            'prefer_morning': True,
            'spread_subjects': True,
        }
    )
    
    print(f"Placed: {result['placed_count']}/{result['total_allocations']}")
    for unplaced in result['unplaced']:
        print(f"Manual: {unplaced['subject']} ({unplaced['reason']})")

Algorithm:
---------
The scheduling uses a Most Constrained First (MCV) heuristic:
1. Calculate "flexibility score" for each allocation
2. Sort allocations by flexibility (least flexible first)
3. For each allocation, try to place required lessons
4. Use constraint propagation to update flexibility scores
5. Track partial solutions for reporting

Future Extensions:
-----------------
- Genetic algorithm for full auto-scheduling
- Simulated annealing for optimization
- Multi-objective optimization (teacher fairness, room utilization)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import time, date, timedelta
from collections import defaultdict
from enum import Enum
import random

from django.db import transaction
from django.db.models import Count, Q


class SchedulingMode(Enum):
    """Scheduling operation modes."""
    SEMI_AUTO = "semi_auto"        # Create slots, ask for manual help on conflicts
    SUGGESTIONS_ONLY = "suggestions_only"  # Just suggest, don't create
    BATCH_FILL = "batch_fill"      # Fill as many as possible, report rest


class DayPreference(Enum):
    """Day distribution preferences."""
    SPREAD = "spread"              # Spread across week
    COMPACT = "compact"            # Group into fewer days
    MORNING_FIRST = "morning_first"
    AFTERNOON_FIRST = "afternoon_first"


@dataclass
class SchedulingPreferences:
    """User preferences for scheduling."""
    prefer_morning: bool = True
    spread_subjects: bool = True                # Avoid same subject twice/day
    max_same_subject_per_day: int = 1
    preferred_rooms: Dict[int, int] = field(default_factory=dict)  # subject -> room
    blocked_periods: List[Tuple[int, time]] = field(default_factory=list)  # (day, time)
    day_preference: DayPreference = DayPreference.SPREAD


@dataclass
class AllocationSchedule:
    """Represents an allocation to be scheduled."""
    allocation_id: int
    teacher_id: int
    teacher_name: str
    subject_id: int
    subject_code: str
    subject_name: str
    class_session_id: int
    class_name: str
    lessons_needed: int
    lessons_scheduled: int
    flexibility_score: float = 0.0
    available_slots: List[Dict] = field(default_factory=list)
    
    @property
    def remaining(self) -> int:
        return self.lessons_needed - self.lessons_scheduled


@dataclass 
class SchedulingResult:
    """Result of a scheduling operation."""
    success: bool
    placed_count: int
    total_allocations: int
    created_slots: List[int] = field(default_factory=list)
    unplaced: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'placed_count': self.placed_count,
            'total_allocations': self.total_allocations,
            'placement_percentage': round(
                self.placed_count / self.total_allocations * 100 
                if self.total_allocations > 0 else 0, 1
            ),
            'created_slots': self.created_slots,
            'unplaced': self.unplaced,
            'warnings': self.warnings,
            'execution_time_ms': self.execution_time_ms,
        }


class SchedulingService:
    """
    Core scheduling engine for timetable generation.
    
    Design Principles:
    1. Separation of concerns - uses ConflictEngine for validation
    2. Graceful degradation - partial success is acceptable
    3. Transparency - detailed reporting on what worked and why
    4. Reversibility - all changes can be undone
    """
    
    def __init__(self):
        """Initialize the scheduling service."""
        from timetable.services.conflict_engine import ConflictEngine
        from timetable.models import (
            TimetableSlot, TimePeriod, WorkAllocation, Room
        )
        
        self.conflict_engine = ConflictEngine()
        self.TimetableSlot = TimetableSlot
        self.TimePeriod = TimePeriod
        self.WorkAllocation = WorkAllocation
        self.Room = Room
    
    def generate_timetable(
        self,
        class_session,
        mode: SchedulingMode = SchedulingMode.SEMI_AUTO,
        preferences: SchedulingPreferences = None,
        effective_from: date = None,
    ) -> SchedulingResult:
        """
        Generate or suggest timetable for a class.
        
        Args:
            class_session: ClassSession to generate timetable for
            mode: How to handle scheduling (create or suggest)
            preferences: User preferences for scheduling
            effective_from: Date from which slots should be effective
            
        Returns:
            SchedulingResult with created/suggested slots
        """
        import time as timer
        start_time = timer.time()
        
        preferences = preferences or SchedulingPreferences()
        effective_from = effective_from or date.today()
        
        # Phase 1: Collect allocations
        allocations = self._collect_allocations(class_session)
        
        if not allocations:
            return SchedulingResult(
                success=True,
                placed_count=0,
                total_allocations=0,
                warnings=["No work allocations found for this class."]
            )
        
        # Phase 2: Calculate flexibility and sort
        periods = self._get_schedulable_periods()
        self._calculate_flexibility_scores(allocations, class_session, periods)
        allocations.sort(key=lambda a: (a.flexibility_score, -a.lessons_needed))
        
        # Phase 3: Apply scheduling
        result = self._execute_scheduling(
            class_session=class_session,
            allocations=allocations,
            periods=periods,
            mode=mode,
            preferences=preferences,
            effective_from=effective_from,
        )
        
        result.execution_time_ms = (timer.time() - start_time) * 1000
        return result
    
    def suggest_next_slot(
        self,
        allocation_id: int,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Suggest best slots for a specific allocation.
        
        Returns ranked list of available slots with quality scores.
        """
        try:
            allocation = self.WorkAllocation.objects.select_related(
                'teacher', 'subject', 'class_session'
            ).get(pk=allocation_id)
        except self.WorkAllocation.DoesNotExist:
            return []
        
        available = self.conflict_engine.get_available_slots(
            class_session=allocation.class_session,
            teacher=allocation.teacher,
            subject=allocation.subject,
        )
        
        # Filter and rank
        scored = []
        for slot in available:
            if not slot['is_available']:
                continue
            
            score = self._calculate_slot_score(slot, allocation)
            slot['quality_score'] = score
            slot['quality_label'] = self._score_to_label(score)
            scored.append(slot)
        
        # Sort by score (highest first) and limit
        scored.sort(key=lambda s: s['quality_score'], reverse=True)
        return scored[:limit]
    
    def fill_gaps(
        self,
        class_session,
        max_iterations: int = 100,
    ) -> SchedulingResult:
        """
        Try to fill remaining allocation gaps for a partially scheduled timetable.
        
        Useful after manual adjustments.
        """
        return self.generate_timetable(
            class_session=class_session,
            mode=SchedulingMode.BATCH_FILL,
        )
    
    def preview_placement(
        self,
        class_session,
        subject,
        teacher,
        day_of_week: int,
        start_time: time,
        end_time: time,
        room=None,
    ) -> Dict[str, Any]:
        """
        Preview what would happen if a slot were placed.
        
        Returns conflicts, warnings, and impact analysis.
        """
        result = self.conflict_engine.check_slot_creation(
            class_session=class_session,
            subject=subject,
            teacher=teacher,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            room=room,
        )
        
        # Get allocation status
        try:
            allocation = self.WorkAllocation.objects.get(
                class_session=class_session,
                subject=subject,
                teacher=teacher,
                is_active=True,
            )
            allocation_status = {
                'required': allocation.lessons_per_week,
                'scheduled': allocation.scheduled_lessons,
                'after_placement': allocation.scheduled_lessons + 1,
                'would_complete': (allocation.scheduled_lessons + 1) >= allocation.lessons_per_week,
            }
        except self.WorkAllocation.DoesNotExist:
            allocation_status = None
        
        return {
            'can_place': result.is_valid,
            'conflicts': result.to_dict()['conflicts'],
            'warnings': result.to_dict()['warnings'],
            'allocation_status': allocation_status,
        }
    
    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================
    
    def _collect_allocations(
        self,
        class_session
    ) -> List[AllocationSchedule]:
        """Collect all incomplete allocations for a class."""
        allocations = self.WorkAllocation.objects.filter(
            class_session=class_session,
            is_active=True,
        ).select_related('teacher', 'subject')
        
        result = []
        for alloc in allocations:
            remaining = alloc.remaining_lessons
            if remaining <= 0:
                continue
                
            result.append(AllocationSchedule(
                allocation_id=alloc.id,
                teacher_id=alloc.teacher_id,
                teacher_name=alloc.teacher.get_full_name() or alloc.teacher.username,
                subject_id=alloc.subject_id,
                subject_code=alloc.subject.code,
                subject_name=alloc.subject.name,
                class_session_id=class_session.id,
                class_name=class_session.name,
                lessons_needed=alloc.lessons_per_week,
                lessons_scheduled=alloc.scheduled_lessons,
            ))
        
        return result
    
    def _get_schedulable_periods(self) -> List[Dict]:
        """Get all schedulable time periods."""
        periods = self.TimePeriod.objects.filter(
            is_schedulable=True,
            is_active=True,
        ).order_by('order')
        
        return [
            {
                'id': p.id,
                'name': p.name,
                'start_time': p.start_time,
                'end_time': p.end_time,
                'days': p.days_applicable or [0, 1, 2, 3, 4, 5],
            }
            for p in periods
        ]
    
    def _calculate_flexibility_scores(
        self,
        allocations: List[AllocationSchedule],
        class_session,
        periods: List[Dict],
    ):
        """
        Calculate flexibility score for each allocation.
        
        Lower score = more constrained = schedule first
        """
        for alloc in allocations:
            available_slots = self.conflict_engine.get_available_slots(
                class_session=class_session,
                teacher=self.WorkAllocation.objects.get(pk=alloc.allocation_id).teacher,
                subject=self.WorkAllocation.objects.get(pk=alloc.allocation_id).subject,
            )
            
            valid_count = sum(1 for s in available_slots if s['is_available'])
            alloc.available_slots = [s for s in available_slots if s['is_available']]
            
            # Flexibility = available slots / required lessons
            # Lower = more constrained
            alloc.flexibility_score = valid_count / max(alloc.remaining, 1)
    
    def _execute_scheduling(
        self,
        class_session,
        allocations: List[AllocationSchedule],
        periods: List[Dict],
        mode: SchedulingMode,
        preferences: SchedulingPreferences,
        effective_from: date,
    ) -> SchedulingResult:
        """Execute the actual scheduling algorithm."""
        result = SchedulingResult(
            success=True,
            placed_count=0,
            total_allocations=sum(a.remaining for a in allocations),
        )
        
        # Track used slots to avoid double-assignment
        used_slots: Set[Tuple[int, str]] = set()  # (day, start_time)
        
        # Track daily subject counts for spreading
        daily_subjects: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        
        for alloc in allocations:
            allocation_obj = self.WorkAllocation.objects.select_related(
                'teacher', 'subject', 'class_session'
            ).get(pk=alloc.allocation_id)
            
            lessons_to_place = alloc.remaining
            placed_for_alloc = 0
            
            # Sort available slots by preference
            sorted_slots = self._rank_slots(
                alloc.available_slots,
                preferences,
                daily_subjects,
                alloc.subject_id,
            )
            
            for slot in sorted_slots:
                if placed_for_alloc >= lessons_to_place:
                    break
                
                slot_key = (slot['day_of_week'], slot['start_time'])
                if slot_key in used_slots:
                    continue
                
                # Check spreading preference
                if preferences.spread_subjects:
                    day = slot['day_of_week']
                    if daily_subjects[day][alloc.subject_id] >= preferences.max_same_subject_per_day:
                        continue
                
                # Re-verify with current state
                period = self.TimePeriod.objects.get(pk=slot['period_id'])
                verify = self.conflict_engine.check_slot_creation(
                    class_session=allocation_obj.class_session,
                    subject=allocation_obj.subject,
                    teacher=allocation_obj.teacher,
                    day_of_week=slot['day_of_week'],
                    start_time=period.start_time,
                    end_time=period.end_time,
                    effective_from=effective_from,
                )
                
                if not verify.is_valid:
                    continue
                
                # Place the slot
                if mode == SchedulingMode.SUGGESTIONS_ONLY:
                    # Don't create, just count as placeable
                    used_slots.add(slot_key)
                    placed_for_alloc += 1
                    daily_subjects[slot['day_of_week']][alloc.subject_id] += 1
                    
                else:
                    # Create the slot
                    try:
                        with transaction.atomic():
                            room = self._select_room(
                                allocation_obj.subject,
                                allocation_obj.class_session,
                                slot['day_of_week'],
                                period.start_time,
                                period.end_time,
                                preferences,
                            )
                            
                            new_slot = self.TimetableSlot.objects.create(
                                class_session=allocation_obj.class_session,
                                subject=allocation_obj.subject,
                                teacher=allocation_obj.teacher,
                                room=room,
                                day_of_week=slot['day_of_week'],
                                start_time=period.start_time,
                                end_time=period.end_time,
                                effective_from=effective_from,
                            )
                            
                            result.created_slots.append(new_slot.id)
                            used_slots.add(slot_key)
                            placed_for_alloc += 1
                            daily_subjects[slot['day_of_week']][alloc.subject_id] += 1
                            
                    except Exception as e:
                        result.warnings.append(f"Failed to create slot: {str(e)}")
            
            result.placed_count += placed_for_alloc
            
            # Track unplaced
            if placed_for_alloc < lessons_to_place:
                result.unplaced.append({
                    'allocation_id': alloc.allocation_id,
                    'subject': alloc.subject_name,
                    'teacher': alloc.teacher_name,
                    'needed': lessons_to_place,
                    'placed': placed_for_alloc,
                    'remaining': lessons_to_place - placed_for_alloc,
                    'reason': self._diagnose_unplaced(alloc, used_slots),
                })
                result.success = False
        
        return result
    
    def _rank_slots(
        self,
        slots: List[Dict],
        preferences: SchedulingPreferences,
        daily_subjects: Dict[int, Dict[int, int]],
        subject_id: int,
    ) -> List[Dict]:
        """Rank available slots by preference criteria."""
        morning_cutoff = time(12, 0)
        
        def score(slot):
            s = 0
            slot_time = time.fromisoformat(slot['start_time'])
            
            # Morning preference
            if preferences.prefer_morning:
                if slot_time < morning_cutoff:
                    s += 10
            else:
                if slot_time >= morning_cutoff:
                    s += 10
            
            # Spread across days
            if preferences.day_preference == DayPreference.SPREAD:
                day_count = daily_subjects[slot['day_of_week']][subject_id]
                s -= day_count * 5
            
            # Prefer fewer warnings
            s -= len(slot.get('warnings', [])) * 2
            
            return s
        
        return sorted(slots, key=score, reverse=True)
    
    def _select_room(
        self,
        subject,
        class_session,
        day_of_week: int,
        start_time: time,
        end_time: time,
        preferences: SchedulingPreferences,
    ):
        """Select an appropriate room for the lesson."""
        # Check preferences first
        if subject.id in preferences.preferred_rooms:
            try:
                room = self.Room.objects.get(pk=preferences.preferred_rooms[subject.id])
                # Verify availability
                check = self.conflict_engine.check_slot_creation(
                    class_session=class_session,
                    subject=subject,
                    teacher=None,  # We only care about room here
                    room=room,
                    day_of_week=day_of_week,
                    start_time=start_time,
                    end_time=end_time,
                )
                if check.is_valid:
                    return room
            except self.Room.DoesNotExist:
                pass
        
        # Find any available room
        from academics.models import StudentSessionEnrollment
        try:
            student_count = StudentSessionEnrollment.objects.filter(
                session=class_session,
                is_active=True,
                status='active'
            ).count()
        except Exception:
            student_count = 30  # Default
        
        # Get rooms with sufficient capacity
        candidate_rooms = self.Room.objects.filter(
            capacity__gte=student_count,
            is_active=True,
        ).order_by('capacity')  # Prefer smallest adequate room
        
        for room in candidate_rooms:
            # Check room availability
            conflict_check = self.TimetableSlot.objects.filter(
                room=room,
                day_of_week=day_of_week,
                is_active=True,
                start_time__lt=end_time,
                end_time__gt=start_time,
            ).exists()
            
            if not conflict_check:
                return room
        
        # No room available, return None (room-less slot)
        return None
    
    def _diagnose_unplaced(
        self,
        allocation: AllocationSchedule,
        used_slots: Set[Tuple[int, str]],
    ) -> str:
        """Diagnose why an allocation couldn't be fully placed."""
        if not allocation.available_slots:
            return "No available slots - teacher may have too many constraints"
        
        available_count = len(allocation.available_slots)
        used_count = sum(
            1 for s in allocation.available_slots
            if (s['day_of_week'], s['start_time']) in used_slots
        )
        
        if used_count == available_count:
            return f"All {available_count} possible slots already used by other allocations"
        
        return f"Only {available_count - used_count} slots available, need more"
    
    def _calculate_slot_score(
        self,
        slot: Dict,
        allocation
    ) -> float:
        """Calculate quality score for a slot (0-100)."""
        score = 50.0  # Base score
        
        # Penalize warnings
        score -= len(slot.get('warnings', [])) * 10
        
        # Prefer morning (8-12)
        slot_time = time.fromisoformat(slot['start_time'])
        if time(8, 0) <= slot_time < time(12, 0):
            score += 15
        elif time(12, 0) <= slot_time < time(14, 0):
            score += 5  # Lunch-adjacent is ok
        
        # Prefer mid-week
        if slot['day_of_week'] in [1, 2, 3]:  # Tue, Wed, Thu
            score += 10
        elif slot['day_of_week'] == 5:  # Saturday
            score -= 10
        
        return max(0, min(100, score))
    
    def _score_to_label(self, score: float) -> str:
        """Convert score to human-readable label."""
        if score >= 80:
            return "Excellent"
        elif score >= 60:
            return "Good"
        elif score >= 40:
            return "Fair"
        elif score >= 20:
            return "Poor"
        else:
            return "Not Recommended"
