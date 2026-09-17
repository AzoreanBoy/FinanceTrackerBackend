from accounts.models import CustomUser
from accounts.serializers import *
from rest_framework import viewsets

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = CustomUserSerializer
    
    def get_queryset(self):
        if self.request.user.is_staff:
            return CustomUser.objects.all()

        return CustomUser.objects.filter(pk=self.request.user.pk)
