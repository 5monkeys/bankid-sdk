from django.urls import path

from bankid_sdk.contrib.django import rest

urlpatterns = [
    path("bankid/auth/", rest.auth, name="auth"),
    path("bankid/check/", rest.check, name="check"),
    path("bankid/cancel/", rest.cancel, name="cancel"),
]
