from rest_framework import serializers
from .models import Route, Stop, FeeStructure, StudentAssignment, FeeCharge

class RouteSerializer(serializers.ModelSerializer):
    active_student_count = serializers.SerializerMethodField()
    capacity_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = '__all__'

    def get_active_student_count(self, obj):
        return obj.student_assignments.filter(is_active=True).count()

    def get_capacity_percentage(self, obj):
        if obj.capacity == 0:
            return 0
        count = self.get_active_student_count(obj)
        return round((count / obj.capacity) * 100, 1)

class StopSerializer(serializers.ModelSerializer):
    route_name = serializers.ReadOnlyField(source='route.route_name')

    class Meta:
        model = Stop
        fields = '__all__'

class FeeStructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeStructure
        fields = '__all__'

    def validate(self, attrs):
        # Validate uniqueness for (route, fee_type, academic_year, term)
        route = attrs.get('route')
        fee_type = attrs.get('fee_type')
        academic_year = attrs.get('academic_year')
        term = attrs.get('term')

        qs = FeeStructure.objects.filter(
            route=route,
            fee_type=fee_type,
            academic_year=academic_year,
            term=term
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "A fee structure for this route, fee type, year, and term already exists."
            )
        return attrs

class StudentAssignmentSerializer(serializers.ModelSerializer):
    student_details = serializers.SerializerMethodField()
    override_capacity = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = StudentAssignment
        fields = '__all__'
        read_only_fields = ('is_active',)

    def get_student_details(self, obj):
        return {
            'admission_number': getattr(obj.student, 'admission_number', None),
            'first_name': getattr(obj.student, 'first_name', ''),
            'last_name': getattr(obj.student, 'last_name', ''),
            'current_class': getattr(obj.student, 'current_class_name', '')
        }

    def validate(self, attrs):
        # Validate that stop belongs to the selected route
        route = attrs.get('route')
        stop = attrs.get('stop')
        
        if route and stop and stop.route != route:
            raise serializers.ValidationError({
                "stop": "The selected stop does not belong to the selected route."
            })

        # Capacity validation logic
        if route and not self.instance: # Only on creation or route change
            active_count = route.student_assignments.filter(is_active=True).count()
            capacity = route.capacity
            override_capacity = attrs.pop('override_capacity', False)

            if capacity > 0:
                if active_count >= capacity and not override_capacity:
                    raise serializers.ValidationError({
                        "route": f"This route is at 100% capacity ({capacity}/{capacity}). Use override_capacity to force assignment."
                    })
                # We can't really "warn" through REST API other than an extra field, but we enforce the strict block.
        else:
            attrs.pop('override_capacity', None)

        return attrs

class FeeChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeCharge
        fields = '__all__'

class BatchChargeGenerationSerializer(serializers.Serializer):
    academic_year_id = serializers.IntegerField(required=True)
    term_id = serializers.IntegerField(required=True)
    route_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    due_date = serializers.DateField(required=False, allow_null=True)
    enable_prorating = serializers.BooleanField(default=True, required=False)
