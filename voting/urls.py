from django.urls import path
from . import views
from .views import NheaLoginView, vote_category, next_category, admin_dashboard, register_voter, CompletedView
from .views import reset_password

urlpatterns = [
    path('', NheaLoginView.as_view(), name='login'),

    # ── Public self-registration ──
    path('register/', views.self_register, name='self_register'),
    path('register/success/', views.register_success, name='register_success'),

    # ── Admin-side registration ──
    path('admin/register-voter/', register_voter, name='register_voter'),

    path('vote/<int:category_id>/', vote_category, name='vote_category'),
    path('next_category/<int:category_id>/', next_category, name='next_category'),
    path('admin_dashboard/', admin_dashboard, name='list_voters'),
    path('completed/', CompletedView.as_view(), name='completed'),
    path('reset/', views.reset_all, name='reset_all'),
    path('live_vote_count/', views.live_vote_count, name='live_vote_count'),
    path('Security-Check/', views.enter_access_code, name='enter_access_code'),
    # path('voters/', views.list_voters, name='list_voters'),
    path('logout/', views.logout_voter, name='logout'),
    path('nominees/', views.list_nominees, name='list_nominees'),
    path('nominees/add/', views.add_nominee, name='add_nominee'),
    path('nominees/delete/<int:nominee_id>/', views.delete_nominee, name='delete_nominee'),
    path('manage_categories/', views.manage_categories, name='manage_categories'),
    path('reset_password/', reset_password, name='reset_password'),
    path('encrypted/site_map/nhea2024/', views.site_map, name='site_map'),
]