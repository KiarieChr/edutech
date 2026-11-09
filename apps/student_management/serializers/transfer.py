from rest_framework import serializers
from student_management.models.transfer import StudentCampusTransfer


class StudentCampusTransferSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.student.get_full_name', read_only=True)
    source_campus_name = serializers.CharField(source='source_campus.name', read_only=True, default='Unassigned')
    target_campus_name = serializers.CharField(source='target_campus.name', read_only=True)
    transferred_by_name = serializers.CharField(source='transferred_by.get_full_name', read_only=True, default='System')

    class Meta:
        model = StudentCampusTransfer
        fields = [
            'id', 'student', 'student_name', 'admission', 'admission_number',
            'source_campus', 'source_campus_name', 'target_campus', 'target_campus_name',
            'previous_class', 'new_class', 'reason', 'notes',
            'transferred_by', 'transferred_by_name', 'transferred_at'
        ]
        read_only_fields = fields

