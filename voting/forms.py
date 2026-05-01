from django import forms
from django.core.exceptions import ValidationError
from .models import Category, Nominee, Voter, Vote


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


class SelfRegistrationForm(forms.ModelForm):
    """
    Public self-registration form — voter_id is auto-generated,
    so we only ask for name, organisation, and a password (× 2).
    """
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
        fields = ['full_name', 'organization']
        labels = {
            'full_name': 'Full Name',
            'organization': 'Organisation / Institution',
        }
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Your full name'}),
            'organization': forms.TextInput(attrs={'placeholder': 'Hospital, clinic, institution…'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        from .models import generate_voter_id
        voter = super().save(commit=False)
        voter.voter_id = generate_voter_id()
        voter.set_password(self.cleaned_data['password1'])
        if commit:
            voter.save()
        return voter


class VoterForm(forms.ModelForm):
    """Admin-side form — allows manually specifying voter_id."""
    class Meta:
        model = Voter
        fields = ['voter_id', 'full_name', 'organization', 'password']
        labels = {
            'voter_id': 'Voter ID',
            'full_name': 'Full Name',
            'organization': 'Organization / Institution',
        }
        widgets = {
            'password': forms.PasswordInput(),
        }