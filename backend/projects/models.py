from django.db import models


class Project(models.Model):
    """
    Represents a data collection project (e.g. a Kobo form/survey).
    Records are scoped to a project, and users are assigned to projects.
    Super Admins assign Admins to projects via project_admins.
    Admins then register Clerks and Coordinators for their projects.
    """
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    kobo_asset_id = models.CharField(
        max_length=100,
        blank=True,
        help_text='The Kobo form asset ID used to match incoming webhook submissions.'
    )
    is_active = models.BooleanField(default=True)
    project_admins = models.ManyToManyField(
        'accounts.CustomUser',
        blank=True,
        related_name='administered_projects',
        limit_choices_to={'groups__name': 'Admin'},
        help_text='Admin users responsible for managing this project\'s users.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
