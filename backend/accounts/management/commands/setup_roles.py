from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from kobo_integration.models import Record
from accounts.models import CustomUser

class Command(BaseCommand):
    help = 'Sets up default roles (Groups) and their permissions.'

    def handle(self, *args, **kwargs):
        # We need the ContentType for the Record and CustomUser models
        # to assign the correct permissions.
        try:
            record_ct = ContentType.objects.get_for_model(Record)
            user_ct = ContentType.objects.get_for_model(CustomUser)
        except ContentType.DoesNotExist:
            self.stdout.write(self.style.ERROR('Models not migrated yet! Please run migrations first.'))
            return

        # Fetch permissions for Record
        view_record, _ = Permission.objects.get_or_create(codename='view_record', content_type=record_ct)
        add_record, _ = Permission.objects.get_or_create(codename='add_record', content_type=record_ct)
        change_record, _ = Permission.objects.get_or_create(codename='change_record', content_type=record_ct)
        delete_record, _ = Permission.objects.get_or_create(codename='delete_record', content_type=record_ct)

        # Fetch permissions for User (so Admin can create users)
        view_user, _ = Permission.objects.get_or_create(codename='view_customuser', content_type=user_ct)
        add_user, _ = Permission.objects.get_or_create(codename='add_customuser', content_type=user_ct)
        change_user, _ = Permission.objects.get_or_create(codename='change_customuser', content_type=user_ct)
        delete_user, _ = Permission.objects.get_or_create(codename='delete_customuser', content_type=user_ct)

        # 1. Setup Coordinator Group
        coordinator_group, created = Group.objects.get_or_create(name='Coordinator')
        coordinator_group.permissions.add(view_record)
        self.stdout.write(self.style.SUCCESS(f"Coordinator group initialized with permissions."))

        # 2. Setup Clerk Group
        clerk_group, created = Group.objects.get_or_create(name='Clerk')
        clerk_group.permissions.add(view_record, add_record, change_record, delete_record)
        self.stdout.write(self.style.SUCCESS(f"Clerk group initialized with permissions."))

        # 3. Setup Admin Group
        # Admin can view, add, change, delete users, and manage records.
        admin_group, created = Group.objects.get_or_create(name='Admin')
        admin_group.permissions.add(
            view_user, add_user, change_user, delete_user,
            view_record, add_record, change_record, delete_record
        )
        self.stdout.write(self.style.SUCCESS(f"Admin group initialized with permissions."))

        self.stdout.write(self.style.SUCCESS('Successfully completed role setup!'))
