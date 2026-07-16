import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from django.core.management import call_command
from django.contrib.auth.models import Group
from accounts.models import CustomUser
from projects.models import Project
from kobo_integration.models import Record
from kobo_integration.forms import RecordForm


class KoboWebhookTests(TestCase):
    def setUp(self):
        # Create a mock project
        self.project = Project.objects.create(
            name="Test Project",
            kobo_asset_id="asset123",
            is_active=True
        )
        # Ensure setting has a token for testing
        settings.KOBO_WEBHOOK_TOKEN = "testsecrettoken"
        self.client = Client()

    def test_webhook_unauthorized(self):
        url = reverse('kobo_webhook')
        response = self.client.post(
            url,
            data=json.dumps({"_id": 12345}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Token wrongtoken"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(Record.objects.count(), 0)

    def test_webhook_authorized_and_creates_record(self):
        url = reverse('kobo_webhook')
        payload = {
            "_id": "99999",
            "_uuid": "abc-uuid-123",
            "_submitted_by": "surveyor_mike",
            "_xform_id_string": "asset123",
            "age": 28,
            "city": "Nairobi"
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION="Token testsecrettoken"
        )
        self.assertEqual(response.status_code, 201)
        
        # Verify database record
        self.assertEqual(Record.objects.count(), 1)
        record = Record.objects.first()
        self.assertEqual(record.kobo_id, "99999")
        self.assertEqual(record.uuid, "abc-uuid-123")
        self.assertEqual(record.submitted_by, "surveyor_mike")
        self.assertEqual(record.project, self.project)
        self.assertEqual(record.data["age"], 28)

    def test_webhook_no_matching_project(self):
        url = reverse('kobo_webhook')
        payload = {
            "_id": "88888",
            "_xform_id_string": "non_existent_asset_id",
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION="Token testsecrettoken"
        )
        self.assertEqual(response.status_code, 201)
        
        # Should create record with project=None
        record = Record.objects.get(kobo_id="88888")
        self.assertIsNone(record.project)


class RecordViewTests(TestCase):
    def setUp(self):
        # Setup roles and groups using the management command
        call_command('setup_roles')
        
        self.clerk_group = Group.objects.get(name='Clerk')
        self.admin_group = Group.objects.get(name='Admin')
        
        self.project1 = Project.objects.create(name="Project A", kobo_asset_id="kobo-asset-a", is_active=True)
        self.project2 = Project.objects.create(name="Project B", kobo_asset_id="kobo-asset-b", is_active=True)
        
        # Admin assigned to Project A
        self.admin_user = CustomUser.objects.create_user(username="admin_user", password="password123")
        self.admin_user.groups.add(self.admin_group)
        self.project1.project_admins.add(self.admin_user)
        self.project1.members.add(self.admin_user)
        
        # Clerk assigned to Project A
        self.clerk_user = CustomUser.objects.create_user(username="clerk_user", password="password123")
        self.clerk_user.groups.add(self.clerk_group)
        self.project1.members.add(self.clerk_user)

        # Records with nested data payloads
        self.record1 = Record.objects.create(
            kobo_id="kobo-id-alpha-99", 
            project=self.project1, 
            data={"first_name": "John", "address": {"city": "Boston"}}
        )
        self.record2 = Record.objects.create(
            kobo_id="kobo-id-beta-88", 
            project=self.project2, 
            data={"first_name": "Jane"}
        )
        
        self.client = Client()

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, f"/accounts/login/?next=/")

    def test_clerk_sees_only_assigned_project_records(self):
        self.client.login(username="clerk_user", password="password123")
        
        # Get record list
        response = self.client.get(reverse('record_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "kobo-id-alpha-99")
        self.assertNotContains(response, "kobo-id-beta-88")
        
        # Get record detail for assigned project
        detail_url = reverse('record_detail', kwargs={'pk': self.record1.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        
        # Accessing unassigned record detail should return 404
        unassigned_url = reverse('record_detail', kwargs={'pk': self.record2.pk})
        response = self.client.get(unassigned_url)
        self.assertEqual(response.status_code, 404)

    def test_csv_export_flattening(self):
        self.client.login(username="admin_user", password="password123")
        
        url = reverse('export_records_csv')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        
        content = response.content.decode('utf-8')
        lines = content.strip().split('\r\n')
        self.assertGreater(len(lines), 1)
        
        headers = lines[0].split(',')
        # Check that nested keys are flattened to columns
        self.assertIn('data/first_name', headers)
        self.assertIn('data/address/city', headers)
        
        # Content row matching record1
        row1 = None
        for line in lines[1:]:
            parts = line.split(',')
            if 'kobo-id-alpha-99' in parts:
                row1 = parts
                break
        self.assertIsNotNone(row1)
        self.assertIn('John', row1)
        self.assertIn('Boston', row1)

    @patch('kobo_integration.views.requests.get')
    def test_kobo_manual_sync(self, mock_get):
        self.client.login(username="admin_user", password="password123")
        
        # Mock successful Kobo API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "_id": "kobo-synced-11",
                "_uuid": "synced-uuid-11",
                "_submitted_by": "surveyor_tim",
                "survey_data": "value"
            }
        ]
        mock_get.return_value = mock_response
        
        # Access sync post
        url = reverse('kobo_sync', kwargs={'project_id': self.project1.pk})
        response = self.client.post(url, {
            'api_url': 'https://kf.kobotoolbox.org/api/v2/',
            'api_token': 'mysecretapitoken'
        })
        self.assertRedirects(response, reverse('record_list'))
        
        # Check record imported
        self.assertEqual(Record.objects.filter(kobo_id="kobo-synced-11").count(), 1)
        rec = Record.objects.get(kobo_id="kobo-synced-11")
        self.assertEqual(rec.project, self.project1)
        self.assertEqual(rec.submitted_by, "surveyor_tim")


class DynamicFormTranslationTests(TestCase):
    def setUp(self):
        call_command('setup_roles')
        self.admin_group = Group.objects.get(name='Admin')
        self.admin_user = CustomUser.objects.create_user(username="admin", password="password123")
        self.admin_user.groups.add(self.admin_group)

        self.schema = {
            "fields": [
                {
                    "type": "select_one",
                    "name": "gender",
                    "label": "Gender of respondent",
                    "labels": {"en": "Gender of respondent", "sw": "Jinsia ya mhojiwa"},
                    "hints": {"en": "Select gender", "sw": "Chagua jinsia"},
                    "choice_list": "genders",
                    "required": True,
                    "appearance": "minimal"
                },
                {
                    "type": "select_multiple",
                    "name": "hobbies",
                    "label": "Respondent hobbies",
                    "labels": {"en": "Respondent hobbies", "sw": "Hobby za mhojiwa"},
                    "hints": {"en": "Choose multiple", "sw": "Chagua nyingi"},
                    "choice_list": "hobby_list",
                    "required": False
                },
                {
                    "type": "integer",
                    "name": "age",
                    "label": "Age",
                    "labels": {"en": "Age", "sw": "Umri"},
                    "required": False
                }
            ],
            "choices": {
                "genders": [
                    {"name": "m", "label": "Male", "labels": {"en": "Male", "sw": "Mwanaume"}},
                    {"name": "f", "label": "Female", "labels": {"en": "Female", "sw": "Mwanamke"}}
                ],
                "hobby_list": [
                    {"name": "read", "label": "Reading Books", "labels": {"en": "Reading Books", "sw": "Kusoma vitabu"}},
                    {"name": "swim", "label": "Swimming", "labels": {"en": "Swimming", "sw": "Kuogelea"}},
                    {"name": "run", "label": "Running", "labels": {"en": "Running", "sw": "Kukimbia"}}
                ]
            }
        }
        self.project = Project.objects.create(
            name="Dynamic Schema Project",
            schema_json=self.schema,
            is_active=True
        )
        self.project.project_admins.add(self.admin_user)
        self.project.members.add(self.admin_user)

        self.record = Record.objects.create(
            kobo_id="kobo-123",
            project=self.project,
            data={
                "gender": "f",
                "hobbies": "read run",
                "age": 30,
                "unlisted_metadata": "some_value"
            }
        )
        self.client = Client()

    def test_record_get_translated_data(self):
        translated = self.record.get_translated_data()
        
        # We expect fields to be ordered: gender, hobbies, age, and unlisted_metadata
        self.assertEqual(len(translated), 4)

        # gender
        self.assertEqual(translated[0]['name'], 'gender')
        self.assertEqual(translated[0]['label'], 'Gender of respondent')
        self.assertEqual(translated[0]['value'], 'Female')
        self.assertEqual(translated[0]['raw_value'], 'f')

        # hobbies
        self.assertEqual(translated[1]['name'], 'hobbies')
        self.assertEqual(translated[1]['label'], 'Respondent hobbies')
        self.assertEqual(translated[1]['value'], 'Reading Books, Running')
        self.assertEqual(translated[1]['raw_value'], 'read run')

        # age
        self.assertEqual(translated[2]['name'], 'age')
        self.assertEqual(translated[2]['label'], 'Age')
        self.assertEqual(translated[2]['value'], 30)

        # unlisted metadata
        self.assertEqual(translated[3]['name'], 'unlisted_metadata')
        self.assertEqual(translated[3]['label'], 'unlisted_metadata')
        self.assertEqual(translated[3]['value'], 'some_value')

    def test_record_form_dynamic_generation_and_load(self):
        form = RecordForm(instance=self.record, request_user=self.admin_user)
        from django import forms as django_forms
        self.assertIsInstance(form.fields['data'].widget, django_forms.HiddenInput)
        self.assertIn('kobo_field_gender', form.fields)
        self.assertIn('kobo_field_hobbies', form.fields)
        self.assertIn('kobo_field_age', form.fields)

        gender_choices = form.fields['kobo_field_gender'].choices
        self.assertEqual(gender_choices, [('m', 'Male'), ('f', 'Female')])
        
        self.assertEqual(form.initial['kobo_field_gender'], 'f')
        self.assertEqual(form.initial['kobo_field_hobbies'], ['read', 'run'])
        self.assertEqual(form.initial['kobo_field_age'], 30)

    def test_record_form_validation_and_saving(self):
        post_data = {
            'project': self.project.pk,
            'kobo_id': 'kobo-unique-456',
            'kobo_field_gender': 'm',
            'kobo_field_hobbies': ['swim', 'run'],
            'kobo_field_age': 25
        }
        form = RecordForm(data=post_data, request_user=self.admin_user)
        self.assertTrue(form.is_valid(), form.errors)
        
        record = form.save()
        self.assertEqual(record.kobo_id, 'kobo-unique-456')
        self.assertEqual(record.data['gender'], 'm')
        self.assertEqual(record.data['hobbies'], 'swim run')
        self.assertEqual(record.data['age'], 25)

    def test_csv_export_label_translation(self):
        self.client.login(username="admin", password="password123")
        url = reverse('export_records_csv')
        
        response = self.client.get(f"{url}?project={self.project.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        content = response.content.decode('utf-8')
        import csv
        import io
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        self.assertGreater(len(rows), 1)

        headers = rows[0]
        self.assertIn('Gender of respondent', headers)
        self.assertIn('Respondent hobbies', headers)
        self.assertIn('Age', headers)

        row = rows[1]
        row_dict = dict(zip(headers, row))
        
        self.assertEqual(row_dict['Gender of respondent'], 'Female')
        self.assertEqual(row_dict['Respondent hobbies'], 'Reading Books, Running')
        self.assertEqual(row_dict['Age'], '30')

