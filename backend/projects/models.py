import openpyxl
from django.db import models


def parse_xlsform(file_path):
    """
    Parses an ODK XLSForm (.xlsx) file and extracts survey fields, choices, and settings.
    """
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    except Exception as e:
        return {"error": f"Failed to load XLSForm workbook: {str(e)}"}

    schema = {"fields": [], "choices": {}, "settings": {}}

    # 0. Parse settings sheet (form_title, form_id, default_language, version)
    if 'settings' in wb.sheetnames:
        s_sheet = wb['settings']
        s_rows = list(s_sheet.iter_rows(values_only=True))
        if len(s_rows) >= 2:
            s_headers = [str(c).strip().lower() if c is not None else "" for c in s_rows[0]]
            s_values = s_rows[1]
            setting_keys = ('form_title', 'form_id', 'default_language', 'version')
            for key in setting_keys:
                if key in s_headers:
                    idx = s_headers.index(key)
                    val = s_values[idx] if idx < len(s_values) else None
                    schema['settings'][key] = str(val).strip() if val is not None else ""

    def get_lang(header_str):
        h = header_str.lower()
        if 'swahili' in h or '(sw)' in h or '::sw' in h:
            return 'sw'
        if 'english' in h or '(en)' in h or '::en' in h:
            return 'en'
        return 'en'

    # 1. Parse choices sheet
    if 'choices' in wb.sheetnames:
        sheet = wb['choices']
        rows = list(sheet.iter_rows(values_only=True))
        if rows:
            headers = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
            try:
                list_name_idx = headers.index('list_name')
                name_idx = headers.index('name')
            except ValueError:
                list_name_idx, name_idx = None, None

            label_cols = {}
            cf_choice_idx = None
            cf1_choice_idx = None  # cf1 is an alias used alongside cf in some forms
            for idx, h in enumerate(headers):
                if h == 'label' or h.startswith('label::') or h.startswith('label:'):
                    label_cols[get_lang(h)] = idx
                elif h == 'cf':
                    cf_choice_idx = idx
                elif h in ('cf1', 'cf2'):  # support both naming conventions
                    cf1_choice_idx = idx

            if list_name_idx is not None and name_idx is not None and label_cols:
                # Find the maximum index of required columns
                max_required_idx = max(list_name_idx, name_idx, *label_cols.values())
                for row in rows[1:]:
                    if not row or len(row) <= max_required_idx:
                        continue
                    list_name = str(row[list_name_idx]).strip() if row[list_name_idx] is not None else ""
                    val_name = str(row[name_idx]).strip() if row[name_idx] is not None else ""

                    if list_name and val_name:
                        labels = {}
                        for lang, idx in label_cols.items():
                            labels[lang] = str(row[idx]).strip() if row[idx] is not None else ""

                        if 'en' not in labels or not labels['en']:
                            labels['en'] = val_name
                        if 'sw' not in labels or not labels['sw']:
                            labels['sw'] = labels['en']

                        # Extract cf / cf1 (choice filter attributes) from choices sheet
                        cf_val = ""
                        if cf_choice_idx is not None and cf_choice_idx < len(row) and row[cf_choice_idx] is not None:
                            cf_val = str(row[cf_choice_idx]).strip()
                        cf1_val = ""
                        if cf1_choice_idx is not None and cf1_choice_idx < len(row) and row[cf1_choice_idx] is not None:
                            cf1_val = str(row[cf1_choice_idx]).strip()

                        if list_name not in schema['choices']:
                            schema['choices'][list_name] = []
                        schema['choices'][list_name].append({
                            "name": val_name,
                            "labels": labels,
                            "label": labels['en'],  # backward compatibility
                            "cf": cf_val,
                            "cf1": cf1_val
                        })

    # 2. Parse survey sheet
    if 'survey' in wb.sheetnames:
        sheet = wb['survey']
        rows = list(sheet.iter_rows(values_only=True))
        if rows:
            headers = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
            try:
                type_idx = headers.index('type')
                name_idx = headers.index('name')
            except ValueError:
                type_idx, name_idx = None, None

            label_cols = {}
            hint_cols = {}
            constraint_msg_cols = {}
            required_idx = None
            appearance_idx = None
            constraint_idx = None
            relevant_idx = None
            cf_idx = None
            cf2_idx = None

            for idx, h in enumerate(headers):
                if h == 'label' or h.startswith('label::') or h.startswith('label:'):
                    label_cols[get_lang(h)] = idx
                elif h == 'hint' or h.startswith('hint::') or h.startswith('hint:'):
                    hint_cols[get_lang(h)] = idx
                elif h == 'constraint_message' or h.startswith('constraint_message::') or h.startswith('constraint_message:'):
                    constraint_msg_cols[get_lang(h)] = idx
                elif h == 'required':
                    required_idx = idx
                elif h == 'appearance':
                    appearance_idx = idx
                elif h == 'constraint':
                    constraint_idx = idx
                elif h == 'relevant':
                    relevant_idx = idx
                elif h == 'cf':
                    cf_idx = idx
                elif h == 'cf2':
                    cf2_idx = idx

            if type_idx is not None and name_idx is not None:
                for row in rows[1:]:
                    if not row or len(row) <= max(type_idx, name_idx):
                        continue
                    f_type = str(row[type_idx]).strip() if row[type_idx] is not None else ""
                    f_name = str(row[name_idx]).strip() if row[name_idx] is not None else ""

                    if not f_name or f_type in ('start', 'end', 'today', 'deviceid', 'phonenumber', 'username', 'email', 'audit'):
                        continue

                    labels = {}
                    for lang, idx in label_cols.items():
                        labels[lang] = str(row[idx]).strip() if idx < len(row) and row[idx] is not None else ""
                    if 'en' not in labels or not labels['en']:
                        labels['en'] = f_name
                    if 'sw' not in labels or not labels['sw']:
                        labels['sw'] = labels['en']

                    hints = {}
                    for lang, idx in hint_cols.items():
                        hints[lang] = str(row[idx]).strip() if idx < len(row) and row[idx] is not None else ""
                    if 'en' not in hints or not hints['en']:
                        hints['en'] = ""
                    if 'sw' not in hints or not hints['sw']:
                        hints['sw'] = hints['en']

                    constraint_msgs = {}
                    for lang, idx in constraint_msg_cols.items():
                        constraint_msgs[lang] = str(row[idx]).strip() if idx < len(row) and row[idx] is not None else ""
                    if 'en' not in constraint_msgs or not constraint_msgs['en']:
                        constraint_msgs['en'] = ""
                    if 'sw' not in constraint_msgs or not constraint_msgs['sw']:
                        constraint_msgs['sw'] = constraint_msgs['en']

                    f_required = False
                    if required_idx is not None and required_idx < len(row) and row[required_idx] is not None:
                        val_req = str(row[required_idx]).strip().lower()
                        if val_req in ('yes', 'true', '1'):
                            f_required = True

                    f_appearance = ""
                    if appearance_idx is not None and appearance_idx < len(row) and row[appearance_idx] is not None:
                        f_appearance = str(row[appearance_idx]).strip()

                    f_constraint = ""
                    if constraint_idx is not None and constraint_idx < len(row) and row[constraint_idx] is not None:
                        f_constraint = str(row[constraint_idx]).strip()

                    f_relevant = ""
                    if relevant_idx is not None and relevant_idx < len(row) and row[relevant_idx] is not None:
                        f_relevant = str(row[relevant_idx]).strip()

                    f_cf = ""
                    if cf_idx is not None and cf_idx < len(row) and row[cf_idx] is not None:
                        f_cf = str(row[cf_idx]).strip()

                    f_cf2 = ""
                    if cf2_idx is not None and cf2_idx < len(row) and row[cf2_idx] is not None:
                        f_cf2 = str(row[cf2_idx]).strip()

                    choice_list = ""
                    clean_type = f_type
                    if f_type.startswith('select_one ') or f_type.startswith('select_multiple '):
                        parts = f_type.split(None, 1)
                        clean_type = parts[0]
                        choice_list = parts[1] if len(parts) > 1 else ""

                    schema['fields'].append({
                        "type": clean_type,
                        "name": f_name,
                        "label": labels['en'], # backward compatibility
                        "labels": labels,
                        "hints": hints,
                        "constraint_messages": constraint_msgs,
                        "choice_list": choice_list,
                        "required": f_required,
                        "appearance": f_appearance,
                        "constraint": f_constraint,
                        "relevant": f_relevant,
                        "cf": f_cf,
                        "cf2": f_cf2
                    })
    return schema


class Project(models.Model):
    """
    Represents a data collection project (e.g. a Kobo form/survey).
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
    
    # XLSForm details for dynamic rendering & schema translation
    xlsform = models.FileField(
        upload_to='xlsforms/',
        blank=True,
        null=True,
        help_text='Upload the XLSForm (.xlsx) file to enable dynamic forms and label translation.'
    )
    schema_json = models.JSONField(
        default=dict,
        blank=True,
        help_text='The parsed schema representation of the XLSForm.'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Detect if xlsform has changed or was newly uploaded
        is_new_file = False
        if self.pk:
            old_self = Project.objects.filter(pk=self.pk).first()
            if old_self and old_self.xlsform != self.xlsform:
                is_new_file = True
        else:
            if self.xlsform:
                is_new_file = True

        super().save(*args, **kwargs)

        # Parse file after standard save (so the file is written to storage)
        if is_new_file and self.xlsform:
            parsed = parse_xlsform(self.xlsform.path)
            # Update schema_json without triggers by calling update
            Project.objects.filter(pk=self.pk).update(schema_json=parsed)
            self.schema_json = parsed
