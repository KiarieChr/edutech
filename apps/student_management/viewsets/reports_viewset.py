from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q
from student_management.models import Student
from student_settings.models import Enrollment

class StudentReportsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def nominal_roll(self, request):
        """
        Retrieves the nominal roll (active students).
        Supports filtering by academic_year, term, grade, stream, gender, status.
        """
        queryset = Enrollment.objects.filter(is_active=True, is_deleted=False).select_related(
            'student', 'grade', 'stream', 'term', 'academic_year'
        )

        academic_year = request.query_params.get('academic_year')
        term = request.query_params.get('term')
        grade = request.query_params.get('grade')
        stream = request.query_params.get('stream')
        gender = request.query_params.get('gender')
        status = request.query_params.get('status')

        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)
        if term:
            queryset = queryset.filter(term_id=term)
        if grade:
            queryset = queryset.filter(grade_id=grade)
        if stream:
            queryset = queryset.filter(stream_id=stream)
        if gender:
            queryset = queryset.filter(student__student__gender=gender)
        if status:
            queryset = queryset.filter(status=status)
            
        queryset = queryset.order_by('grade__level_order', 'student__student__first_name')

        data = []
        for enr in queryset:
            student = enr.student
            data.append({
                'id': student.id,
                'admission_number': student.admission_number,
                'first_name': student.student.first_name,
                'last_name': student.student.last_name,
                'full_name': student.student.get_full_name(),
                'gender': student.student.gender,
                'grade': enr.grade.name if enr.grade else 'N/A',
                'stream': enr.stream.name if enr.stream else 'N/A',
                'admission_date': student.admission_date,
                'status': enr.get_status_display(),
                'age': None,
            })

        return Response(data)

    @action(detail=False, methods=['get'])
    def demographics(self, request):
        """
        Retrieves demographic data for reporting.
        """
        queryset = Student.objects.filter(status='active')
        
        # Gender breakdown
        gender_stats = queryset.values('student__gender').annotate(count=Count('id'))
        
        # Age breakdown
        # Since age is a property, we might need to rely on DOB or just calculate.
        # For simplicity, we can do nationality and religion which are DB fields
        nationality_stats = queryset.values('nationality').annotate(count=Count('id'))
        religion_stats = queryset.values('religion').annotate(count=Count('id'))
        
        # Enrollment status
        status_stats = Student.objects.all().values('status').annotate(count=Count('id'))

        return Response({
            'gender': gender_stats,
            'nationality': nationality_stats,
            'religion': religion_stats,
            'status': status_stats,
        })

    @action(detail=False, methods=['get'])
    def enrollment_trends(self, request):
        """
        Retrieves admission and enrollment trends.
        """
        # Admissions grouped by year/month
        from django.db.models.functions import TruncMonth, TruncYear
        
        admissions_by_year = Student.objects.all()\
            .annotate(year=TruncYear('admission_date'))\
            .values('year')\
            .annotate(count=Count('id'))\
            .order_by('year')
            
        return Response({
            'admissions_by_year': admissions_by_year,
        })
        
    @action(detail=False, methods=['get'])
    def class_distribution(self, request):
        """
        Retrieves class and stream capacity distribution.
        """
        distribution = Enrollment.objects.filter(is_active=True, is_deleted=False)\
            .values('grade__name')\
            .annotate(count=Count('id'))\
            .order_by('grade__level_order')
            
        stream_distribution = Enrollment.objects.filter(is_active=True, is_deleted=False, stream__isnull=False)\
            .values('grade__name', 'stream__name')\
            .annotate(count=Count('id'))\
            .order_by('grade__level_order', 'stream__name')
            
        return Response({
            'grade_distribution': distribution,
            'stream_distribution': stream_distribution,
        })
        
    @action(detail=False, methods=['get'])
    def progression_transitions(self, request):
        """
        Retrieves student progression stats (promotions, repetitions).
        """
        # Very basic stub: rely on current enrollment status for now
        status_stats = Enrollment.objects.filter(is_deleted=False)\
            .values('status')\
            .annotate(count=Count('id'))
            
        return Response({
            'progression': status_stats,
        })
