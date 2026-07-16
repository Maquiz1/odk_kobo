from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser
from django.contrib.auth.models import Group
from projects.models import Project


def _get_project_queryset(request_user):
    """
    Return the Project queryset visible to the given user:
    - Super Admin: all active projects
    - Admin: only projects they administer
    - Others: their own member projects (fallback)
    """
    if not request_user:
        return Project.objects.none()
    if request_user.is_superuser:
        return Project.objects.filter(is_active=True)
    if request_user.groups.filter(name='Admin').exists():
        return request_user.administered_projects.filter(is_active=True)
    return request_user.projects.filter(is_active=True)


class CustomUserCreationForm(UserCreationForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Assign Roles'
    )
    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.none(),   # overridden in __init__
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Assign Projects'
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'groups', 'projects')

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        # Role choices: Admins can only create Clerks/Coordinators
        if self.request_user and not self.request_user.is_superuser:
            self.fields['groups'].queryset = Group.objects.filter(name__in=['Clerk', 'Coordinator'])
        # Project choices scoped to what the requesting user administers
        self.fields['projects'].queryset = _get_project_queryset(self.request_user)


class CustomUserChangeForm(UserChangeForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Assign Roles'
    )
    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.none(),   # overridden in __init__
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Assign Projects'
    )

    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = ('username', 'email', 'groups', 'projects', 'is_active')

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        # Role choices: Admins can only assign Clerk/Coordinator
        if self.request_user and not self.request_user.is_superuser:
            self.fields['groups'].queryset = Group.objects.filter(name__in=['Clerk', 'Coordinator'])
        # Project choices scoped to what the requesting user administers
        self.fields['projects'].queryset = _get_project_queryset(self.request_user)
