# ============================================================================
# PERFORMANCE VIEWSETS
# ============================================================================

class PerformanceMetricViewSet(viewsets.ModelViewSet):
    """ViewSet for Performance Metrics"""
    queryset = PerformanceMetric.objects.all()
    serializer_class = PerformanceMetricSerializer
    permission_classes = [permissions.IsAuthenticated]

class AppraisalCycleViewSet(viewsets.ModelViewSet):
    """ViewSet for Appraisal Cycles"""
    queryset = AppraisalCycle.objects.all().order_by('-start_date')
    serializer_class = AppraisalCycleSerializer
    permission_classes = [permissions.IsAuthenticated]

class EmployeeAppraisalViewSet(viewsets.ModelViewSet):
    """ViewSet for Employee Appraisals"""
    queryset = EmployeeAppraisal.objects.all().select_related('employee', 'appraiser', 'appraisal_cycle')
    serializer_class = EmployeeAppraisalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        
        # If not HR/Admin, restrict to own appraisals or appraisals where user is appraiser
        if not (user.is_staff or user.is_superuser or user.groups.filter(name='HR').exists()):
            try:
                employee = user.employee_profile
                qs = qs.filter(Q(employee=employee) | Q(appraiser=employee))
            except Exception:
                return qs.none()
        return qs

    @action(detail=False, methods=['get'])
    def dashboard_metrics(self, request):
        """Aggregate performance data for dashboard"""
        user = request.user
        
        # Base querysets
        appraisals = self.get_queryset()
        goals = EmployeePerformanceGoal.objects.all()
        
        if not (user.is_staff or user.is_superuser or user.groups.filter(name='HR').exists()):
            try:
                employee = user.employee_profile
                goals = goals.filter(employee=employee)
            except Exception:
                goals = goals.none()
        
        # Compute metrics
        total_appraisals = appraisals.count()
        pending_reviews = appraisals.filter(status__in=['draft', 'submitted']).count()
        completed_reviews = appraisals.filter(status='approved').count()
        
        # Compute goals metrics
        total_goals = goals.count()
        completed_goals = goals.filter(status='completed').count()
        in_progress_goals = goals.filter(status='in_progress').count()
        
        goal_completion_rate = 0
        if total_goals > 0:
            goal_completion_rate = int((completed_goals / total_goals) * 100)
        
        return Response({
            'metrics': [
                {
                    'id': 1,
                    'title': 'Goal Completion',
                    'value': f"{goal_completion_rate}%",
                    'subtitle': f'{completed_goals} of {total_goals} goals met',
                    'trend': '+5% vs last period',
                    'trendUp': True,
                    'color': 'bg-blue-500',
                    'lightColor': 'bg-blue-50'
                },
                {
                    'id': 2,
                    'title': 'Pending Reviews',
                    'value': pending_reviews,
                    'subtitle': 'Awaiting action',
                    'trend': '-2 since last week',
                    'trendUp': True,
                    'color': 'bg-orange-500',
                    'lightColor': 'bg-orange-50'
                },
                {
                    'id': 3,
                    'title': 'Avg Appraisals',
                    'value': '4.2',
                    'subtitle': 'Out of 5.0',
                    'trend': '+0.3 vs last cycle',
                    'trendUp': True,
                    'color': 'bg-green-500',
                    'lightColor': 'bg-green-50'
                },
                {
                    'id': 4,
                    'title': 'Completed Reviews',
                    'value': completed_reviews,
                    'subtitle': 'This cycle',
                    'trend': f'{total_appraisals} total',
                    'trendUp': True,
                    'color': 'bg-purple-500',
                    'lightColor': 'bg-purple-50'
                }
            ],
            'recent_appraisals': EmployeeAppraisalSerializer(appraisals.order_by('-appraisal_date')[:5], many=True).data,
            'goals': EmployeePerformanceGoalSerializer(goals.order_by('-target_completion_date')[:5], many=True).data
        })

class EmployeePerformanceGoalViewSet(viewsets.ModelViewSet):
    """ViewSet for Employee Performance Goals"""
    queryset = EmployeePerformanceGoal.objects.all().select_related('employee')
    serializer_class = EmployeePerformanceGoalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        
        # If not HR/Admin, restrict to own goals
        if not (user.is_staff or user.is_superuser or user.groups.filter(name='HR').exists()):
            try:
                employee = user.employee_profile
                qs = qs.filter(employee=employee)
            except Exception:
                return qs.none()
        return qs
