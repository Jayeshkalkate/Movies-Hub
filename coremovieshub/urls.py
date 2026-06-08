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
path("webhook/", views.telegram_webhook, name="telegram_webhook"),
path(
    "watch/<int:movie_id>/",
    views.watch_movie,
    name="watch_movie"
),

path(
    "download/<int:movie_id>/",
    views.download_movie,
    name="download_movie"
),
path(
    "search/",
    views.search_movies,
    name="search_movies"
),

path(
    "category/<slug:slug>/",
    views.category_movies,
    name="category_movies"
),

path(
    "movie/<int:movie_id>/",
    views.movie_detail,
    name="movie_detail"
),
path(
    "dashboard/",
    views.admin_dashboard,
    name="admin_dashboard"
),
path(
    "admin/movies/edit/<int:movie_id>/",
    views.edit_movie,
    name="edit_movie"
),
path(
    "watchlist/",
    views.my_watchlist,
    name="my_watchlist"
),

path(
    "watchlist/add/<int:movie_id>/",
    views.add_to_watchlist,
    name="add_to_watchlist"
),

path(
    "watchlist/remove/<int:movie_id>/",
    views.remove_from_watchlist,
    name="remove_from_watchlist"
),
path(
    "admin/movies/delete/<int:movie_id>/",
    views.delete_movie,
    name="delete_movie"
),
path(
    "dashboard/movies/",
    views.movie_management,
    name="movie_management"
),
path(
    "dashboard/upload-movie/",
    views.upload_movie,
    name='upload_movie'
),
]