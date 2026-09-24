from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from cuentas import views

admin.site.site_header = "Central de Reportes"
admin.site.site_title = "Central de Reportes"
admin.site.index_title = "Administración"

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("reportes/", include("central.urls")),
    path("admin/", admin.site.urls),
]
