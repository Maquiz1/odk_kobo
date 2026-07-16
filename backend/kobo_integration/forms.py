from django import forms
from .models import Record
from projects.models import Project
import json


class RecordForm(forms.ModelForm):
    """
    Form for Clerks to manually add or edit a Kobo submission record.
    The project dropdown is limited to the requesting user's assigned projects.
    """
    data = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 8,
            'placeholder': '{\n  "question_1": "answer",\n  "question_2": "answer"\n}'
        }),
        help_text='Enter the form submission data as valid JSON.',
        label='Submission Data (JSON)'
    )

    class Meta:
        model = Record
        fields = ('project', 'kobo_id', 'uuid', 'submitted_by', 'data')
        labels = {
            'project': 'Project',
            'kobo_id': 'Kobo Submission ID',
            'uuid': 'UUID',
            'submitted_by': 'Submitted By',
        }

    def clean_data(self):
        raw = self.cleaned_data.get('data', '')
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise forms.ValidationError('This field must contain valid JSON. Please check your input.')

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        # Pre-populate textarea with pretty-printed JSON on edit
        if self.instance and self.instance.pk and self.instance.data:
            self.initial['data'] = json.dumps(self.instance.data, indent=2)
        # Limit project choices to user's own projects (unless admin/superuser)
        if self.request_user and not self.request_user.is_superuser \
                and not self.request_user.groups.filter(name='Admin').exists():
            self.fields['project'].queryset = self.request_user.projects.filter(is_active=True)
        else:
            self.fields['project'].queryset = Project.objects.filter(is_active=True)
