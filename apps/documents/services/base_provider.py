"""
Base Document Data Provider.
Defines the contract for transforming domain models into validated document contexts
and rendering semantic document bodies for WeasyPrint paged media.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from django.core.exceptions import ValidationError


class BaseDocumentDataProvider(ABC):
    """
    Abstract base provider that decouples application modules (Student Management,
    Finance, HR, Academics) from document template resolution and PDF rendering.
    """

    def __init__(self, entity: Any, context: Optional[Dict[str, Any]] = None):
        self.entity = entity
        self.extra_context = context or {}
        self.validate()

    @abstractmethod
    def get_document_type(self) -> str:
        """
        Unique machine identifier for this document type (e.g. 'admission_letter').
        """
        pass

    @abstractmethod
    def get_document_title(self) -> str:
        """
        Official document title (e.g. 'OFFICIAL LETTER OF ADMISSION').
        """
        pass

    @abstractmethod
    def get_category(self) -> str:
        """
        DocumentTemplate category matching DocumentTemplate.Category (e.g. 'letter', 'student_report').
        """
        pass

    def validate(self) -> None:
        """
        Validates that required entity attributes or relationships exist.
        Subclasses should raise ValidationError with clear descriptive messages.
        """
        if not self.entity:
            raise ValidationError("Entity record is required for document generation.")

    @abstractmethod
    def get_context_data(self) -> Dict[str, Any]:
        """
        Returns a normalized, sanitized dictionary representing the document data.
        Handles optional fields gracefully.
        """
        pass

    @abstractmethod
    def render_body_html(self, context: Dict[str, Any]) -> str:
        """
        Renders the document's central body HTML.
        This HTML is placed within the document's main flow beneath the prominent
        first-page masthead, flowing across continuation pages as necessary.
        """
        pass
