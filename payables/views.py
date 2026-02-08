from rest_framework import viewsets
from .models import Vendor, Bill
from .serializers import VendorSerializer, BillSerializer

class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer

class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
