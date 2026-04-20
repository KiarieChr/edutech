from django.contrib import admin
from .models import (
    PurchaseRequisition, RequisitionLine,
    RequestForQuotation, RFQLine, RFQSupplierInvitation,
    SupplierQuotation, SupplierQuotationLine,
    PurchaseOrder, PurchaseOrderLine,
    SupplierContract, ContractMilestone,
)


class RequisitionLineInline(admin.TabularInline):
    model = RequisitionLine
    extra = 1


@admin.register(PurchaseRequisition)
class PurchaseRequisitionAdmin(admin.ModelAdmin):
    list_display = ['requisition_number', 'requested_by', 'department', 'priority', 'status', 'created_at']
    list_filter = ['status', 'priority', 'department']
    search_fields = ['requisition_number', 'justification']
    readonly_fields = ['requisition_number', 'created_at', 'updated_at']
    inlines = [RequisitionLineInline]


class RFQLineInline(admin.TabularInline):
    model = RFQLine
    extra = 1


class RFQInvitationInline(admin.TabularInline):
    model = RFQSupplierInvitation
    extra = 1
    readonly_fields = ['token', 'invited_at', 'viewed_at', 'public_url']


@admin.register(RequestForQuotation)
class RFQAdmin(admin.ModelAdmin):
    list_display = ['rfq_number', 'title', 'status', 'deadline', 'created_at']
    list_filter = ['status']
    search_fields = ['rfq_number', 'title']
    readonly_fields = ['rfq_number', 'created_at', 'updated_at']
    inlines = [RFQLineInline, RFQInvitationInline]


class QuotationLineInline(admin.TabularInline):
    model = SupplierQuotationLine
    extra = 0


@admin.register(SupplierQuotation)
class SupplierQuotationAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'status', 'total_amount', 'submitted_at']
    list_filter = ['status']
    readonly_fields = ['submitted_at']
    inlines = [QuotationLineInline]


class POLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'supplier', 'status', 'total_amount', 'order_date', 'created_at']
    list_filter = ['status', 'supplier']
    search_fields = ['po_number', 'notes']
    readonly_fields = ['po_number', 'created_at', 'updated_at']
    inlines = [POLineInline]


class MilestoneInline(admin.TabularInline):
    model = ContractMilestone
    extra = 1


@admin.register(SupplierContract)
class SupplierContractAdmin(admin.ModelAdmin):
    list_display = ['contract_number', 'title', 'supplier', 'contract_type', 'status', 'end_date', 'days_remaining']
    list_filter = ['status', 'contract_type']
    search_fields = ['contract_number', 'title']
    readonly_fields = ['contract_number', 'created_at', 'updated_at']
    inlines = [MilestoneInline]
