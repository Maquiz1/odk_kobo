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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Record {self.kobo_id} [{self.project}]"

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
