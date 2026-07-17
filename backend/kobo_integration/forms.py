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

    def clean(self):
        cleaned_data = super().clean()
        
        project = cleaned_data.get('project')
        if not project and self.instance:
            project = self.instance.project

        schema = project.schema_json if project else None
        if schema and isinstance(schema, dict) and schema.get('fields'):
            data_dict = {}
            for field in schema['fields']:
                f_name = field['name']
                form_key = f'kobo_field_{f_name}'
                if form_key in cleaned_data:
                    val = cleaned_data[form_key]
                    if field['type'] == 'select_multiple' and isinstance(val, list):
                        val = ' '.join(val)
                    data_dict[f_name] = val
            cleaned_data['data'] = data_dict
        else:
            # Fallback JSON parsing
            raw = cleaned_data.get('data', '')
            if isinstance(raw, str) and raw:
                try:
                    cleaned_data['data'] = json.loads(raw)
                except json.JSONDecodeError:
                    self.add_error('data', 'This field must contain valid JSON. Please check your input.')
            elif isinstance(raw, dict):
                cleaned_data['data'] = raw
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if 'data' in self.cleaned_data:
            instance.data = self.cleaned_data['data']
        if commit:
            instance.save()
        return instance

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit project choices to user's own projects (unless admin/superuser)
        if self.request_user and not self.request_user.is_superuser \
                and not self.request_user.groups.filter(name='Admin').exists():
            self.fields['project'].queryset = self.request_user.projects.filter(is_active=True)
        else:
            self.fields['project'].queryset = Project.objects.filter(is_active=True)

        # Determine if we have a project schema
        project = None
        if self.instance and getattr(self.instance, 'project_id', None):
            project = self.instance.project
        elif self.data and self.data.get('project'):
            try:
                project = Project.objects.get(pk=self.data.get('project'))
            except Project.DoesNotExist:
                pass
        elif self.initial and self.initial.get('project'):
            try:
                project = Project.objects.get(pk=self.initial.get('project'))
            except Project.DoesNotExist:
                pass

        self.project = project
        schema = project.schema_json if project else None
        if schema and isinstance(schema, dict) and schema.get('fields'):
            self.dynamic_fields_active = True
            if 'data' in self.fields:
                self.fields['data'].widget = forms.HiddenInput()
                self.fields['data'].required = False

            choices_dict = schema.get('choices', {})
            for field in schema['fields']:
                f_type = field['type']
                f_name = field['name']
                f_label = field.get('labels', {}).get('en') or field.get('label') or f_name
                f_help_text = field.get('hints', {}).get('en') or ""
                f_required_raw = field.get('required', False)
                f_required = str(f_required_raw).lower() in ['true', 'yes', '1']
                choice_list_name = field.get('choice_list', '')

                form_key = f'kobo_field_{f_name}'
                
                if f_type == 'select_one':
                    raw_choices = choices_dict.get(choice_list_name, [])
                    choices = [(c['name'], c.get('labels', {}).get('en') or c.get('label') or c['name']) for c in raw_choices]
                    if not f_required:
                        choices = [('', '---------')] + choices
                    self.fields[form_key] = forms.ChoiceField(
                        choices=choices,
                        required=f_required,
                        label=f_label,
                        help_text=f_help_text
                    )
                elif f_type == 'select_multiple':
                    raw_choices = choices_dict.get(choice_list_name, [])
                    choices = [(c['name'], c.get('labels', {}).get('en') or c.get('label') or c['name']) for c in raw_choices]
                    self.fields[form_key] = forms.MultipleChoiceField(
                        choices=choices,
                        required=f_required,
                        label=f_label,
                        widget=forms.CheckboxSelectMultiple,
                        help_text=f_help_text
                    )
                elif f_type == 'integer':
                    self.fields[form_key] = forms.IntegerField(
                        required=f_required,
                        label=f_label,
                        help_text=f_help_text
                    )
                elif f_type == 'decimal':
                    self.fields[form_key] = forms.DecimalField(
                        required=f_required,
                        label=f_label,
                        help_text=f_help_text
                    )
                elif f_type == 'date':
                    self.fields[form_key] = forms.DateField(
                        required=f_required,
                        label=f_label,
                        widget=forms.DateInput(attrs={'type': 'date'}),
                        help_text=f_help_text
                    )
                elif f_type == 'datetime':
                    self.fields[form_key] = forms.DateTimeField(
                        required=f_required,
                        label=f_label,
                        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
                        help_text=f_help_text
                    )
                else:
                    appearance = field.get('appearance', '')
                    widget = forms.Textarea(attrs={'rows': 3}) if appearance == 'multiline' else None
                    self.fields[form_key] = forms.CharField(
                        required=f_required,
                        label=f_label,
                        widget=widget,
                        help_text=f_help_text
                    )

            # Pre-populate dynamic fields if editing
            if self.instance and self.instance.pk and self.instance.data:
                for field in schema['fields']:
                    f_name = field['name']
                    form_key = f'kobo_field_{f_name}'
                    val = self.instance.data.get(f_name)
                    if val is not None:
                        if field['type'] == 'select_multiple' and isinstance(val, str):
                            val = val.split()
                        self.initial[form_key] = val
        else:
            self.dynamic_fields_active = False
            if self.instance and self.instance.pk and self.instance.data:
                self.initial['data'] = json.dumps(self.instance.data, indent=2)
