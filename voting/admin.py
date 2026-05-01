from django.contrib import admin
from .models import Voter, Category, Nominee, Vote


class VoterAdmin(admin.ModelAdmin):
    model = Voter
    list_display = ('voter_id', 'full_name', 'organization')
    search_fields = ('voter_id', 'full_name', 'organization')
    ordering = ('voter_id',)
    filter_horizontal = ()
    list_filter = ()
    fieldsets = ()


admin.site.register(Voter, VoterAdmin)
admin.site.register(Category)
admin.site.register(Nominee)
admin.site.register(Vote)