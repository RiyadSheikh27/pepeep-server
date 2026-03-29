from django.shortcuts import render
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_somplejwt.exceptions import TokenError, InvalidToken


from apps.utils.custom_response import APIResponse
from apps.restaurants.models import Branch, Employee, Restaurant
from .models import User, OTPVerification
from .serializers import (
    CustomerOTPSendSerializer, CustomerOTPVerifySerializer,
    CustomerProfileSerializer,
    ChangePhoneRequestSerializer, ChangePhoneVerifySerializer,
    EmployeeLoginSerializer,
    OwnerLoginSerializer, BranchSerializer, CreateEmployeeSerializer, EmployeeDetailSerializer,
    AdminLoginSerializer, AdminForgotPasswordSerializer,
    AdminResetPasswordSerializer, AdminProfileSerializer,
)