from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser


def _get_visible_users(request_user):
    """
    Return users visible to the current user based on their role:
    - Super Admin: all users
    - Admin: users who are members of the Admin's administered projects
    - Others: only themselves (shouldn't reach this view normally)
    """
    if request_user.is_superuser:
        return CustomUser.objects.all().order_by('-date_joined')
    if request_user.groups.filter(name='Admin').exists():
        # Get all projects this admin administers, then get all member users
        administered = request_user.administered_projects.all()
        return CustomUser.objects.filter(
            projects__in=administered
        ).distinct().order_by('-date_joined')
    # Fallback: only self
    return CustomUser.objects.filter(pk=request_user.pk)


@login_required
@permission_required('accounts.view_customuser', raise_exception=True)
def user_list(request):
    users = _get_visible_users(request.user)
    return render(request, 'accounts/user_list.html', {
        'users': users,
        'title': 'User Management',
    })


@login_required
@permission_required('accounts.add_customuser', raise_exception=True)
def user_create(request):
    # Admins must administer at least one project before they can add users
    if not request.user.is_superuser:
        if not request.user.administered_projects.filter(is_active=True).exists():
            messages.error(
                request,
                'You are not assigned as an admin to any active project yet. '
                'Please ask a Super Admin to assign you to a project first.'
            )
            return redirect('user_list')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'User created successfully!')
            return redirect('user_list')
    else:
        form = CustomUserCreationForm(request_user=request.user)
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': 'Create New User',
    })


@login_required
@permission_required('accounts.change_customuser', raise_exception=True)
def user_update(request, pk):
    user_obj = get_object_or_404(CustomUser, pk=pk)

    # Non-superusers cannot edit superusers
    if not request.user.is_superuser and user_obj.is_superuser:
        messages.error(request, 'You do not have permission to edit this user.')
        return redirect('user_list')

    # Admins can only edit users who belong to their administered projects
    if request.user.groups.filter(name='Admin').exists() and not request.user.is_superuser:
        administered = request.user.administered_projects.all()
        if not user_obj.projects.filter(pk__in=administered).exists():
            messages.error(request, 'You can only edit users within your administered projects.')
            return redirect('user_list')

    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, instance=user_obj, request_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'User updated successfully!')
            return redirect('user_list')
    else:
        form = CustomUserChangeForm(instance=user_obj, request_user=request.user)
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': f'Edit User: {user_obj.username}',
    })
