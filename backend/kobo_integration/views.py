import csv
import requests
from django.conf import settings as django_settings
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q
from .models import Record
from .forms import RecordForm
from projects.models import Project
from accounts.models import CustomUser


def _base_record_qs(user):
    """Return the base queryset of records visible to this user, excluding deleted ones."""
    is_privileged = user.is_superuser or user.groups.filter(name='Admin').exists()
    qs = Record.objects.select_related('project').filter(is_deleted=False)
    if not is_privileged:
        qs = qs.filter(project__in=user.projects.all())
    return qs


def _flatten_dict(d, parent_key='', sep='/'):
    """Helper to recursively flatten nested dictionaries."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


@login_required
def dashboard(request):
    """Home dashboard with summary stats."""
    record_qs = _base_record_qs(request.user)
    is_privileged = request.user.is_superuser or request.user.groups.filter(name='Admin').exists()

    context = {
        'title': 'Dashboard',
        'total_records': record_qs.count(),
        'recent_records': record_qs.order_by('-created_at')[:5],
        'total_projects': Project.objects.filter(is_active=True).count() if is_privileged
                          else request.user.projects.filter(is_active=True).count(),
        'total_users': CustomUser.objects.count() if request.user.is_superuser else None,
        'projects_with_counts': (
            Project.objects.filter(is_active=True) if is_privileged
            else request.user.projects.filter(is_active=True)
        ),
    }
    return render(request, 'kobo_integration/dashboard.html', context)


@login_required
@permission_required('kobo_integration.view_record', raise_exception=True)
def record_list(request):
    """List records with search, advanced filter, and pagination support."""
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    query = request.GET.get('q', '').strip()
    project_filter = request.GET.get('project', '').strip()
    enumerator_filter = request.GET.get('enumerator', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    records = _base_record_qs(request.user).order_by('-created_at')

    # Advanced Q Search across main fields and JSON data keys
    if query:
        records = records.filter(
            Q(kobo_id__icontains=query) |
            Q(uuid__icontains=query) |
            Q(submitted_by__icontains=query) |
            Q(data__patient_fname__icontains=query) |
            Q(data__patient_mname__icontains=query) |
            Q(data__patient_lname__icontains=query) |
            Q(data__study_id__icontains=query) |
            Q(data__today__icontains=query) |
            Q(data__enumerator__icontains=query)
        )

    if project_filter:
        records = records.filter(project__id=project_filter)

    if enumerator_filter:
        records = records.filter(
            Q(data__enumerator=enumerator_filter) | Q(submitted_by=enumerator_filter)
        )

    # Date range filters on 'today' field inside Kobo data (string 'YYYY-MM-DD')
    if date_from:
        records = records.filter(data__today__gte=date_from)
    if date_to:
        records = records.filter(data__today__lte=date_to)

    # Fetch unique enumerators for the filter dropdown
    all_records = _base_record_qs(request.user)
    enumerators = set()
    for r in all_records:
        enum_val = r.data.get('enumerator') or r.submitted_by
        if enum_val:
            enumerators.add(enum_val)
    enumerators = sorted(list(enumerators))

    # Projects for filter dropdown
    is_privileged = request.user.is_superuser or request.user.groups.filter(name='Admin').exists()
    projects = Project.objects.filter(is_active=True) if is_privileged else request.user.projects.filter(is_active=True)

    # Pagination: 10 records per page
    paginator = Paginator(records, 10)
    page = request.GET.get('page')
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return render(request, 'kobo_integration/record_list.html', {
        'page_obj': page_obj,
        'records': page_obj.object_list,
        'query': query,
        'project_filter': project_filter,
        'enumerator_filter': enumerator_filter,
        'date_from': date_from,
        'date_to': date_to,
        'projects': projects,
        'enumerators': enumerators,
        'title': 'Kobo Records',
    })



@login_required
@permission_required('kobo_integration.view_record', raise_exception=True)
def record_detail(request, pk):
    """Show full details of a single Record."""
    record = get_object_or_404(_base_record_qs(request.user), pk=pk)
    data_items = record.get_translated_data()
    return render(request, 'kobo_integration/record_detail.html', {
        'record': record,
        'data_items': data_items,
        'title': f'Record: {record.kobo_id}',
    })


@login_required
@permission_required('kobo_integration.view_record', raise_exception=True)
def export_records_csv(request):
    """Export the currently filtered record list as a flattened CSV."""
    query = request.GET.get('q', '').strip()
    project_filter = request.GET.get('project', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    records = _base_record_qs(request.user).order_by('-created_at')

    if query:
        records = records.filter(
            Q(kobo_id__icontains=query) | Q(submitted_by__icontains=query)
        )
    if project_filter:
        records = records.filter(project__id=project_filter)
    if date_from:
        records = records.filter(created_at__date__gte=date_from)
    if date_to:
        records = records.filter(created_at__date__lte=date_to)

    # Compile all records to lists of dictionaries
    flat_records = []
    seen_labels = set()

    for rec in records:
        # Standard columns
        rec_dict = {
            'Kobo ID': rec.kobo_id,
            'UUID': rec.uuid or '',
            'Project': rec.project.name if rec.project else '',
            'Submitted By': rec.submitted_by or '',
            'Created At': rec.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        # Translate this record's fields if schema exists, otherwise fallback to flattening
        if rec.project and rec.project.schema_json and 'fields' in rec.project.schema_json:
            translated_fields = rec.get_translated_data()
            for field in translated_fields:
                col_label = field['label']
                rec_dict[col_label] = field['value']
                seen_labels.add(col_label)
        else:
            if isinstance(rec.data, dict):
                flat_data = _flatten_dict(rec.data)
                for k, v in flat_data.items():
                    col_name = f"data/{k}"
                    rec_dict[col_name] = v
                    seen_labels.add(col_name)

        flat_records.append(rec_dict)

    # Order the dynamic headers nicely
    # If we filtered by a specific project, we can order headers exactly as in the project's schema!
    dynamic_headers = []
    if project_filter:
        try:
            proj = Project.objects.get(pk=project_filter)
            if proj.schema_json and 'fields' in proj.schema_json:
                for field in proj.schema_json['fields']:
                    lbl = field.get('label') or field['name']
                    if lbl in seen_labels:
                        dynamic_headers.append(lbl)
        except Project.DoesNotExist:
            pass

    # For any remaining labels not added by the project's schema (or if no project_filter was selected)
    for lbl in sorted(list(seen_labels)):
        if lbl not in dynamic_headers:
            dynamic_headers.append(lbl)

    headers = ['Kobo ID', 'UUID', 'Project', 'Submitted By', 'Created At'] + dynamic_headers

    # Generate CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="kobo_records_export.csv"'

    writer = csv.DictWriter(response, fieldnames=headers)
    writer.writeheader()
    for row in flat_records:
        writer.writerow(row)

    return response


@login_required
def kobo_sync(request, project_id):
    """
    Manually pull submissions from Kobo API.
    Authorized: Super Admins or the Project's assigned Project Admins.
    """
    project = get_object_or_404(Project, pk=project_id, is_active=True)

    # Authorization Check
    is_authorized = request.user.is_superuser or project.project_admins.filter(pk=request.user.pk).exists()
    if not is_authorized:
        messages.error(request, 'You do not have permission to sync this project.')
        return redirect('project_list')

    if not project.kobo_asset_id:
        messages.error(request, 'This project does not have a Kobo Asset ID configured.')
        return redirect('project_list')

    if request.method == 'POST':
        api_url = request.POST.get('api_url', '').strip()
        api_token = request.POST.get('api_token', '').strip()

        if not api_url.endswith('/'):
            api_url += '/'

        # Construct final Kobo submissions endpoint (uses /data/ in modern Kobo API v2)
        submissions_url = f"{api_url}assets/{project.kobo_asset_id}/data/?format=json"
        headers = {'Authorization': f'Token {api_token}'}

        submissions = []
        next_url = submissions_url

        try:
            while next_url:
                response = requests.get(next_url, headers=headers, timeout=30)
                if response.status_code != 200:
                    messages.error(request, f'Kobo API Error (Status {response.status_code}): {response.text[:200]}')
                    return render(request, 'kobo_integration/kobo_sync.html', {'project': project})

                data = response.json()
                if isinstance(data, list):
                    submissions.extend(data)
                    next_url = None
                elif isinstance(data, dict) and 'results' in data:
                    submissions.extend(data['results'])
                    next_url = data.get('next')  # Follow next page URL
                else:
                    messages.error(request, 'Unexpected data structure returned from Kobo API.')
                    return render(request, 'kobo_integration/kobo_sync.html', {'project': project})

            created_count = 0
            updated_count = 0

            for payload in submissions:
                kobo_id = payload.get('_id') or payload.get('formhub/uuid') or payload.get('_uuid')
                uuid = payload.get('_uuid', '')
                submitted_by = payload.get('_submitted_by', '')

                if not kobo_id:
                    continue

                # Check if record already exists to respect local modifications and deletions
                existing_record = Record.objects.filter(kobo_id=str(kobo_id)).first()
                if existing_record:
                    if existing_record.is_deleted or existing_record.is_locally_updated:
                        # Skip overwriting this record to preserve local updates/deletes
                        continue
                    
                    # Update non-locally-modified record
                    existing_record.uuid = uuid
                    existing_record.submitted_by = submitted_by
                    existing_record.data = payload
                    existing_record.project = project
                    existing_record.save()
                    updated_count += 1
                else:
                    # Create new record
                    Record.objects.create(
                        kobo_id=str(kobo_id),
                        uuid=uuid,
                        submitted_by=submitted_by,
                        data=payload,
                        project=project
                    )
                    created_count += 1

            messages.success(
                request,
                f'Synchronization complete! Imported {created_count} new records and updated {updated_count} existing records.'
            )
            return redirect('record_list')

        except requests.exceptions.RequestException as e:
            messages.error(request, f'Network error connecting to Kobo: {str(e)}')

    return render(request, 'kobo_integration/kobo_sync.html', {'project': project})


@login_required
def register_kobo_webhook(request, project_id):
    """
    Allows Admins/Super-admins to register or delete a KoboToolbox REST Service
    (webhook) for a project programmatically via the Kobo API.
    """
    project = get_object_or_404(Project, pk=project_id, is_active=True)

    # Authorization: only superusers or this project's admins
    is_authorized = request.user.is_superuser or project.project_admins.filter(pk=request.user.pk).exists()
    if not is_authorized:
        messages.error(request, 'You do not have permission to manage webhooks for this project.')
        return redirect('project_list')

    if not project.kobo_asset_id:
        messages.error(request, 'This project does not have a Kobo Asset ID configured.')
        return redirect('project_list')

    # Build the default webhook URL pointing to our endpoint
    webhook_url = f"{django_settings.SITE_URL}/webhook/kobo/"
    kobo_webhook_token = django_settings.KOBO_WEBHOOK_TOKEN

    hooks = []
    fetch_error = None

    def _kobo_hooks_url(api_base, asset_id):
        base = api_base.rstrip('/')
        return f"{base}/assets/{asset_id}/hooks/"

    if request.method == 'POST':
        api_url = request.POST.get('api_url', '').strip().rstrip('/') + '/'
        api_token = request.POST.get('api_token', '').strip()
        action = request.POST.get('action', 'register')
        hook_uid = request.POST.get('hook_uid', '').strip()

        kobo_headers = {
            'Authorization': f'Token {api_token}',
            'Content-Type': 'application/json',
        }
        hooks_url = _kobo_hooks_url(api_url, project.kobo_asset_id)

        if action == 'delete' and hook_uid:
            # --- Delete an existing hook ---
            delete_url = f"{hooks_url}{hook_uid}/"
            try:
                resp = requests.delete(delete_url, headers=kobo_headers, timeout=15)
                if resp.status_code == 204:
                    messages.success(request, f'Webhook "{hook_uid}" has been deleted from KoboToolbox.')
                else:
                    messages.error(request, f'Failed to delete webhook (Status {resp.status_code}): {resp.text[:200]}')
            except requests.exceptions.RequestException as e:
                messages.error(request, f'Network error: {str(e)}')
            return redirect('register_kobo_webhook', project_id=project.pk)

        else:
            # --- Register a new hook ---
            payload = {
                "name": f"ODK App — {project.name}",
                "endpoint": webhook_url,
                "active": True,
                "subset_fields": [],
                "email_notification": True,
                "export_type": "json",
                "auth_level": "no_auth",
                "settings": {
                    "custom_headers": {
                        "Authorization": f"Token {kobo_webhook_token}"
                    }
                }
            }
            try:
                resp = requests.post(hooks_url, json=payload, headers=kobo_headers, timeout=15)
                if resp.status_code in (200, 201):
                    hook_data = resp.json()
                    messages.success(
                        request,
                        f'Webhook registered successfully! Hook UID: {hook_data.get("uid", "—")}. '
                        f'KoboToolbox will now POST submissions to: {webhook_url}'
                    )
                elif resp.status_code == 400:
                    # Often means already registered — show the error body
                    messages.warning(request, f'KoboToolbox returned 400: {resp.text[:300]}')
                else:
                    messages.error(request, f'Kobo API Error (Status {resp.status_code}): {resp.text[:200]}')
            except requests.exceptions.RequestException as e:
                messages.error(request, f'Network error connecting to Kobo: {str(e)}')

            # After register, list existing hooks so user can see current state
            try:
                list_resp = requests.get(hooks_url, headers=kobo_headers, timeout=15)
                if list_resp.status_code == 200:
                    data = list_resp.json()
                    hooks = data.get('results', data) if isinstance(data, dict) else data
            except Exception:
                pass

            return render(request, 'kobo_integration/kobo_webhook_register.html', {
                'project': project,
                'hooks': hooks,
                'webhook_url': webhook_url,
                'api_url': api_url,
                # Don't echo the token back for security
            })

    # GET — optionally pre-load hooks if token is in session (we don't store it, so just show empty)
    return render(request, 'kobo_integration/kobo_webhook_register.html', {
        'project': project,
        'hooks': hooks,
        'fetch_error': fetch_error,
        'webhook_url': webhook_url,
        'api_url': 'https://kf.kobotoolbox.org/api/v2/',
    })


@login_required
@permission_required('kobo_integration.add_record', raise_exception=True)
def record_create(request):
    if request.method == 'POST':
        form = RecordForm(request.POST, request_user=request.user)
        if form.is_valid():
            record = form.save(commit=False)
            record.is_locally_updated = True  # Flag to prevent sync overwrites
            record.save()
            messages.success(request, 'Record created successfully!')
            return redirect('record_list')
    else:
        form = RecordForm(request_user=request.user)
    return render(request, 'kobo_integration/record_form.html', {
        'form': form,
        'title': 'Add New Record',
    })


@login_required
@permission_required('kobo_integration.change_record', raise_exception=True)
def record_update(request, pk):
    record = get_object_or_404(Record, pk=pk)
    if request.method == 'POST':
        form = RecordForm(request.POST, instance=record, request_user=request.user)
        if form.is_valid():
            record = form.save(commit=False)
            record.is_locally_updated = True  # Flag to prevent sync overwrites
            record.save()
            messages.success(request, f'Record "{record.kobo_id}" updated successfully!')
            return redirect('record_list')
    else:
        form = RecordForm(instance=record, request_user=request.user)
    return render(request, 'kobo_integration/record_form.html', {
        'form': form,
        'title': f'Edit Record: {record.kobo_id}',
        'record': record,
    })


@login_required
@permission_required('kobo_integration.delete_record', raise_exception=True)
def record_delete(request, pk):
    record = get_object_or_404(Record, pk=pk)
    if request.method == 'POST':
        kobo_id = record.kobo_id
        record.is_deleted = True  # Soft delete
        record.save()
        messages.success(request, f'Record "{kobo_id}" has been deleted.')
        return redirect('record_list')
    return render(request, 'kobo_integration/record_confirm_delete.html', {
        'record': record,
        'title': 'Confirm Delete',
    })
