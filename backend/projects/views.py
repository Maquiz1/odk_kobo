from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Project
from .forms import ProjectForm


def is_superuser(user):
    return user.is_superuser


def is_admin_or_super(user):
    """Admin group members and superusers can access project management."""
    return user.is_superuser or user.groups.filter(name='Admin').exists()


def get_user_projects(user):
    """
    Return the projects this user can manage:
    - Super Admin: all projects
    - Admin: only projects where they are listed as a project_admin
    """
    if user.is_superuser:
        return Project.objects.all()
    return user.administered_projects.all()


@login_required
def project_list(request):
    if not is_admin_or_super(request.user):
        messages.error(request, 'You do not have permission to manage projects.')
        return redirect('record_list')
    projects = get_user_projects(request.user)
    return render(request, 'projects/project_list.html', {
        'projects': projects,
        'title': 'Projects',
    })


@login_required
def project_create(request):
    if not is_superuser(request.user):
        messages.error(request, 'Only Super Admins can create new projects.')
        return redirect('project_list')
    if request.method == 'POST':
        form = ProjectForm(request.POST, request_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project created successfully!')
            return redirect('project_list')
    else:
        form = ProjectForm(request_user=request.user)
    return render(request, 'projects/project_form.html', {
        'form': form,
        'title': 'Add New Project',
    })


@login_required
def project_update(request, pk):
    if not is_admin_or_super(request.user):
        messages.error(request, 'You do not have permission to edit projects.')
        return redirect('record_list')

    # Admins can only edit projects they administer
    allowed = get_user_projects(request.user)
    project = get_object_or_404(allowed, pk=pk)

    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project, request_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Project "{project.name}" updated!')
            return redirect('project_list')
    else:
        form = ProjectForm(instance=project, request_user=request.user)
    return render(request, 'projects/project_form.html', {
        'form': form,
        'title': f'Edit Project: {project.name}',
        'project': project,
    })


@login_required
def project_delete(request, pk):
    if not is_superuser(request.user):
        messages.error(request, 'Only Super Admins can delete projects.')
        return redirect('project_list')
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        name = project.name
        project.delete()
        messages.success(request, f'Project "{name}" deleted.')
        return redirect('project_list')
    return render(request, 'projects/project_confirm_delete.html', {
        'project': project,
        'title': 'Confirm Delete Project',
    })
