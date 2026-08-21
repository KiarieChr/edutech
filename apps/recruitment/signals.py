from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Avg, F
from .models import *


@receiver(post_save, sender=JobOpening)
def create_recruitment_workflow(sender, instance, created, **kwargs):
    """Create default workflow stages when a job opening is created"""
    if created:
        default_stages = [
            ('Application Screening', 1, 2),
            ('Technical Assessment', 2, 3),
            ('First Interview', 3, 5),
            ('Second Interview', 4, 5),
            ('Reference Check', 5, 3),
            ('Offer Approval', 6, 2),
            ('Onboarding', 7, 7)
        ]
        
        for stage_name, stage_order, duration in default_stages:
            RecruitmentWorkflow.objects.create(
                job_opening=instance,
                stage_name=stage_name,
                stage_order=stage_order,
                expected_duration_days=duration,
                is_mandatory=True
            )


@receiver(post_save, sender=JobApplication)
def create_application_workflow(sender, instance, created, **kwargs):
    """Create workflow progress for new applications"""
    if created:
        workflow_stages = RecruitmentWorkflow.objects.filter(
            job_opening=instance.job_opening
        ).order_by('stage_order')
        
        for stage in workflow_stages:
            ApplicationWorkflow.objects.create(
                application=instance,
                workflow_stage=stage,
                status=ApplicationWorkflow.StageStatus.NOT_STARTED
            )
        
        # Update first stage to in-progress
        first_stage = ApplicationWorkflow.objects.filter(
            application=instance
        ).order_by('workflow_stage__stage_order').first()
        
        if first_stage:
            first_stage.status = ApplicationWorkflow.StageStatus.IN_PROGRESS
            first_stage.started_date = timezone.now()
            first_stage.save()


@receiver(post_save, sender=InterviewEvaluation)
def update_application_status_after_interview(sender, instance, created, **kwargs):
    """Update application status based on interview evaluation"""
    if not created:
        return
    
    interview = instance.interview
    application = interview.application
    
    # Get all evaluations for this interview
    evaluations = InterviewEvaluation.objects.filter(interview=interview)
    total_evaluations = evaluations.count()
    
    if total_evaluations == interview.interviewers.count():
        # All evaluations submitted
        avg_score = evaluations.aggregate(avg=Avg('overall_score'))['avg']
        
        if avg_score >= 7:  # Pass threshold
            # Move to next stage
            current_workflow = ApplicationWorkflow.objects.filter(
                application=application,
                status=ApplicationWorkflow.StageStatus.IN_PROGRESS
            ).first()
            
            if current_workflow:
                current_workflow.status = ApplicationWorkflow.StageStatus.COMPLETED
                current_workflow.completed_date = timezone.now()
                current_workflow.save()
                
                # Move to next stage
                next_workflow = ApplicationWorkflow.objects.filter(
                    application=application,
                    workflow_stage__stage_order__gt=current_workflow.workflow_stage.stage_order
                ).order_by('workflow_stage__stage_order').first()
                
                if next_workflow:
                    next_workflow.status = ApplicationWorkflow.StageStatus.IN_PROGRESS
                    next_workflow.started_date = timezone.now()
                    next_workflow.save()
        else:
            # Interview failed
            application.application_status = JobApplication.ApplicationStatus.REJECTED
            application.save()


@receiver(post_save, sender=OfferLetter)
def update_analytics_on_offer(sender, instance, created, **kwargs):
    """Update recruitment analytics when an offer is created"""
    if created:
        job_opening = instance.job_opening
        
        # Get or create analytics for today
        today = timezone.now().date()
        analytics, created = RecruitmentAnalytics.objects.get_or_create(
            job_opening=job_opening,
            metric_date=today,
            defaults={
                'offers_made': 1
            }
        )
        
        if not created:
            analytics.offers_made = F('offers_made') + 1
            analytics.save()