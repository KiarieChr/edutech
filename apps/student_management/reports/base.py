"""
Student Management Reporting Base Architecture
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from django.db.models import QuerySet
from django.utils import timezone


class BaseStudentReport(ABC):
    """
    Abstract base class for all Student Management reports.
    Enforces unified querying, summary calculation, pagination, and multi-format exports.
    """
    report_id: str = ""
    title: str = ""
    description: str = ""

    def __init__(self, user, filters: Dict[str, Any]):
        self.user = user
        self.filters = filters
        self.generated_at = timezone.now()

    def _get_scope_metadata(self) -> Dict[str, Any]:
        """Resolve institution and campus scope metadata for report headers and exports."""
        from core.campus_filter import get_effective_campus_id_for_user
        from core.models import InstitutionProfile
        from workforce.models import Campus

        inst = InstitutionProfile.get_instance()
        inst_name = inst.name if inst else "Fahari Academia"
        effective_cid = get_effective_campus_id_for_user(self.user, self.filters)
        campus_name = "All Campuses (Consolidated)"
        campus_code = "ALL"
        report_mode = "consolidated"
        if effective_cid:
            camp = Campus.objects.filter(id=effective_cid).first()
            if camp:
                campus_name = f"{camp.name} ({camp.code})"
                campus_code = camp.code
                report_mode = "individual_campus"

        gen_by = "System"
        if self.user and getattr(self.user, "is_authenticated", False):
            full_n = self.user.get_full_name() if callable(getattr(self.user, "get_full_name", None)) else getattr(self.user, "get_full_name", "")
            gen_by = full_n or self.user.username

        return {
            "institution_name": inst_name,
            "report_mode": report_mode,
            "effective_campus_id": effective_cid,
            "campus_scope": campus_name,
            "campus_code": campus_code,
            "generated_by": gen_by,
        }

    @abstractmethod
    def get_base_queryset(self) -> QuerySet:
        """Return the base queryset with all joins, filters, and campus/tenant scoping applied."""
        pass

    @abstractmethod
    def get_summary_metrics(self, queryset: QuerySet) -> Dict[str, Any]:
        """Compute aggregate summary figures across the ENTIRE filtered dataset."""
        pass

    @abstractmethod
    def get_columns(self) -> List[Dict[str, str]]:
        """Return list of column definitions: [{'key': 'adm_no', 'label': 'Adm No.', 'align': 'left'}]."""
        pass

    @abstractmethod
    def serialize_record(self, record: Any) -> Dict[str, Any]:
        """Serialize a single model instance into preview and export dictionary."""
        pass

    def get_preview_data(self, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """
        Generate preview payload:
        - summary metrics computed over FULL matching dataset.
        - results sliced by page & page_size.
        """
        qs = self.get_base_queryset()
        summaries = self.get_summary_metrics(qs)
        total_count = qs.count()

        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        start = (page - 1) * page_size
        end = start + page_size

        sliced_qs = qs[start:end]
        results = [self.serialize_record(item) for item in sliced_qs]

        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

        scope_meta = self._get_scope_metadata()
        return {
            "metadata": {
                "report_id": self.report_id,
                "title": self.title,
                "description": self.description,
                "generated_at": self.generated_at.isoformat(),
                "applied_filters": self.filters,
                **scope_meta,
            },
            "summaries": summaries,
            "columns": self.get_columns(),
            "pagination": {
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            },
            "results": results,
        }

    def get_export_data(self, max_records: int = 5000) -> Dict[str, Any]:
        """
        Fetch full filtered dataset for document generation.
        Enforces max_records ceiling to prevent memory exhaustion.
        """
        qs = self.get_base_queryset()
        total_count = qs.count()
        if total_count > max_records:
            raise ValueError(
                f"Export dataset contains {total_count} records, which exceeds the limit of {max_records}. "
                f"Please refine your filters."
            )

        summaries = self.get_summary_metrics(qs)
        results = [self.serialize_record(item) for item in qs]

        scope_meta = self._get_scope_metadata()
        return {
            "metadata": {
                "report_id": self.report_id,
                "title": self.title,
                "description": f"{self.description} | Scope: {scope_meta['campus_scope']} | Generated by: {scope_meta['generated_by']}",
                "generated_at": self.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "applied_filters": self.filters,
                **scope_meta,
            },
            "summaries": summaries,
            "columns": self.get_columns(),
            "results": results,
        }
