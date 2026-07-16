from django import forms
from .models import Project


class ProjectForm(forms.ModelForm):
    """
    Form for Super Admin to create/edit projects and assign Admins.
    The project_admins field is only shown to Super Admins.
    """
    class Meta:
        model = Project
        fields = ('name', 'description', 'kobo_asset_id', 'is_active', 'project_admins')
        labels = {
            'name': 'Project Name',
            'description': 'Description',
            'kobo_asset_id': 'Kobo Asset ID',
            'is_active': 'Active',
            'project_admins': 'Assign Project Admins',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'project_admins': forms.CheckboxSelectMultiple(),
        }
        help_texts = {
            'project_admins': 'Select Admin users who will manage this project\'s Clerks and Coordinators.',
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        # Only Super Admins can assign project admins
        if self.request_user and not self.request_user.is_superuser:
            self.fields.pop('project_admins', None)
