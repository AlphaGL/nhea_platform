from django.urls import path
from . import views
from .views import (
    NheaLoginView, vote_category, next_category,
    admin_dashboard, register_voter, CompletedView,
    reset_password, verify_phone, verify_email, use_email_instead,
    voting_dashboard,
)

urlpatterns = [
    path('', NheaLoginView.as_view(), name='login'),

    # ── Public self-registration ──────────────────────────────────────────
    path('register/',          views.self_register,    name='self_register'),
    path('register/success/',  views.register_success, name='register_success'),

    # ── OTP Verification ──────────────────────────────────────────────────
    path('verify/phone/',         verify_phone,       name='verify_phone'),
    path('verify/phone/email/',   use_email_instead,  name='use_email_instead'),
    path('verify/email/',         verify_email,       name='verify_email'),

    # ── Admin-side voter registration ─────────────────────────────────────
    path('panel/register-voter/', register_voter,      name='register_voter'),

    # ── Superadmin: Admin Management ──────────────────────────────────────
    path('panel/create-admin/',   views.create_admin,  name='create_admin'),
    path('panel/manage-admins/',  views.manage_admins, name='manage_admins'),

    # ── Admin: Force Password Change ──────────────────────────────────────
    path('panel/change-password/', views.admin_change_password, name='admin_change_password'),

    # ── Voting ────────────────────────────────────────────────────────────
    path('vote/',                            voting_dashboard, name='voting_dashboard'),
    path('vote/<int:category_id>/',          vote_category,    name='vote_category'),
    path('next_category/<int:category_id>/', next_category,    name='next_category'),

    # ── Admin Dashboard & Tools ───────────────────────────────────────────
    path('admin_dashboard/',  admin_dashboard,          name='admin_dashboard'),
    path('voters/',           views.list_voters,        name='list_voters'),
    path('completed/',        CompletedView.as_view(),  name='completed'),
    path('reset/',            views.reset_all,          name='reset_all'),
    path('live_vote_count/',  views.live_vote_count,    name='live_vote_count'),
    path('Security-Check/',   views.enter_access_code,  name='enter_access_code'),
    path('logout/',           views.logout_voter,       name='logout'),

    # ── Nominees ──────────────────────────────────────────────────────────
    path('nominees/',                         views.list_nominees,  name='list_nominees'),
    path('nominees/add/',                     views.add_nominee,    name='add_nominee'),
    path('nominees/delete/<int:nominee_id>/', views.delete_nominee, name='delete_nominee'),

    # ── Categories ────────────────────────────────────────────────────────
    path('manage_categories/', views.manage_categories, name='manage_categories'),

    # ── Activity Log & Analytics ──────────────────────────────────────────
    # IMPORTANT: These must NOT start with 'admin/' — that prefix is
    # reserved by Django's built-in admin site and will 404 otherwise.
    path('panel/activity-log/',     views.activity_log_view, name='activity_log'),
    path('panel/voting-analytics/', views.voting_analytics,  name='voting_analytics'),

    # ── Misc ──────────────────────────────────────────────────────────────
    path('reset_password/',              reset_password,   name='reset_password'),
    path('encrypted/site_map/nhea2024/', views.site_map,   name='site_map'),
]