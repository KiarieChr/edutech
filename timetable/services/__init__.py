"""
Timetable Services Package

Contains:
- ConflictEngine: Validates scheduling constraints and detects conflicts
- SchedulingService: Semi-automatic and automatic timetable generation
- TimetableAnalytics: Workload analysis and reporting
"""

from .conflict_engine import ConflictEngine
from .scheduling_service import SchedulingService
from .analytics import TimetableAnalytics

__all__ = ['ConflictEngine', 'SchedulingService', 'TimetableAnalytics']
