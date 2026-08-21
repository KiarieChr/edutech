from django.db import models
from django.conf import settings


class DailyAttendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
        ('half_day', 'Half Day'),
    ]

    student = models.ForeignKey(
        'student_management.Student',
        on_delete=models.CASCADE,
        related_name='daily_attendance',
    )
    class_session = models.ForeignKey(
        'academics.ClassSession',
        on_delete=models.PROTECT,
        related_name='daily_attendance',
    )
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='absent')
    arrival_time = models.TimeField(null=True, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_marked',
    )
    marked_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'daily_attendance'
        unique_together = ['student', 'date']
        ordering = ['date', 'student__student__last_name']
        verbose_name = 'Daily Attendance'
        verbose_name_plural = 'Daily Attendance Records'

    def __str__(self):
        return f"{self.student} - {self.date} - {self.get_status_display()}"
