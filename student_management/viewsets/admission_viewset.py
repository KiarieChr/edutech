from rest_framework import viewsets, permissions, filters
from student_management.models.admission import Admission
from student_management.serializers import AdmissionSerializer

class AdmissionViewSet(viewsets.ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = AdmissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['admission_number', 'student__student__first_name', 'student__student__last_name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, admitted_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
