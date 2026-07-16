import json
import logging
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Record
from projects.models import Project

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def kobo_webhook(request):
    """
    Endpoint: POST /webhook/kobo/
    KoboToolbox sends a JSON payload for each form submission.

    Authentication: Authorization header must match KOBO_WEBHOOK_TOKEN.
    Project matching: uses the 'formhub/uuid' or '_xform_id_string' field
    to find the matching Project via kobo_asset_id.
    """
    # --- Token authentication ---
    expected_token = settings.KOBO_WEBHOOK_TOKEN
    if expected_token:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Token ', '').strip()
        if token != expected_token:
            logger.warning('Webhook: unauthorized attempt — invalid token.')
            return JsonResponse({'error': 'Unauthorized'}, status=401)

    # --- Parse payload ---
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error('Webhook: received invalid JSON payload.')
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # --- Extract key fields from Kobo submission ---
    kobo_id = payload.get('_id') or payload.get('formhub/uuid') or payload.get('_uuid')
    uuid = payload.get('_uuid', '')
    submitted_by = payload.get('_submitted_by', '')

    # Identify the asset/form ID to match a Project
    asset_id = (
        payload.get('_xform_id_string') or
        payload.get('formhub/uuid') or
        ''
    )

    if not kobo_id:
        logger.error('Webhook: submission missing a unique ID.')
        return JsonResponse({'error': 'Missing submission ID'}, status=400)

    # --- Match to a Project ---
    project = None
    if asset_id:
        project = Project.objects.filter(kobo_asset_id=asset_id, is_active=True).first()
        if not project:
            logger.warning(f'Webhook: no active project found for asset_id="{asset_id}". Saving without project.')

    # --- Create or update the Record ---
    record, created = Record.objects.update_or_create(
        kobo_id=str(kobo_id),
        defaults={
            'uuid': uuid,
            'submitted_by': submitted_by,
            'data': payload,
            'project': project,
        }
    )

    action = 'created' if created else 'updated'
    logger.info(f'Webhook: record {kobo_id} {action} (project={project}).')
    return JsonResponse({'status': 'ok', 'record_id': record.pk, 'action': action}, status=201 if created else 200)
