# ============================================================================
# DOCUMENT SERVICE
# ============================================================================
"""
Service for managing employee documents.
"""

from django.db import transaction
from django.utils import timezone
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.exceptions import ValidationError
from typing import Optional, Dict, List, Any
import mimetypes
import os

from workforce.core_models import Employee
from workforce.models import EmployeeDocument


class DocumentService:
    """
    Service for managing employee documents with verification workflow.
    """
    
    ALLOWED_EXTENSIONS = [
        '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif',
        '.xls', '.xlsx', '.txt', '.rtf', '.odt'
    ]
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    def __init__(self, user):
        """Initialize with the current user."""
        self.user = user
    
    def _validate_file(self, file: InMemoryUploadedFile) -> None:
        """
        Validate uploaded file.
        
        Raises:
            ValidationError: If file is invalid
        """
        # Check file size
        if file.size > self.MAX_FILE_SIZE:
            raise ValidationError(
                f"File size ({file.size / 1024 / 1024:.2f} MB) exceeds maximum "
                f"allowed size ({self.MAX_FILE_SIZE / 1024 / 1024} MB)"
            )
        
        # Check file extension
        _, ext = os.path.splitext(file.name.lower())
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"File type '{ext}' not allowed. Allowed types: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )
    
    @transaction.atomic
    def upload_document(
        self,
        employee: Employee,
        file: InMemoryUploadedFile,
        document_name: str,
        document_category: str,
        document_type: str,
        description: str = '',
        document_number: str = '',
        issue_date=None,
        expiry_date=None,
        issuing_authority: str = '',
        issuing_country_id: Optional[int] = None,
        is_confidential: bool = False,
        expiry_alert_days: int = 30,
    ) -> EmployeeDocument:
        """
        Upload a new document for an employee.
        
        Args:
            employee: The employee
            file: The uploaded file
            document_name: Display name for the document
            document_category: Category from EmployeeDocument.DocumentCategory
            document_type: Specific type (e.g., "Passport", "Degree")
            description: Optional description
            document_number: Document reference number
            issue_date: Date of issue
            expiry_date: Expiry date if applicable
            issuing_authority: Authority that issued the document
            issuing_country_id: ID of Country model
            is_confidential: Whether document is confidential
            expiry_alert_days: Days before expiry to send alert
            
        Returns:
            EmployeeDocument: The created document
        """
        # Validate file
        self._validate_file(file)
        
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(file.name)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        # Check for existing document with same category and type
        existing = EmployeeDocument.objects.filter(
            employee=employee,
            document_category=document_category,
            document_type=document_type,
            is_active=True
        ).order_by('-version').first()
        
        version = 1
        previous_version = None
        if existing:
            version = existing.version + 1
            previous_version = existing
        
        document = EmployeeDocument.objects.create(
            employee=employee,
            document_name=document_name,
            document_category=document_category,
            document_type=document_type,
            description=description,
            file=file,
            file_size_bytes=file.size,
            mime_type=mime_type,
            original_filename=file.name,
            document_number=document_number,
            issue_date=issue_date,
            expiry_date=expiry_date,
            issuing_authority=issuing_authority,
            issuing_country_id=issuing_country_id,
            is_confidential=is_confidential,
            expiry_alert_days=expiry_alert_days,
            version=version,
            previous_version=previous_version,
        )
        
        return document
    
    @transaction.atomic
    def verify_document(
        self,
        document: EmployeeDocument,
        notes: str = '',
    ) -> EmployeeDocument:
        """
        Mark a document as verified.
        
        Args:
            document: The document to verify
            notes: Verification notes
            
        Returns:
            EmployeeDocument: The updated document
        """
        document.verification_status = EmployeeDocument.VerificationStatus.VERIFIED
        document.verified_by = self.user
        document.verification_date = timezone.now().date()
        document.verification_notes = notes
        document.save()
        
        return document
    
    @transaction.atomic
    def reject_document(
        self,
        document: EmployeeDocument,
        rejection_reason: str,
    ) -> EmployeeDocument:
        """
        Reject a document verification.
        
        Args:
            document: The document to reject
            rejection_reason: Reason for rejection
            
        Returns:
            EmployeeDocument: The updated document
        """
        if not rejection_reason:
            raise ValidationError("Rejection reason is required")
        
        document.verification_status = EmployeeDocument.VerificationStatus.REJECTED
        document.verified_by = self.user
        document.verification_date = timezone.now().date()
        document.rejection_reason = rejection_reason
        document.save()
        
        return document
    
    def get_employee_documents(
        self,
        employee: Employee,
        category: Optional[str] = None,
        verification_status: Optional[str] = None,
        include_inactive: bool = False,
    ):
        """
        Get documents for an employee with optional filters.
        
        Args:
            employee: The employee
            category: Filter by category
            verification_status: Filter by verification status
            include_inactive: Include inactive documents
            
        Returns:
            QuerySet of EmployeeDocument
        """
        queryset = EmployeeDocument.objects.filter(employee=employee)
        
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        
        if category:
            queryset = queryset.filter(document_category=category)
        
        if verification_status:
            queryset = queryset.filter(verification_status=verification_status)
        
        return queryset.select_related(
            'verified_by', 'issuing_country', 'previous_version'
        ).order_by('-created_at')
    
    def get_expiring_documents(
        self,
        days_ahead: int = 30,
        employee: Optional[Employee] = None,
    ):
        """
        Get documents expiring within specified days.
        
        Args:
            days_ahead: Number of days to look ahead
            employee: Optional employee filter
            
        Returns:
            QuerySet of EmployeeDocument
        """
        from datetime import timedelta
        
        expiry_threshold = timezone.now().date() + timedelta(days=days_ahead)
        
        queryset = EmployeeDocument.objects.filter(
            is_active=True,
            expiry_date__isnull=False,
            expiry_date__lte=expiry_threshold,
            verification_status=EmployeeDocument.VerificationStatus.VERIFIED,
        )
        
        if employee:
            queryset = queryset.filter(employee=employee)
        
        return queryset.select_related('employee').order_by('expiry_date')
    
    def get_expired_documents(self, employee: Optional[Employee] = None):
        """
        Get all expired documents.
        
        Args:
            employee: Optional employee filter
            
        Returns:
            QuerySet of EmployeeDocument
        """
        today = timezone.now().date()
        
        queryset = EmployeeDocument.objects.filter(
            is_active=True,
            expiry_date__isnull=False,
            expiry_date__lt=today,
        )
        
        if employee:
            queryset = queryset.filter(employee=employee)
        
        return queryset.select_related('employee').order_by('expiry_date')
    
    def mark_expired_documents(self) -> int:
        """
        Mark all expired documents with EXPIRED status.
        
        Returns:
            int: Number of documents updated
        """
        today = timezone.now().date()
        
        expired = EmployeeDocument.objects.filter(
            is_active=True,
            expiry_date__isnull=False,
            expiry_date__lt=today,
            verification_status=EmployeeDocument.VerificationStatus.VERIFIED,
        )
        
        count = expired.update(
            verification_status=EmployeeDocument.VerificationStatus.EXPIRED
        )
        
        return count
    
    @transaction.atomic
    def archive_document(self, document: EmployeeDocument) -> EmployeeDocument:
        """
        Archive (soft delete) a document.
        
        Args:
            document: The document to archive
            
        Returns:
            EmployeeDocument: The updated document
        """
        document.is_active = False
        document.save()
        return document
    
    @transaction.atomic
    def restore_document(self, document: EmployeeDocument) -> EmployeeDocument:
        """
        Restore an archived document.
        
        Args:
            document: The document to restore
            
        Returns:
            EmployeeDocument: The updated document
        """
        document.is_active = True
        document.save()
        return document
    
    def get_document_statistics(self, employee: Optional[Employee] = None) -> Dict:
        """
        Get document statistics.
        
        Args:
            employee: Optional employee filter
            
        Returns:
            Dict with statistics
        """
        from django.db.models import Count
        
        queryset = EmployeeDocument.objects.filter(is_active=True)
        
        if employee:
            queryset = queryset.filter(employee=employee)
        
        # By category
        by_category = queryset.values('document_category').annotate(count=Count('id'))
        
        # By verification status
        by_status = queryset.values('verification_status').annotate(count=Count('id'))
        
        # Expiring soon (30 days)
        from datetime import timedelta
        expiry_threshold = timezone.now().date() + timedelta(days=30)
        expiring_soon = queryset.filter(
            expiry_date__isnull=False,
            expiry_date__lte=expiry_threshold,
            expiry_date__gte=timezone.now().date()
        ).count()
        
        # Already expired
        expired = queryset.filter(
            expiry_date__isnull=False,
            expiry_date__lt=timezone.now().date()
        ).count()
        
        return {
            'total_documents': queryset.count(),
            'by_category': {item['document_category']: item['count'] for item in by_category},
            'by_verification_status': {item['verification_status']: item['count'] for item in by_status},
            'expiring_soon': expiring_soon,
            'expired': expired,
        }
    
    def get_document_history(self, document: EmployeeDocument) -> List[EmployeeDocument]:
        """
        Get version history for a document.
        
        Args:
            document: The current document
            
        Returns:
            List of document versions (newest first)
        """
        versions = [document]
        current = document
        
        while current.previous_version:
            versions.append(current.previous_version)
            current = current.previous_version
            if len(versions) > 100:  # Safety limit
                break
        
        return versions
    
    def check_required_documents(
        self,
        employee: Employee,
        required_types: List[str],
    ) -> Dict:
        """
        Check if employee has all required document types.
        
        Args:
            employee: The employee to check
            required_types: List of required document types
            
        Returns:
            Dict with compliance status
        """
        existing_docs = EmployeeDocument.objects.filter(
            employee=employee,
            is_active=True,
            verification_status=EmployeeDocument.VerificationStatus.VERIFIED,
        ).values_list('document_type', flat=True)
        
        existing_set = set(existing_docs)
        required_set = set(required_types)
        
        missing = required_set - existing_set
        
        return {
            'is_compliant': len(missing) == 0,
            'required': list(required_set),
            'existing': list(existing_set),
            'missing': list(missing),
            'compliance_percentage': round(
                (len(required_set) - len(missing)) / len(required_set) * 100 
                if required_set else 100, 2
            ),
        }
