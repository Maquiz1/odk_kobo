from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from .models import Record
from .forms import RecordForm


@login_required
@permission_required('kobo_integration.view_record', raise_exception=True)
def record_list(request):
    """
    List Kobo records.
    - Admins and Super users see ALL records.
    - Clerks and Coordinators see only records from their assigned projects.
    """
    query = request.GET.get('q', '')
    is_privileged = request.user.is_superuser or request.user.groups.filter(name='Admin').exists()

    if is_privileged:
        records = Record.objects.select_related('project').all().order_by('-created_at')
    else:
        user_projects = request.user.projects.all()
        records = Record.objects.select_related('project').filter(
            project__in=user_projects
        ).order_by('-created_at')

    if query:
        records = records.filter(kobo_id__icontains=query) | \
                  records.model.objects.filter(submitted_by__icontains=query).order_by('-created_at')

    return render(request, 'kobo_integration/record_list.html', {
        'records': records,
        'query': query,
        'title': 'Kobo Records',
    })


@login_required
@permission_required('kobo_integration.add_record', raise_exception=True)
def record_create(request):
    if request.method == 'POST':
        form = RecordForm(request.POST, request_user=request.user)
        if form.is_valid():
            form.save()
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
            form.save()
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
        record.delete()
        messages.success(request, f'Record "{kobo_id}" has been deleted.')
        return redirect('record_list')
    return render(request, 'kobo_integration/record_confirm_delete.html', {
        'record': record,
        'title': 'Confirm Delete',
    })
