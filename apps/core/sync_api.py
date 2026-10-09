import json
from django.db import transaction, IntegrityError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django_tenants.utils import tenant_context
from .sync_auth import Ed25519SyncAuthentication
from .models import SyncProcessedEvent, SyncErrorLog
from django.apps import apps
from django.utils import timezone

SYNCABLE_MODELS = {
    "workforce.Employee": "workforce.Employee",
    # Add other mapped models here
}

class SyncPushAPIView(APIView):
    authentication_classes = [Ed25519SyncAuthentication]

    def post(self, request, *args, **kwargs):
        installation = request.user.installation
        tenant = request.user.tenant

        try:
            payload = json.loads(request.body)
            events = payload.get('events', [])
        except json.JSONDecodeError:
            return Response({"error": "INVALID_PAYLOAD"}, status=status.HTTP_400_BAD_REQUEST)

        response_data = {
            "processed": [],
            "already_processed": [],
            "failed": []
        }

        with tenant_context(tenant):
            for event in events:
                event_id = event.get('event_id')
                source_installation_id = event.get('source_installation_id')
                model_str = event.get('model')
                action = event.get('action')
                sync_id = event.get('sync_id')
                event_payload = event.get('payload', {})

                if not event_id:
                    response_data["failed"].append({
                        "event_id": None,
                        "code": "MISSING_EVENT_ID",
                        "message": "Event ID is required"
                    })
                    continue

                if source_installation_id != installation.installation_id:
                    response_data["failed"].append({
                        "event_id": event_id,
                        "code": "INVALID_SOURCE",
                        "message": "Source installation does not match authenticated installation"
                    })
                    continue

                if model_str not in SYNCABLE_MODELS:
                    response_data["failed"].append({
                        "event_id": event_id,
                        "code": "UNKNOWN_MODEL",
                        "message": f"Model {model_str} is not syncable"
                    })
                    continue

                try:
                    with transaction.atomic():
                        # 1. Idempotency Check with inner savepoint
                        try:
                            with transaction.atomic():
                                SyncProcessedEvent.objects.create(event_id=event_id)
                        except IntegrityError:
                            response_data["already_processed"].append(event_id)
                            continue

                        # 2. Process Business Logic
                        app_label, model_name = SYNCABLE_MODELS[model_str].split('.')
                        ModelClass = apps.get_model(app_label, model_name)

                        # Validate payload to prevent protected field modification
                        protected_fields = {'id', 'tenant', 'created_at', 'updated_at'}
                        clean_payload = {k: v for k, v in event_payload.items() if k not in protected_fields}

                        if action == "CREATE":
                            if not ModelClass.objects.filter(sync_id=sync_id).exists():
                                ModelClass.objects.create(sync_id=sync_id, **clean_payload)
                        elif action == "UPDATE":
                            ModelClass.objects.filter(sync_id=sync_id).update(**clean_payload)
                        elif action == "DELETE":
                            ModelClass.objects.filter(sync_id=sync_id).delete()
                        else:
                            raise ValueError(f"UNSUPPORTED_ACTION: {action}")

                        response_data["processed"].append(event_id)
                except Exception as e:
                    response_data["failed"].append({
                        "event_id": event_id,
                        "code": "EVENT_APPLICATION_FAILED",
                        "message": "An error occurred during event processing."
                    })
                    # Log error in an isolated transaction to prevent rolling back the error log
                    try:
                        with transaction.atomic():
                            SyncErrorLog.objects.create(
                                event_id=event_id,
                                sync_id=sync_id,
                                installation_id=source_installation_id,
                                model_name=model_str,
                                action=action,
                                error_code="EVENT_APPLICATION_FAILED",
                                error_message=str(e),
                                payload=event_payload
                            )
                    except Exception:
                        pass

        return Response(response_data, status=status.HTTP_200_OK)
