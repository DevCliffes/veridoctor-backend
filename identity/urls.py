from django.urls import path
from identity.views import (
    StatusView,
    RegisterView,
    LoginView,
    VerifyOTPView,
    SendOTPView,
    ActivateAccountView,
    DeactivateIdentityView,
    IdentityAccountsView,
    ResetPasswordView,
    confirmResetPasswordView,
    TokenView,
)

urlpatterns = [
    path("status", StatusView.as_view(), name="status"),
    path("register", RegisterView.as_view(), name="register"),
    path("register/<str:identity_id>", RegisterView.as_view(), name="register-detail"),
    path("login", LoginView.as_view(), name="login"),
    path("authorise", TokenView.as_view(), name="login"),
    path("otp-send", SendOTPView.as_view()),
    path("otp-verify", VerifyOTPView.as_view()),
    path("activate/<str:account_type>", ActivateAccountView.as_view()),
    path("<str:identity_id>/deactivate", DeactivateIdentityView.as_view()),
    path("reset-password", ResetPasswordView.as_view()),
    path("reset-password/confirm", confirmResetPasswordView.as_view()),
    path("<str:identity_id>/accounts", IdentityAccountsView.as_view()),
]
