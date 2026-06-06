from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('register/', views.register, name='register'),

path(
    'login/',
    auth_views.LoginView.as_view(
        template_name='accounts/login.html'
    ),
    name='login'
),

path(
    'logout/',
    auth_views.LogoutView.as_view(
        next_page='home'
    ),
    name='logout'
),

path('profile/', views.profile, name='profile'),
path('profile/edit/', views.edit_profile, name='edit_profile'),
path('videos/', views.video_list, name='video_list'),
path('categories/add/', views.add_category, name='add_category'),
path('verify/', views.verify_telegram, name='verify_telegram'),
path('check-verification/', views.check_verification, name='check_verification'),
]