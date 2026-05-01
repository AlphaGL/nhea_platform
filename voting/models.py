from django.db import models
from cloudinary.models import CloudinaryField
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
import random
import string


def generate_voter_id():
    """Generate a unique NHEA voter ID like NHEA-2026-XXXXX"""
    from django.utils import timezone
    year = timezone.now().year
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    candidate = f"NHEA-{year}-{suffix}"
    while Voter.objects.filter(voter_id=candidate).exists():
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        candidate = f"NHEA-{year}-{suffix}"
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
    voter_id = models.CharField(max_length=100, unique=True, default=generate_voter_id)
    full_name = models.CharField(max_length=255)
    organization = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    USERNAME_FIELD = 'voter_id'
    REQUIRED_FIELDS = ['full_name']

    objects = VoterManager()

    def __str__(self):
        return self.full_name

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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['voter', 'category'], name='unique_vote_per_category')
        ]

    def __str__(self):
        return f"{self.voter.full_name} → {self.nominee.name} ({self.category.name})"

    @classmethod
    def validate_vote(cls, voter, category):
        return cls.objects.filter(voter=voter, category=category).exists()