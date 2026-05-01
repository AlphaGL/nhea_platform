from django import forms
from django.core.exceptions import ValidationError
from .models import Category, Nominee, Voter, Vote
import re


class PasswordResetForm(forms.Form):
    voter_id = forms.CharField(
        max_length=100,
        label="Voter ID",
        widget=forms.TextInput(attrs={'placeholder': 'e.g. NHEA-2026-AB3XY'})
    )
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'New password'})
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm new password'})
    )

    def clean_voter_id(self):
        voter_id = self.cleaned_data.get('voter_id')
        if not Voter.objects.filter(voter_id=voter_id).exists():
            raise ValidationError("No voter found with this Voter ID.")
        return voter_id

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password1")
        p2 = cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
        return cleaned_data


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'importance']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class NomineeForm(forms.ModelForm):
    class Meta:
        model = Nominee
        fields = ['category', 'name', 'organization', 'image']


class AccessCodeForm(forms.Form):
    access_code = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter Access Code'}),
        label='Access Code'
    )


class ResetAllForm(forms.Form):
    access_code = forms.CharField(widget=forms.PasswordInput, label="Access Code")
    confirm_reset = forms.BooleanField(label="I confirm I want to reset all votes", required=True)


class VoteForm(forms.Form):
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=True)
    nominee = forms.ModelChoiceField(queryset=Nominee.objects.none(), required=True)

    def __init__(self, *args, **kwargs):
        category_id = kwargs.pop('category_id', None)
        super().__init__(*args, **kwargs)
        if category_id:
            self.fields['nominee'].queryset = Nominee.objects.filter(category_id=category_id)


# ── Self-Registration (PUBLIC) ─────────────────────────────────────────────────

class SelfRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Choose a password'}),
        min_length=6,
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Repeat password'}),
    )

    class Meta:
        model = Voter
        fields = ['full_name', 'organization', 'phone_number', 'email']
        labels = {
            'full_name':     'Full Name',
            'organization':  'Organisation / Institution',
            'phone_number':  'Phone Number (for SMS OTP)',
            'email':         'Email Address (fallback OTP)',
        }
        widgets = {
            'full_name':    forms.TextInput(attrs={'placeholder': 'Your full name'}),
            'organization': forms.TextInput(attrs={'placeholder': 'Hospital, clinic, institution…'}),
            'phone_number': forms.TextInput(attrs={
                'placeholder': '+2348100000000',
                'id': 'id_phone_number',
            }),
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        if phone:
            if not re.match(r'^\+\d{7,15}$', phone):
                raise ValidationError(
                    "Enter a valid international phone number (e.g. +2348100000000)."
                )
            if Voter.objects.filter(phone_number=phone).exists():
                raise ValidationError("This phone number is already registered.")
        return phone or None

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email and Voter.objects.filter(email=email).exists():
            raise ValidationError("This email address is already registered.")
        return email or None

    def clean(self):
        cleaned_data = super().clean()
        p1    = cleaned_data.get('password1')
        p2    = cleaned_data.get('password2')
        phone = cleaned_data.get('phone_number')
        email = cleaned_data.get('email')

        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")

        if not phone and not email:
            raise ValidationError(
                "Please provide at least a phone number or email address "
                "so we can verify your identity."
            )
        return cleaned_data

    def save(self, commit=True):
        from .models import generate_voter_id
        voter = super().save(commit=False)
        voter.voter_id = generate_voter_id()
        voter.set_password(self.cleaned_data['password1'])
        voter.is_phone_verified = False
        voter.is_email_verified = False
        if commit:
            voter.save()
        return voter


# ── Admin-side voter form ──────────────────────────────────────────────────────

class VoterForm(forms.ModelForm):
    class Meta:
        model = Voter
        fields = ['voter_id', 'full_name', 'organization', 'password', 'phone_number', 'email']
        labels = {
            'voter_id':     'Voter ID',
            'full_name':    'Full Name',
            'organization': 'Organization / Institution',
            'phone_number': 'Phone Number',
            'email':        'Email Address',
        }
        widgets = {
            'password': forms.PasswordInput(),
        }


# ── OTP Verification forms ─────────────────────────────────────────────────────

class PhoneOTPVerifyForm(forms.Form):
    firebase_id_token = forms.CharField(widget=forms.HiddenInput())


class EmailOTPVerifyForm(forms.Form):
    otp_code = forms.CharField(
        label="Verification Code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder':   '6-digit code',
            'inputmode':     'numeric',
            'autocomplete':  'one-time-code',
            'class':         'nhea-input otp-input',
        })
    )


# ── Admin Creation (Superadmin only) ──────────────────────────────────────────

class AdminCreationForm(forms.ModelForm):
    """
    Used by the superadmin to create a new admin account.
    The superadmin sets the initial password; admin must change it on first login.
    """
    initial_password = forms.CharField(
        label="Initial Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Temporary password'}),
        min_length=6,
        help_text="Admin will be forced to change this on first login.",
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Repeat password'}),
    )

    class Meta:
        model = Voter
        fields = ['full_name', 'organization', 'email', 'phone_number']
        labels = {
            'full_name':    'Full Name',
            'organization': 'Organization / Department',
            'email':        'Email Address',
            'phone_number': 'Phone Number',
        }
        widgets = {
            'full_name':    forms.TextInput(attrs={'placeholder': 'Admin full name'}),
            'organization': forms.TextInput(attrs={'placeholder': 'Department / unit'}),
            'email':        forms.EmailInput(attrs={'placeholder': 'admin@nhea.ng'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '+2348100000000'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email and Voter.objects.filter(email=email).exists():
            raise ValidationError("This email address is already registered.")
        return email or None

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('initial_password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True, created_by=None):
        from .models import generate_voter_id
        voter = super().save(commit=False)
        voter.voter_id = generate_voter_id()
        voter.set_password(self.cleaned_data['initial_password'])
        voter.is_admin = True
        voter.is_staff = True
        voter.must_change_password = True
        voter.is_phone_verified = True   # admin accounts skip OTP verification
        voter.is_email_verified = True
        if created_by:
            voter.created_by = created_by
        if commit:
            voter.save()
        return voter


# ── Admin Password Change (post-login, forced) ────────────────────────────────

class AdminPasswordChangeForm(forms.Form):
    """
    Shown to admin users who have must_change_password=True.
    Requires current password for security.
    """
    current_password = forms.CharField(
        label="Current Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Your current / temporary password'}),
    )
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Choose a strong password'}),
        min_length=8,
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Repeat new password'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current = self.cleaned_data.get('current_password')
        if self.user and not self.user.check_password(current):
            raise ValidationError("Current password is incorrect.")
        return current

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password1')
        p2 = cleaned_data.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError("New passwords do not match.")
        return cleaned_data