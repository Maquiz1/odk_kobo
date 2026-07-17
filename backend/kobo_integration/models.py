from django.db import models

class Record(models.Model):
    """
    Represents a submission from KoboToolbox.
    Records are scoped to a Project; users only see records for their projects.
    """
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='records',
        help_text='The project this submission belongs to.'
    )
    kobo_id = models.CharField(max_length=255, unique=True)
    uuid = models.CharField(max_length=255, blank=True, null=True)
    submitted_by = models.CharField(max_length=255, blank=True, null=True)
    
    # We store the raw form data in a JSON field for flexibility
    data = models.JSONField(default=dict)
    
    # Flag to support soft deletion (hides from UI but keeps in DB to prevent re-sync recreation)
    is_deleted = models.BooleanField(default=False)
    
    # Flag to protect local updates from being overwritten during Kobo syncs
    is_locally_updated = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Record {self.kobo_id} [{self.project}]"

    @property
    def patient_name(self):
        """Returns concatenated patient name from nested JSON keys."""
        fname = self.data.get('section_1_0/patient_fname', '') or self.data.get('patient_fname', '')
        mname = self.data.get('section_1_0/patient_mname', '') or self.data.get('patient_mname', '')
        lname = self.data.get('section_1_0/patient_lname', '') or self.data.get('patient_lname', '')
        full_name = f"{fname} {mname} {lname}".strip().replace('  ', ' ')
        return full_name if full_name else None

    @property
    def study_id(self):
        """Returns study_id from nested JSON keys."""
        return self.data.get('section_1_0/study_id') or self.data.get('study_id')

    @property
    def enumerator(self):
        """Returns enumerator from nested JSON keys."""
        return self.data.get('section_1_0/enumerator') or self.data.get('enumerator') or self.submitted_by

    def get_translated_data(self):
        """
        Returns a list of dicts: [{'name': ..., 'label': ..., 'value': ..., 'raw_value': ...}]
        translated using the project's XLSForm schema.
        """
        if not self.project or not self.project.schema_json:
            # Fallback to returning raw data sorted by key
            return [{'name': k, 'label': k, 'value': v, 'raw_value': v} for k, v in sorted(self.data.items())]

        schema = self.project.schema_json
        fields = schema.get('fields', [])
        choices_dict = schema.get('choices', {})

        translated = []
        seen_keys = set()

        for field in fields:
            f_name = field['name']
            f_label = field.get('labels', {}).get('en') or field.get('label') or f_name
            f_type = field['type']
            choice_list = field.get('choice_list', '')

            if f_name in self.data:
                val = self.data[f_name]
                seen_keys.add(f_name)

                # Translate choice value(s)
                translated_val = val
                if val is not None:
                    if f_type == 'select_one' and choice_list in choices_dict:
                        choices = choices_dict[choice_list]
                        match = next((c for c in choices if str(c['name']) == str(val)), None)
                        if match:
                            translated_val = match.get('labels', {}).get('en') or match.get('label') or val
                    elif f_type == 'select_multiple' and choice_list in choices_dict:
                        choices = choices_dict[choice_list]
                        if isinstance(val, str):
                            parts = val.split()
                        elif isinstance(val, list):
                            parts = val
                        else:
                            parts = [val]
                        
                        labels = []
                        for part in parts:
                            match = next((c for c in choices if str(c['name']) == str(part)), None)
                            labels.append(match.get('labels', {}).get('en') or match.get('label') if match else str(part))
                        translated_val = ', '.join(labels)

                translated.append({
                    'name': f_name,
                    'label': f_label,
                    'value': translated_val,
                    'raw_value': val
                })

        # Add any remaining keys in data that were not in the schema (metadata, etc.)
        for k, v in sorted(self.data.items()):
            if k not in seen_keys:
                # Skip common metadata keys that are already displayed in detail views
                if k in ('_id', '_uuid', '_submitted_by', '_submission_time', 'meta/instanceID', 'formhub/uuid'):
                    continue
                translated.append({
                    'name': k,
                    'label': k,
                    'value': v,
                    'raw_value': v
                })

        return translated
