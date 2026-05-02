from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q
from django.contrib import messages
from django.contrib.auth import login as auth_login, authenticate
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView
from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_POST
from functools import wraps

from .models import Category, Nominee, Vote, Voter, ActivityLog
from .forms import (
    VoteForm, VoterForm, AccessCodeForm,
    ResetAllForm, CategoryForm, NomineeForm,
    PasswordResetForm, SelfRegistrationForm,
    PhoneOTPVerifyForm, EmailOTPVerifyForm,
    AdminCreationForm, AdminPasswordChangeForm,
)
from .otp_utils import (
    send_email_otp, verify_otp,
    verify_firebase_id_token, get_phone_from_token,
)
from .log_utils import log_action
from .geo_utils import get_client_ip, get_geo_data
from django.contrib.auth.forms import AuthenticationForm

ACCESS_CODE = 'NHEA2026'


# ─── Decorators ────────────────────────────────────────────────────────────────

def superadmin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Superadmin access required.')
        return redirect('login')
    return _wrapped


def admin_required(view_func):
    """Allows both superadmin and staff (admin) users."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            if request.user.must_change_password and request.path != '/panel/change-password/':
                messages.warning(request, 'You must change your password before continuing.')
                return redirect('admin_change_password')
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Admin access required. Please log in.')
        return redirect('login')
    return _wrapped


def role_required(permission_method):
    """
    Decorator factory — checks a named permission method on the Voter model.
    Usage: @role_required('can_manage_voters')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not (request.user.is_authenticated and
                    (request.user.is_staff or request.user.is_superuser)):
                messages.error(request, 'Admin access required.')
                return redirect('login')
            if request.user.must_change_password and request.path != '/panel/change-password/':
                messages.warning(request, 'You must change your password before continuing.')
                return redirect('admin_change_password')
            checker = getattr(request.user, permission_method, None)
            if checker and checker():
                return view_func(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to access this section.')
            return redirect('admin_dashboard')
        return _wrapped
    return decorator


def custom_auth_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Unauthorized access.')
        return redirect('login')
    return _wrapped_view


# ─── Password Reset (voter) ────────────────────────────────────────────────────

def reset_password(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            voter_id = form.cleaned_data.get('voter_id')
            new_password = form.cleaned_data.get('new_password1')
            try:
                voter = Voter.objects.get(voter_id=voter_id)
                voter.set_password(new_password)
                voter.save()
                log_action(request, 'PASSWORD_RESET',
                           description=f'Password reset for voter {voter_id}',
                           actor=voter)
                messages.success(request, 'Your password has been successfully updated!')
                return redirect('login')
            except Voter.DoesNotExist:
                messages.error(request, 'No voter found with this Voter ID.')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordResetForm()
    return render(request, 'voting/reset_password.html', {'form': form})


# ─── Admin Password Change (forced on first login) ────────────────────────────

def admin_change_password(request):
    if not request.user.is_authenticated:
        return redirect('login')
    voter = request.user

    # Only staff/superadmin accounts should hit this view
    if not (voter.is_staff or voter.is_superuser):
        return redirect('voting_dashboard')

    # If they don't actually need to change, send them home
    if not voter.must_change_password:
        if voter.is_superuser:
            return redirect('superadmin_dashboard')
        return redirect('admin_dashboard')

    if request.method == 'POST':
        form = AdminPasswordChangeForm(request.POST, user=voter)
        if form.is_valid():
            voter.set_password(form.cleaned_data['new_password1'])
            voter.must_change_password = False
            voter.save()
            log_action(request, 'PASSWORD_CHANGE',
                       description='Admin changed temporary password on first login',
                       actor=voter)
            messages.success(request, 'Password updated successfully. Welcome!')
            # Re-authenticate with the new password so the session stays valid
            auth_login(request, voter)
            # Redirect based on role
            if voter.is_superuser:
                return redirect('superadmin_dashboard')
            return redirect('admin_dashboard')
    else:
        form = AdminPasswordChangeForm(user=voter)

    return render(request, 'voting/admin_change_password.html', {
        'form': form,
        'user_role': 'Superadmin' if voter.is_superuser else voter.get_role_display_name(),
    })


# ─── Self-Registration ─────────────────────────────────────────────────────────

def self_register(request):
    if request.method == 'POST':
        form = SelfRegistrationForm(request.POST)
        if form.is_valid():
            voter = form.save()
            request.session['pending_voter_id'] = voter.voter_id
            request.session['new_voter_id']     = voter.voter_id
            log_action(request, 'VOTER_CREATED',
                       description=f'Self-registered: {voter.full_name}',
                       target=voter)
            if voter.phone_number:
                return redirect('verify_phone')
            elif voter.email:
                sent = send_email_otp(voter.email, voter.full_name)
                if not sent:
                    messages.error(request, 'Could not send verification email. Please try again.')
                return redirect('verify_email')
    else:
        form = SelfRegistrationForm()
    return render(request, 'voting/self_register.html', {'form': form})


def register_success(request):
    voter_id = request.session.pop('new_voter_id', None)
    if not voter_id:
        return redirect('self_register')
    return render(request, 'voting/register_success.html', {'voter_id': voter_id})


# ─── Phone OTP Verification (Firebase) ────────────────────────────────────────

def verify_phone(request):
    voter_id = request.session.get('pending_voter_id')
    if not voter_id:
        return redirect('self_register')

    voter = get_object_or_404(Voter, voter_id=voter_id)

    if request.method == 'POST':
        form = PhoneOTPVerifyForm(request.POST)
        if form.is_valid():
            id_token = form.cleaned_data['firebase_id_token']
            decoded  = verify_firebase_id_token(id_token)
            if decoded:
                phone_from_token = get_phone_from_token(decoded)
                if phone_from_token and phone_from_token == voter.phone_number:
                    voter.is_phone_verified = True
                    voter.save(update_fields=['is_phone_verified'])
                    request.session.pop('pending_voter_id', None)
                    log_action(request, 'PHONE_VERIFIED',
                               description=f'Phone verified for {voter.full_name}',
                               actor=voter)
                    messages.success(request, 'Phone verified! Your Voter ID is ready.')
                    return redirect('register_success')
                else:
                    messages.error(request, 'Phone number mismatch.')
            else:
                messages.error(request, 'OTP verification failed. Please try again.')

    from django.conf import settings
    firebase_api_key = getattr(settings, 'FIREBASE_WEB_API_KEY', '')
    return render(request, 'voting/verify_phone.html', {
        'voter': voter,
        'firebase_api_key': firebase_api_key,
        'phone_form': PhoneOTPVerifyForm(),
    })


def use_email_instead(request):
    voter_id = request.session.get('pending_voter_id')
    if not voter_id:
        return redirect('self_register')

    voter = get_object_or_404(Voter, voter_id=voter_id)
    if not voter.email:
        messages.error(request, 'No email address is linked to your account.')
        return redirect('verify_phone')

    sent = send_email_otp(voter.email, voter.full_name)
    if sent:
        messages.success(request, f'A verification code has been sent to {voter.email}.')
    else:
        messages.error(request, 'Could not send the email. Please try again.')
    return redirect('verify_email')


# ─── Email OTP Verification (Brevo) ───────────────────────────────────────────

def verify_email(request):
    voter_id = request.session.get('pending_voter_id')
    if not voter_id:
        return redirect('self_register')

    voter = get_object_or_404(Voter, voter_id=voter_id)

    if not voter.email:
        messages.error(request, 'No email address linked to your account.')
        return redirect('verify_phone')

    if request.method == 'POST':
        if 'resend' in request.POST:
            sent = send_email_otp(voter.email, voter.full_name)
            if sent:
                messages.success(request, 'A new code has been sent.')
            else:
                messages.error(request, 'Could not resend. Please try again shortly.')
            return redirect('verify_email')

        form = EmailOTPVerifyForm(request.POST)
        if form.is_valid():
            otp_code = form.cleaned_data['otp_code']
            if verify_otp(voter.email, otp_code):
                voter.is_email_verified = True
                voter.save(update_fields=['is_email_verified'])
                request.session.pop('pending_voter_id', None)
                log_action(request, 'EMAIL_VERIFIED',
                           description=f'Email verified for {voter.full_name}',
                           actor=voter)
                messages.success(request, 'Email verified! Your account is ready.')
                return redirect('register_success')
            else:
                messages.error(request, 'Invalid or expired code. Please try again.')
    else:
        form = EmailOTPVerifyForm()

    has_phone = bool(voter.phone_number)
    return render(request, 'voting/verify_email.html', {
        'voter':     voter,
        'form':      form,
        'has_phone': has_phone,
    })


# ─── Category Management ───────────────────────────────────────────────────────

@role_required('can_manage_nominees')
def manage_categories(request):
    if request.method == 'POST':
        delete_id = request.POST.get('delete_category_id')
        if delete_id:
            category = get_object_or_404(Category, id=delete_id)
            log_action(request, 'CATEGORY_DELETED',
                       description=f'Category deleted: {category.name}',
                       actor=request.user, target=category)
            category.delete()
            messages.success(request, 'Category deleted successfully.')
            return redirect('manage_categories')
        form = CategoryForm(request.POST)
        if form.is_valid():
            cat = form.save()
            log_action(request, 'CATEGORY_CREATED',
                       description=f'Category created: {cat.name}',
                       actor=request.user, target=cat)
            messages.success(request, 'Category added successfully.')
            return redirect('manage_categories')
    else:
        form = CategoryForm()
    categories = Category.objects.all().order_by('importance')
    return render(request, 'voting/manage_categories.html', {'form': form, 'categories': categories})


# ─── Nominee Management ────────────────────────────────────────────────────────

@role_required('can_manage_nominees')
def add_nominee(request):
    if request.method == 'POST':
        form = NomineeForm(request.POST, request.FILES)
        if form.is_valid():
            nominee = form.save()
            log_action(request, 'NOMINEE_CREATED',
                       description=f'Nominee added: {nominee.name} ({nominee.category.name})',
                       actor=request.user, target=nominee)
            messages.success(request, 'Nominee added successfully.')
            return redirect('list_nominees')
    else:
        form = NomineeForm()
    return render(request, 'voting/add_nominee.html', {'form': form})


@role_required('can_manage_nominees')
def delete_nominee(request, nominee_id):
    nominee = get_object_or_404(Nominee, id=nominee_id)
    log_action(request, 'NOMINEE_DELETED',
               description=f'Nominee removed: {nominee.name}',
               actor=request.user, target=nominee)
    nominee.delete()
    messages.success(request, 'Nominee removed successfully.')
    return redirect('list_nominees')


@role_required('can_manage_nominees')
def list_nominees(request):
    nominees = Nominee.objects.select_related('category').all()
    return render(request, 'voting/list_nominees.html', {'nominees': nominees})


# ─── Access Code / Voter List ──────────────────────────────────────────────────

def enter_access_code(request):
    if request.method == 'POST':
        form = AccessCodeForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data.get('access_code')
            if code == ACCESS_CODE:
                request.session['has_access'] = True
                log_action(request, 'ACCESS_CODE_USED',
                           description='Access code used to enter voter list',
                           actor=request.user if request.user.is_authenticated else None)
                return redirect('list_voters')
            else:
                messages.error(request, 'Invalid access code.')
    else:
        form = AccessCodeForm()
    return render(request, 'voting/security.html', {'form': form})


@role_required('can_manage_voters')
def list_voters(request):
    if request.method == 'POST':
        voter_id = request.POST.get('delete_voter_id')
        if voter_id:
            voter = get_object_or_404(Voter, id=voter_id)
            log_action(request, 'VOTER_DELETED',
                       description=f'Voter deleted: {voter.full_name} ({voter.voter_id})',
                       actor=request.user if request.user.is_authenticated else None,
                       target=voter)
            voter.delete()
            messages.success(request, 'Voter deleted successfully.')
            return redirect('list_voters')

    voters = Voter.objects.filter(is_staff=False, is_superuser=False)
    voters_by_org = {}
    count_by_org = {}
    for voter in voters:
        org = voter.organization or 'Unknown'
        if org not in voters_by_org:
            voters_by_org[org] = []
            count_by_org[org] = 0
        voters_by_org[org].append(voter)
        count_by_org[org] += 1

    total_voters  = voters.count()
    largest_group = max(count_by_org.values(), default=0)

    return render(request, 'voting/list_voters.html', {
        'voters_by_org': voters_by_org,
        'count_by_org':  count_by_org,
        'total_voters':  total_voters,
        'largest_group': largest_group,
    })


def logout_voter(request):
    actor = request.user if request.user.is_authenticated else None
    log_action(request, 'LOGOUT',
               description=f'User logged out: {actor.full_name if actor else "Unknown"}',
               actor=actor)
    request.session.flush()
    return redirect('login')


# ─── Vote Reset ────────────────────────────────────────────────────────────────

@role_required('can_reset_votes')
def reset_all(request):
    if request.method == 'POST':
        form = ResetAllForm(request.POST)
        if form.is_valid():
            entered_code = form.cleaned_data.get('access_code')
            if entered_code != ACCESS_CODE:
                messages.error(request, 'Invalid access code. Please try again.')
                return redirect('reset_all')
            if form.cleaned_data.get('confirm_reset'):
                Vote.objects.all().delete()
                log_action(request, 'VOTES_RESET',
                           description='All votes were reset by admin',
                           actor=request.user)
                messages.success(request, 'All votes have been reset successfully.')
            else:
                messages.error(request, 'You must confirm the reset.')
            return redirect('reset_all')
    else:
        form = ResetAllForm()
    return render(request, 'voting/reset_vote.html', {'form': form})


# ─── Live Vote Count ───────────────────────────────────────────────────────────

@role_required('can_view_results')
def live_vote_count(request):
    vote_data = {}
    categories = Category.objects.all().order_by('importance')
    for cat in categories:
        nominees = Nominee.objects.filter(category=cat).annotate(vote_count=Count('vote'))
        vote_data[cat] = nominees
    total_voters = Vote.objects.values('voter').distinct().count()
    return render(request, 'voting/live_vote_count.html', {
        'vote_data':    vote_data,
        'total_voters': total_voters
    })


# ─── Admin Registration (staff only) ──────────────────────────────────────────

@role_required('can_manage_voters')
def register_voter(request):
    if request.method == 'POST':
        form = VoterForm(request.POST)
        if form.is_valid():
            voter = form.save(commit=False)
            voter.set_password(form.cleaned_data['password'])
            voter.is_phone_verified = True
            voter.save()
            log_action(request, 'VOTER_CREATED',
                       description=f'Voter registered by admin: {voter.full_name}',
                       actor=request.user, target=voter)
            messages.success(request, f'Voter registered successfully! ID: {voter.voter_id}')
            return redirect('register_voter')
    else:
        form = VoterForm()
    return render(request, 'voting/register_student.html', {'form': form})


# ─── Superadmin: Create Admin ─────────────────────────────────────────────────

@superadmin_required
def create_admin(request):
    if request.method == 'POST':
        form = AdminCreationForm(request.POST)
        if form.is_valid():
            admin_user = form.save(created_by=request.user)
            log_action(request, 'ADMIN_CREATED',
                       description=f'Admin account created for {admin_user.full_name} '
                                   f'(ID: {admin_user.voter_id}, Role: {admin_user.admin_role})',
                       actor=request.user, target=admin_user)
            messages.success(
                request,
                f'Admin created successfully! Voter ID: {admin_user.voter_id}. '
                f'Role: {admin_user.get_admin_role_display()}. '
                f'They must change their password on first login.'
            )
            return redirect('manage_admins')
    else:
        form = AdminCreationForm()
    return render(request, 'voting/create_admin.html', {'form': form})


@superadmin_required
def manage_admins(request):
    """List all admin users (is_staff=True). Superadmin can delete them."""
    if request.method == 'POST':
        admin_id = request.POST.get('delete_admin_id')
        if admin_id:
            admin_user = get_object_or_404(Voter, id=admin_id, is_staff=True, is_superuser=False)
            log_action(request, 'VOTER_DELETED',
                       description=f'Admin account deleted: {admin_user.full_name}',
                       actor=request.user, target=admin_user)
            admin_user.delete()
            messages.success(request, 'Admin account removed.')
            return redirect('manage_admins')

    admins = Voter.objects.filter(is_staff=True, is_superuser=False).order_by('full_name')
    return render(request, 'voting/manage_admins.html', {'admins': admins})


@superadmin_required
def promote_to_superadmin(request, admin_id):
    """
    Promote a staff admin to superadmin.
    Only an existing superadmin can do this.
    Requires a POST with 'confirm_promote' checkbox for safety.
    """
    admin_user = get_object_or_404(Voter, id=admin_id, is_staff=True, is_superuser=False)

    if request.method == 'POST':
        if request.POST.get('confirm_promote'):
            admin_user.is_superuser = True
            admin_user.admin_role   = None        # superadmins don't use role codes
            admin_user.save(update_fields=['is_superuser', 'admin_role'])
            log_action(
                request, 'SYSTEM_UPDATE',
                description=f'Admin {admin_user.full_name} ({admin_user.voter_id}) promoted to Superadmin',
                actor=request.user,
                target=admin_user,
            )
            messages.success(
                request,
                f'{admin_user.full_name} has been promoted to Superadmin. '
                f'They will have full platform access on their next login.'
            )
        else:
            messages.error(request, 'You must tick the confirmation box to promote an admin.')
        return redirect('manage_admins')

    # GET — show a confirmation page
    return render(request, 'voting/promote_superadmin_confirm.html', {'admin_user': admin_user})


# ─── Activity Log ──────────────────────────────────────────────────────────────

@admin_required
def activity_log_view(request):
    logs = ActivityLog.objects.select_related('actor').all()

    action_filter = request.GET.get('action', '')
    actor_filter  = request.GET.get('actor', '')
    date_from     = request.GET.get('date_from', '')
    date_to       = request.GET.get('date_to', '')

    if action_filter:
        logs = logs.filter(action=action_filter)
    if actor_filter:
        logs = logs.filter(
            Q(actor__full_name__icontains=actor_filter) |
            Q(actor__voter_id__icontains=actor_filter)
        )
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    action_choices = ActivityLog.ACTION_CHOICES
    return render(request, 'voting/activity_log.html', {
        'logs':           logs[:500],
        'action_choices': action_choices,
        'action_filter':  action_filter,
        'actor_filter':   actor_filter,
        'date_from':      date_from,
        'date_to':        date_to,
    })


# ─── Voting Analytics ──────────────────────────────────────────────────────────

@role_required('can_view_results')
def voting_analytics(request):
    by_country = (
        Vote.objects
        .exclude(country__isnull=True).exclude(country='')
        .values('country').annotate(count=Count('id')).order_by('-count')
    )
    by_region = (
        Vote.objects
        .exclude(region__isnull=True).exclude(region='')
        .values('region', 'country').annotate(count=Count('id')).order_by('-count')[:10]
    )
    by_category = (
        Vote.objects
        .values('category__name').annotate(count=Count('id')).order_by('-count')
    )
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(hours=24)
    by_hour = (
        Vote.objects.filter(timestamp__gte=cutoff)
        .extra(select={'hour': "date_trunc('hour', timestamp)"})
        .values('hour').annotate(count=Count('id')).order_by('hour')
    )
    geo_points = list(
        Vote.objects.exclude(latitude__isnull=True).values('latitude', 'longitude')
    )
    total_votes     = Vote.objects.count()
    total_voters    = Vote.objects.values('voter').distinct().count()
    total_countries = by_country.count()

    return render(request, 'voting/voting_analytics.html', {
        'by_country':      list(by_country),
        'by_region':       list(by_region),
        'by_category':     list(by_category),
        'by_hour':         list(by_hour),
        'geo_points':      geo_points,
        'total_votes':     total_votes,
        'total_voters':    total_voters,
        'total_countries': total_countries,
    })


# ─── Login ─────────────────────────────────────────────────────────────────────

class NheaLoginView(LoginView):
    template_name = 'voting/login.html'
    form_class = AuthenticationForm

    def form_valid(self, form):
        voter_id = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        voter    = authenticate(voter_id=voter_id, password=password)

        if voter is None:
            log_action(self.request, 'LOGIN_FAILED',
                       description=f'Failed login attempt for voter_id: {voter_id}')
            form.add_error(None, 'Invalid Voter ID or password.')
            return self.form_invalid(form)

        # ── STAFF / ADMIN ACCOUNTS ─────────────────────────────────────────
        if voter.is_staff or voter.is_superuser:
            auth_login(self.request, voter)
            self.request.session['voter_id'] = voter_id
            log_action(self.request, 'LOGIN',
                       description=f'{"Superadmin" if voter.is_superuser else "Admin"} login: {voter.full_name}',
                       actor=voter)

            # Force password reset on very first login (set by superadmin)
            if voter.must_change_password:
                messages.warning(
                    self.request,
                    'Welcome! Your account requires a password change before you can continue.'
                )
                return redirect('admin_change_password')

            # Route to correct dashboard
            if voter.is_superuser:
                return redirect('superadmin_dashboard')
            return redirect('admin_dashboard')

        # ── REGULAR VOTER ACCOUNTS ─────────────────────────────────────────
        # Verification gate — unverified voters must complete OTP first
        if not voter.is_verified:
            self.request.session['pending_voter_id'] = voter.voter_id
            self.request.session['new_voter_id']     = voter.voter_id
            messages.warning(self.request, 'Please verify your identity before voting.')
            if voter.phone_number:
                return redirect('verify_phone')
            elif voter.email:
                send_email_otp(voter.email, voter.full_name)
                return redirect('verify_email')
            else:
                messages.error(self.request, 'No contact method on file. Contact an administrator.')
                return self.form_invalid(form)

        auth_login(self.request, voter)
        self.request.session['voter_id'] = voter_id
        log_action(self.request, 'LOGIN',
                   description=f'Voter login: {voter.full_name}',
                   actor=voter)
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('voting_dashboard')


# ─── Superadmin Dashboard ──────────────────────────────────────────────────────

@superadmin_required
def superadmin_dashboard(request):
    """Full-control dashboard exclusively for the superadmin."""
    total_votes      = Vote.objects.count()
    total_voters     = Voter.objects.filter(is_staff=False, is_superuser=False).count()
    total_categories = Category.objects.count()
    total_nominees   = Nominee.objects.count()
    total_admins     = Voter.objects.filter(is_staff=True, is_superuser=False).count()
    recent_logs      = ActivityLog.objects.select_related('actor').all()[:10]
    admins           = Voter.objects.filter(is_staff=True, is_superuser=False).order_by('full_name')

    # Role distribution
    from .models import Voter as V
    role_counts = {}
    for code, label in V.ROLE_CHOICES:
        role_counts[label] = Voter.objects.filter(admin_role=code, is_staff=True).count()

    context = {
        'total_votes':      total_votes,
        'total_voters':     total_voters,
        'total_categories': total_categories,
        'total_nominees':   total_nominees,
        'total_admins':     total_admins,
        'recent_logs':      recent_logs,
        'admins':           admins,
        'role_counts':      role_counts,
    }
    return render(request, 'voting/superadmin_dashboard.html', context)


# ─── Admin Dashboard ───────────────────────────────────────────────────────────

@admin_required
def admin_dashboard(request):
    """Role-filtered dashboard for staff admins."""
    user = request.user

    # Redirect superadmin to their own dashboard
    if user.is_superuser:
        return redirect('superadmin_dashboard')

    total_votes      = Vote.objects.count()
    total_voters     = Voter.objects.filter(is_staff=False, is_superuser=False).count()
    total_categories = Category.objects.count()
    total_nominees   = Nominee.objects.count()
    recent_logs      = ActivityLog.objects.select_related('actor').all()[:8]

    context = {
        'total_votes':      total_votes,
        'total_voters':     total_voters,
        'total_categories': total_categories,
        'total_nominees':   total_nominees,
        'recent_logs':      recent_logs,
        'admin':            user,
    }
    return render(request, 'voting/admin_dashboard.html', context)


# ─── Voting Dashboard ──────────────────────────────────────────────────────────

def voting_dashboard(request):
    voter_id = request.session.get('voter_id')
    if not voter_id:
        return redirect('login')

    voter = get_object_or_404(Voter, voter_id=voter_id)

    if not voter.is_verified and not voter.is_staff:
        messages.warning(request, 'Please complete identity verification before voting.')
        request.session['pending_voter_id'] = voter.voter_id
        if voter.phone_number:
            return redirect('verify_phone')
        return redirect('verify_email')

    all_categories = Category.objects.all().order_by('importance')
    voted_category_ids = set(
        Vote.objects.filter(voter=voter).values_list('category_id', flat=True)
    )

    category_list = []
    for cat in all_categories:
        nominee_count = Nominee.objects.filter(category=cat).count()
        voted = cat.id in voted_category_ids
        voted_nominee = None
        if voted:
            try:
                vote_obj = Vote.objects.select_related('nominee').get(voter=voter, category=cat)
                voted_nominee = vote_obj.nominee.name
            except Vote.DoesNotExist:
                pass
        category_list.append({
            'category':      cat,
            'voted':         voted,
            'voted_nominee': voted_nominee,
            'nominee_count': nominee_count,
        })

    total_categories  = len(category_list)
    voted_count       = len(voted_category_ids)
    unvoted_count     = total_categories - voted_count
    progress_pct      = int((voted_count / total_categories) * 100) if total_categories else 0

    return render(request, 'voting/voting_dashboard.html', {
        'voter':            voter,
        'category_list':    category_list,
        'total_categories': total_categories,
        'voted_count':      voted_count,
        'unvoted_count':    unvoted_count,
        'progress_pct':     progress_pct,
    })


# ─── Voting ────────────────────────────────────────────────────────────────────

def vote_category(request, category_id):
    voter_id = request.session.get('voter_id')
    if not voter_id:
        return redirect('login')

    voter = get_object_or_404(Voter, voter_id=voter_id)

    if not voter.is_verified and not voter.is_staff:
        messages.warning(request, 'Please complete identity verification before voting.')
        request.session['pending_voter_id'] = voter.voter_id
        if voter.phone_number:
            return redirect('verify_phone')
        return redirect('verify_email')

    category = get_object_or_404(Category, id=category_id)

    if Vote.objects.filter(voter=voter, category=category).exists():
        messages.info(request, f'You have already voted in "{category.name}".')
        return redirect('voting_dashboard')

    if request.method == 'POST':
        if 'skip' in request.POST:
            messages.info(request, f'Skipped "{category.name}". You can return to vote later.')
            return redirect('voting_dashboard')

        nominee_id = request.POST.get('nominee')
        if not nominee_id:
            messages.error(request, 'Please select a nominee before continuing.')
            return redirect('vote_category', category_id=category_id)
        nominee = get_object_or_404(Nominee, id=nominee_id, category=category)

        ip  = get_client_ip(request)
        geo = get_geo_data(ip)

        vote = Vote.objects.create(
            voter=voter, category=category, nominee=nominee,
            ip_address=ip or None,
            country=geo.get('country') or None,
            region=geo.get('region') or None,
            city=geo.get('city') or None,
            latitude=geo.get('lat'),
            longitude=geo.get('lon'),
        )
        log_action(request, 'VOTE_CAST',
                   description=f'{voter.full_name} voted for {nominee.name} in {category.name}',
                   actor=voter, target=vote)
        messages.success(request, f'Your vote for "{nominee.name}" has been recorded!')
        return redirect('voting_dashboard')

    nominees       = Nominee.objects.filter(category=category)
    all_categories = Category.objects.count()
    voted_count    = Vote.objects.filter(voter=voter).count()
    progress_pct   = int((voted_count / all_categories) * 100) if all_categories else 0

    return render(request, 'voting/vote_position.html', {
        'position':         category,
        'contestants':      nominees,
        'total_categories': all_categories,
        'voted_count':      voted_count,
        'progress_pct':     progress_pct,
        'voter':            voter,
    })


def next_category(request, category_id):
    return redirect('voting_dashboard')


# ─── Completed & Site Map ──────────────────────────────────────────────────────

class CompletedView(TemplateView):
    template_name = 'voting/completed.html'


def site_map(request):
    return render(request, 'voting/site_map.html')




# ─── Admin Login ───────────────────────────────────────────────────────────────
 
class AdminLoginView(LoginView):
    """
    Dedicated login page for admin (staff) accounts.
    Rejects regular voters and superadmins with a clear error message.
    """
    template_name = 'voting/admin_login.html'
    form_class    = AuthenticationForm
 
    def form_valid(self, form):
        voter_id = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        voter    = authenticate(voter_id=voter_id, password=password)
 
        if voter is None:
            log_action(self.request, 'LOGIN_FAILED',
                       description=f'Admin login failed for voter_id: {voter_id}')
            form.add_error(None, 'Invalid Voter ID or password.')
            return self.form_invalid(form)
 
        # Must be a staff admin (not a superuser, not a regular voter)
        if voter.is_superuser:
            form.add_error(None,
                'Superadmin accounts must use the Superadmin Sign In portal.')
            return self.form_invalid(form)
 
        if not voter.is_staff:
            form.add_error(None,
                'This portal is for admin accounts only. '
                'Please use the Voter Sign In instead.')
            return self.form_invalid(form)
 
        # Successful admin login
        auth_login(self.request, voter)
        self.request.session['voter_id'] = voter_id
        log_action(self.request, 'LOGIN',
                   description=f'Admin login: {voter.full_name}',
                   actor=voter)
 
        if voter.must_change_password:
            messages.warning(
                self.request,
                'Welcome! You must change your password before continuing.'
            )
            return redirect('admin_change_password')
 
        return redirect('admin_dashboard')
 
    def get(self, request, *args, **kwargs):
        # Already logged-in admin → go straight to dashboard
        if request.user.is_authenticated and request.user.is_staff and not request.user.is_superuser:
            return redirect('admin_dashboard')
        return super().get(request, *args, **kwargs)
 
 
# ─── Superadmin Login ──────────────────────────────────────────────────────────
 
class SuperadminLoginView(LoginView):
    """
    Dedicated login page for superadmin accounts only.
    Rejects regular voters and staff admins.
    """
    template_name = 'voting/superadmin_login.html'
    form_class    = AuthenticationForm
 
    def form_valid(self, form):
        voter_id = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        voter    = authenticate(voter_id=voter_id, password=password)
 
        if voter is None:
            log_action(self.request, 'LOGIN_FAILED',
                       description=f'Superadmin login failed for voter_id: {voter_id}')
            form.add_error(None, 'Invalid Voter ID or password.')
            return self.form_invalid(form)
 
        # Must be a superuser
        if not voter.is_superuser:
            if voter.is_staff:
                form.add_error(None,
                    'Admin accounts must use the Admin Sign In portal.')
            else:
                form.add_error(None,
                    'This portal is restricted to superadmin accounts only.')
            return self.form_invalid(form)
 
        # Successful superadmin login
        auth_login(self.request, voter)
        self.request.session['voter_id'] = voter_id
        log_action(self.request, 'LOGIN',
                   description=f'Superadmin login: {voter.full_name}',
                   actor=voter)
 
        if voter.must_change_password:
            messages.warning(
                self.request,
                'Welcome! You must change your password before continuing.'
            )
            return redirect('admin_change_password')
 
        return redirect('superadmin_dashboard')
 
    def get(self, request, *args, **kwargs):
        # Already logged-in superadmin → skip login
        if request.user.is_authenticated and request.user.is_superuser:
            return redirect('superadmin_dashboard')
        return super().get(request, *args, **kwargs)