from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """
    Custom user model. Extend this with any additional fields needed.
    Uses Django Groups for role-based access control (Clerk, Coordinator, Admin).
    Users can be assigned to multiple projects.
    """
    projects = models.ManyToManyField(
        'projects.Project',
        blank=True,
        related_name='members',
        help_text='Projects this user has access to.'
    )

    def __str__(self):
        return self.username
