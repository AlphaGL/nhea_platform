from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count
from django.contrib import messages
from django.contrib.auth import login as auth_login, authenticate
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView
from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from functools import wraps

from .models import Category, Nominee, Vote, Voter
from .forms import (
    VoteForm, VoterForm, AccessCodeForm,
    ResetAllForm, CategoryForm, NomineeForm,
    PasswordResetForm, SelfRegistrationForm,
)
from django.contrib.auth.forms import AuthenticationForm

ACCESS_CODE = 'NHEA2026'


# ─── Password Reset ────────────────────────────────────────────────────────────

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
                messages.success(request, 'Your password has been successfully updated!')
                return redirect('login')
            except Voter.DoesNotExist:
                messages.error(request, 'No voter found with this Voter ID.')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordResetForm()
    return render(request, 'voting/reset_password.html', {'form': form})


# ─── Self-Registration ─────────────────────────────────────────────────────────

def self_register(request):
    """
    Public self-registration.
    On success, shows the user their auto-generated Voter ID so they can
    note it down before being redirected to login.
    """
    if request.method == 'POST':
        form = SelfRegistrationForm(request.POST)
        if form.is_valid():
            voter = form.save()
            # Store the new voter_id in session so the success page can display it
            request.session['new_voter_id'] = voter.voter_id
            return redirect('register_success')
    else:
        form = SelfRegistrationForm()
    return render(request, 'voting/self_register.html', {'form': form})


def register_success(request):
    """Show the newly generated Voter ID to the delegate."""
    voter_id = request.session.pop('new_voter_id', None)
    if not voter_id:
        return redirect('self_register')
    return render(request, 'voting/register_success.html', {'voter_id': voter_id})


# ─── Category Management ───────────────────────────────────────────────────────

def manage_categories(request):
    if request.method == 'POST':
        delete_id = request.POST.get('delete_category_id')
        if delete_id:
            category = get_object_or_404(Category, id=delete_id)
            category.delete()
            messages.success(request, 'Category deleted successfully.')
            return redirect('manage_categories')
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category added successfully.')
            return redirect('manage_categories')
    else:
        form = CategoryForm()
    categories = Category.objects.all().order_by('importance')
    return render(request, 'voting/manage_categories.html', {'form': form, 'categories': categories})


# ─── Nominee Management ────────────────────────────────────────────────────────

def add_nominee(request):
    if request.method == 'POST':
        form = NomineeForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Nominee added successfully.')
            return redirect('list_nominees')
    else:
        form = NomineeForm()
    return render(request, 'voting/add_nominee.html', {'form': form})


def delete_nominee(request, nominee_id):
    nominee = get_object_or_404(Nominee, id=nominee_id)
    nominee.delete()
    messages.success(request, 'Nominee removed successfully.')
    return redirect('list_nominees')


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
                return redirect('list_voters')
            else:
                messages.error(request, 'Invalid access code.')
    else:
        form = AccessCodeForm()
    return render(request, 'voting/security.html', {'form': form})


def list_voters(request):
    if not request.session.get('has_access'):
        return redirect('enter_access_code')

    if request.method == 'POST':
        voter_id = request.POST.get('delete_voter_id')
        if voter_id:
            voter = get_object_or_404(Voter, id=voter_id)
            voter.delete()
            messages.success(request, 'Voter deleted successfully.')
            return redirect('list_voters')

    voters = Voter.objects.all()
    voters_by_org = {}
    count_by_org = {}
    for voter in voters:
        org = voter.organization or 'Unknown'
        if org not in voters_by_org:
            voters_by_org[org] = []
            count_by_org[org] = 0
        voters_by_org[org].append(voter)
        count_by_org[org] += 1

    total_voters = voters.count()
    largest_group = max(count_by_org.values(), default=0)

    return render(request, 'voting/list_voters.html', {
        'voters_by_org': voters_by_org,
        'count_by_org': count_by_org,
        'total_voters': total_voters,
        'largest_group': largest_group,
    })


def logout_voter(request):
    request.session.pop('has_access', None)
    request.session.pop('voter_id', None)
    return redirect('login')


# ─── Vote Reset ────────────────────────────────────────────────────────────────

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
                messages.success(request, 'All votes have been reset successfully.')
            else:
                messages.error(request, 'You must confirm the reset.')
            return redirect('reset_all')
    else:
        form = ResetAllForm()
    return render(request, 'voting/reset_vote.html', {'form': form})


# ─── Live Vote Count ───────────────────────────────────────────────────────────

def live_vote_count(request):
    if request.method == 'POST':
        code = request.POST.get('access_code')
        if code == ACCESS_CODE:
            vote_data = {}
            categories = Category.objects.all().order_by('importance')
            for cat in categories:
                nominees = Nominee.objects.filter(category=cat).annotate(vote_count=Count('vote'))
                vote_data[cat] = nominees
            total_voters = Vote.objects.values('voter').distinct().count()
            return render(request, 'voting/live_vote_count.html', {
                'vote_data': vote_data,
                'total_voters': total_voters
            })
        else:
            messages.error(request, 'Invalid access code.')
    return render(request, 'voting/live_vote_count.html')


# ─── Custom Auth Decorator ─────────────────────────────────────────────────────

def custom_auth_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Unauthorized access.')
        return redirect('login')
    return _wrapped_view


# ─── Admin Registration (staff only) ──────────────────────────────────────────

def register_voter(request):
    """Admin-side registration; voter_id can be set manually."""
    if request.method == 'POST':
        form = VoterForm(request.POST)
        if form.is_valid():
            voter = form.save(commit=False)
            voter.set_password(form.cleaned_data['password'])
            voter.save()
            messages.success(request, f'Voter registered successfully! ID: {voter.voter_id}')
            return redirect('register_voter')
    else:
        form = VoterForm()
    return render(request, 'voting/register_student.html', {'form': form})


# ─── Login ─────────────────────────────────────────────────────────────────────

class NheaLoginView(LoginView):
    template_name = 'voting/login.html'
    form_class = AuthenticationForm

    def form_valid(self, form):
        voter_id = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        voter = authenticate(voter_id=voter_id, password=password)
        if voter is not None:
            auth_login(self.request, voter)
            self.request.session['voter_id'] = voter_id
            return super().form_valid(form)
        else:
            form.add_error(None, 'Invalid Voter ID or password.')
            return self.form_invalid(form)

    def get_success_url(self):
        voter_id = self.request.session.get('voter_id')
        if voter_id:
            voter = Voter.objects.filter(voter_id=voter_id).first()
            if voter:
                total_cats = Category.objects.count()
                voted_cats = Vote.objects.filter(voter=voter).values('category').distinct().count()
                if voted_cats == total_cats:
                    return reverse_lazy('completed')
                remaining = Category.objects.exclude(
                    id__in=Vote.objects.filter(voter=voter).values_list('category_id', flat=True)
                ).order_by('importance').first()
                if remaining:
                    return reverse_lazy('vote_category', kwargs={'category_id': remaining.id})
                return reverse_lazy('completed')
        return reverse_lazy('login')


# ─── Voting ────────────────────────────────────────────────────────────────────

def vote_category(request, category_id):
    voter_id = request.session.get('voter_id')
    if not voter_id:
        return redirect('login')

    voter = get_object_or_404(Voter, voter_id=voter_id)
    category = get_object_or_404(Category, id=category_id)

    # Guard: already voted here
    if Vote.objects.filter(voter=voter, category=category).exists():
        return redirect('next_category', category_id=category_id)

    if request.method == 'POST':
        nominee_id = request.POST.get('nominee')
        if not nominee_id:
            messages.error(request, 'Please select a nominee before continuing.')
            return redirect('vote_category', category_id=category_id)
        nominee = get_object_or_404(Nominee, id=nominee_id, category=category)
        Vote.objects.create(voter=voter, category=category, nominee=nominee)
        messages.success(request, f'Your vote for "{nominee.name}" has been recorded!')
        return redirect('next_category', category_id=category_id)

    nominees = Nominee.objects.filter(category=category)
    total_categories = Category.objects.count()
    voted_count = Vote.objects.filter(voter=voter).count()
    # Progress as a percentage for the progress bar
    progress_pct = int((voted_count / total_categories) * 100) if total_categories else 0

    return render(request, 'voting/vote_position.html', {
        'position': category,
        'contestants': nominees,
        'total_categories': total_categories,
        'voted_count': voted_count,
        'progress_pct': progress_pct,
        'voter': voter,
    })


def next_category(request, category_id):
    voter_id = request.session.get('voter_id')
    if not voter_id:
        return redirect('login')

    voter = get_object_or_404(Voter, voter_id=voter_id)
    voted_cats = Vote.objects.filter(voter=voter).values_list('category_id', flat=True)
    remaining = Category.objects.exclude(id__in=voted_cats).order_by('importance')

    if remaining.exists():
        return redirect('vote_category', category_id=remaining.first().id)
    return redirect('completed')


# ─── Admin Dashboard ───────────────────────────────────────────────────────────

@login_required
@staff_member_required
def admin_dashboard(request):
    if not request.user.is_superuser:
        return redirect('login')

    total_votes = Vote.objects.count()
    total_voters = Voter.objects.count()
    total_categories = Category.objects.count()
    total_nominees = Nominee.objects.count()

    context = {
        'total_votes': total_votes,
        'total_voters': total_voters,
        'total_categories': total_categories,
        'total_nominees': total_nominees,
    }
    return render(request, 'voting/admin_dashboard.html', context)


# ─── Completed & Site Map ──────────────────────────────────────────────────────

class CompletedView(TemplateView):
    template_name = 'voting/completed.html'


def site_map(request):
    return render(request, 'voting/site_map.html')         