from django.db import models
from cloudinary.models import CloudinaryField
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
import random
import string


def generate_voter_id():
    """Generate a unique NHEA voter ID like NHEA-2026-XXXXX"""
    from django.utils import timezone
    from django.db import OperationalError, ProgrammingError
    year = timezone.now().year
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    candidate = f"NHEA-{year}-{suffix}"
    try:
        while Voter.objects.filter(voter_id=candidate).exists():
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
            candidate = f"NHEA-{year}-{suffix}"
    except (OperationalError, ProgrammingError):
        pass
    return candidate


class Category(models.Model):
    """Award categories (e.g. Best Hospital of the Year)"""
    IMPORTANCE_CHOICES = [(i, str(i)) for i in range(1, 13)]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    importance = models.PositiveIntegerField(choices=IMPORTANCE_CHOICES, default=1)

    class Meta:
        verbose_name = "Award Category"
        verbose_name_plural = "Award Categories"

    def __str__(self):
        return self.name


class VoterManager(BaseUserManager):
    def create_user(self, voter_id, full_name, password=None):
        if not voter_id:
            raise ValueError('The Voter ID must be set')
        voter = self.model(voter_id=voter_id, full_name=full_name)
        voter.set_password(password)
        voter.save(using=self._db)
        return voter

    def create_superuser(self, voter_id, full_name, password=None):
        voter = self.create_user(voter_id=voter_id, full_name=full_name, password=password)
        voter.is_staff = True
        voter.is_superuser = True
        voter.save(using=self._db)
        return voter


class Voter(AbstractBaseUser):
    """A registered delegate/voter for the NHEA awards."""

    # ── Admin Permission Roles ───────────────────────────────────────────────
    ROLE_CHOICES = [
        ('voter_manager',    'Voter Manager'),       # register/delete voters
        ('nominee_manager',  'Nominee Manager'),     # add/remove nominees & categories
        ('results_viewer',   'Results Viewer'),      # view live results & analytics
        ('full_admin',       'Full Admin'),          # all of the above
    ]

    voter_id = models.CharField(max_length=100, unique=True, default=generate_voter_id)
    full_name = models.CharField(max_length=255)
    organization = models.CharField(max_length=255, blank=True, null=True)

    # ── Contact & Verification fields ───────────────────────────────────────
    email = models.EmailField(unique=True, blank=True, null=True)
    phone_number = models.CharField(
        max_length=20, unique=True, blank=True, null=True,
        help_text="International format, e.g. +2348100000000"
    )
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    # ── Admin role fields ────────────────────────────────────────────────────
    is_admin = models.BooleanField(default=False, help_text="Can manage election operations")
    admin_role = models.CharField(
        max_length=30, choices=ROLE_CHOICES, blank=True, null=True,
        help_text="Specific permission set assigned by superadmin"
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="Force password change on next login (set by superadmin)"
    )
    created_by = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_users',
        help_text="Superadmin who created this admin account"
    )
    date_joined = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    USERNAME_FIELD = 'voter_id'
    REQUIRED_FIELDS = ['full_name']

    objects = VoterManager()

    def __str__(self):
        return self.full_name

    @property
    def is_verified(self):
        """Voter is considered verified if phone OR email is verified."""
        return self.is_phone_verified or self.is_email_verified

    # ── Role-based permission helpers ────────────────────────────────────────

    def can_manage_voters(self):
        """Can register/delete voters."""
        if self.is_superuser:
            return True
        return self.admin_role in ('voter_manager', 'full_admin')

    def can_manage_nominees(self):
        """Can add/remove nominees and categories."""
        if self.is_superuser:
            return True
        return self.admin_role in ('nominee_manager', 'full_admin')

    def can_view_results(self):
        """Can view live results and analytics."""
        if self.is_superuser:
            return True
        return self.admin_role in ('results_viewer', 'full_admin')

    def can_reset_votes(self):
        """Only superadmin or full_admin can reset votes."""
        if self.is_superuser:
            return True
        return self.admin_role == 'full_admin'

    def get_role_display_name(self):
        if self.is_superuser:
            return 'Superadmin'
        for code, label in self.ROLE_CHOICES:
            if code == self.admin_role:
                return label
        return 'Admin'

    def has_voted_for_category(self, category):
        return Vote.objects.filter(voter=self, category=category).exists()

    def get_remaining_categories(self):
        voted_categories = Vote.objects.filter(voter=self).values_list('category_id', flat=True)
        return Category.objects.exclude(id__in=voted_categories).order_by('importance')

    def has_perm(self, perm, obj=None):
        return self.is_active and self.is_superuser

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label):
        return self.is_active and self.is_superuser


class Nominee(models.Model):
    """A nominee/contestant in an award category."""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='nominees')
    name = models.CharField(max_length=200)
    organization = models.CharField(max_length=255, blank=True, null=True)
    image = CloudinaryField('nominees', blank=True, null=True)

    def __str__(self):
        return f"{self.name} – {self.category.name}"


class Vote(models.Model):
    """A single vote cast by a voter for a nominee in a category."""
    voter = models.ForeignKey(Voter, on_delete=models.CASCADE, related_name='votes')
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    nominee = models.ForeignKey(Nominee, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    # ── Location tracking ────────────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['voter', 'category'], name='unique_vote_per_category')
        ]

    def __str__(self):
        return f"{self.voter.full_name} → {self.nominee.name} ({self.category.name})"

    @classmethod
    def validate_vote(cls, voter, category):
        return cls.objects.filter(voter=voter, category=category).exists()


# ── Activity Log ──────────────────────────────────────────────────────────────

class ActivityLog(models.Model):
    """Audit log for all important actions on the platform."""

    ACTION_CHOICES = [
        # Auth
        ('LOGIN',               'User Login'),
        ('LOGOUT',              'User Logout'),
        ('LOGIN_FAILED',        'Failed Login Attempt'),
        ('PASSWORD_CHANGE',     'Password Changed'),
        ('PASSWORD_RESET',      'Password Reset'),
        # Voting
        ('VOTE_CAST',           'Vote Cast'),
        ('VOTES_RESET',         'All Votes Reset'),
        # Admin / User management
        ('ADMIN_CREATED',       'Admin Account Created'),
        ('VOTER_CREATED',       'Voter Registered'),
        ('VOTER_DELETED',       'Voter Deleted'),
        # Category / Nominee
        ('CATEGORY_CREATED',    'Category Created'),
        ('CATEGORY_UPDATED',    'Category Updated'),
        ('CATEGORY_DELETED',    'Category Deleted'),
        ('NOMINEE_CREATED',     'Nominee Added'),
        ('NOMINEE_DELETED',     'Nominee Deleted'),
        # Verification
        ('PHONE_VERIFIED',      'Phone Verified'),
        ('EMAIL_VERIFIED',      'Email Verified'),
        # System
        ('ACCESS_CODE_USED',    'Access Code Used'),
        ('SYSTEM_UPDATE',       'System Update'),
    ]

    actor = models.ForeignKey(
        Voter, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='activity_logs',
        help_text="The user who performed this action (null = anonymous/system)"
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Network / location
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    user_agent = models.CharField(max_length=500, blank=True, null=True)

    # Optional target object info
    target_model = models.CharField(max_length=100, blank=True, null=True)
    target_id = models.CharField(max_length=100, blank=True, null=True)
    target_repr = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"

    def __str__(self):
        actor_name = self.actor.full_name if self.actor else "Anonymous"
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {actor_name} – {self.get_action_display()}"