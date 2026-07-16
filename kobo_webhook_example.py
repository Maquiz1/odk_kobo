import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# This is an example Django view to receive KoboToolbox Webhooks

@csrf_exempt  # Kobo won't send a CSRF token, so we must exempt this view
@require_POST # Webhooks are sent as POST requests
def kobo_webhook_receiver(request):
    try:
        # 1. Parse the incoming JSON data from KoboToolbox
        payload = json.loads(request.body)
        
        # 2. Extract the data you care about
        # KoboToolbox form data is usually inside the payload directly or under specific keys
        # depending on your form structure. For example:
        submission_id = payload.get('_id')
        uuid = payload.get('_uuid')
        submitted_by = payload.get('_submitted_by')
        
        # Example form fields (these will match your Kobo question names):
        patient_name = payload.get('patient_name', 'Unknown')
        medication = payload.get('medication_given', '')
        
        # 3. Save the data to your Django database
        # Example:
        # MyModel.objects.create(
        #     kobo_id=submission_id,
        #     uuid=uuid,
        #     name=patient_name,
        #     medication=medication
        # )

        print(f"Received submission {submission_id} from {submitted_by}")

        # 4. Return a 201 Created or 200 OK response so Kobo knows it was successful
        return JsonResponse({"status": "success", "message": "Data received"}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON payload"}, status=400)
    except Exception as e:
        # Note: Use Python's logging module in production instead of print!
        print(f"Error processing webhook: {e}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
