from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from student_management.models.class_session import StudentPlacement
from student_management.serializers import StudentPlacementSerializer

class StudentPlacementViewSet(viewsets.ModelViewSet):
    queryset = StudentPlacement.objects.all()
    serializer_class = StudentPlacementSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['academic_year', 'term', 'curriculum', 'grade', 'session_status', 'session_type']
    search_fields = ['student__student__first_name', 'student__student__last_name', 'student__admission_number']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
