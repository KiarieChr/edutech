import json
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from .services import FahariIntelligenceService
from anthropic import Anthropic
import traceback
from django.db import connection
from .models import IntelligenceUsage, AnthropicAPIKey, IntelligenceChatSession, IntelligenceChatMessage
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import BasePermission
from .serializers import AnthropicAPIKeySerializer, IntelligenceChatSessionSerializer

class IsSuperUser(BasePermission):
    """
    Allows access only to superusers.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)

class AnthropicAPIKeyViewSet(viewsets.ModelViewSet):
    queryset = AnthropicAPIKey.objects.all()
    serializer_class = AnthropicAPIKeySerializer
    permission_classes = [IsSuperUser]
    
    def perform_create(self, serializer):
        # If this is set as active, maybe deactivate others? (optional logic)
        if serializer.validated_data.get('is_active', False):
            AnthropicAPIKey.objects.update(is_active=False)
        serializer.save()

    def perform_update(self, serializer):
        if serializer.validated_data.get('is_active', False):
            AnthropicAPIKey.objects.exclude(pk=self.get_object().pk).update(is_active=False)
        serializer.save()

class IntelligenceChatSessionViewSet(viewsets.ModelViewSet):
    serializer_class = IntelligenceChatSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return IntelligenceChatSession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

def get_anthropic_api_key():
    """
    Helper function to get the active Anthropic API key from the database.
    Falls back to settings.ANTHROPIC_API_KEY if no active key is found in the DB.
    """
    active_key = AnthropicAPIKey.objects.filter(is_active=True).first()
    if active_key and active_key.api_key:
        return active_key.api_key
    return getattr(settings, 'ANTHROPIC_API_KEY', None)

def generate_sse_stream(anthropic_stream):
    """
    Yields Server-Sent Events from the Anthropic stream.
    """
    try:
        for event in anthropic_stream:
            if event.type == "content_block_delta":
                # Yield text delta
                data = json.dumps({"text": event.delta.text})
                yield f"data: {data}\n\n"
        # Yield end event
        yield f"data: {json.dumps({'done': True})}\n\n"
    except Exception as e:
        error_msg = json.dumps({"error": str(e)})
        yield f"data: {error_msg}\n\n"

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def report_card_narrative(request):
    try:
        # Extract parameters
        data = request.data
        student_id = data.get('student_id')
        term = data.get('term')
        academic_year = data.get('academic_year')
        class_id = data.get('class_id')
        tone = data.get('tone', 'formal')
        
        if not all([student_id, term, academic_year]):
            return JsonResponse({"error": "Missing required parameters"}, status=400)
            
        # Check if intelligence module is enabled
        if not getattr(settings, 'AI_MODULE_ENABLED', True):
            return JsonResponse({"error": "Fahari Intelligence is not activated."}, status=403)

        # 1. Context Builder (Retrieval & Anonymisation)
        context = FahariIntelligenceService.get_student_academic_context(
            student_id=student_id,
            term=term,
            academic_year=academic_year,
            class_id=class_id
        )

        system_prompt, user_prompt = FahariIntelligenceService.build_narrative_prompts(context, tone)

        # 2. Setup Anthropic API Call
        api_key = get_anthropic_api_key()
        if not api_key:
            return JsonResponse({"error": "No active Anthropic API key found. Please configure one in the settings."}, status=400)
            
        client = Anthropic(api_key=api_key)
        
        # We use a stream for real-time text delivery
        stream = client.messages.create(
            max_tokens=300,
            temperature=0.7,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            model="claude-sonnet-5",
            stream=True,
        )

        # 3. Log Audit
        # Note: We are logging BEFORE completion. In a robust setup, you might want 
        # to log it after streaming finishes, but streaming makes post-logging tricky 
        # without background workers. We'll log it as 'PENDING' for now.
        FahariIntelligenceService.log_audit(
            user=request.user,
            data_scope=f"Report Card Narrative for Student ID {student_id}",
            document_type="REPORT_CARD_NARRATIVE",
            status="PENDING"
        )

        # 4. Return Streaming Response
        response = StreamingHttpResponse(
            generate_sse_stream(stream),
            content_type="text/event-stream"
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no' # For NGINX to not buffer SSE
        return response

    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": "Internal server error occurred."}, status=500)


@csrf_exempt
@api_view(['POST'])
def ask_intelligence(request):
    """
    Streaming endpoint for conversational queries.
    """
    try:
        data = request.data
        query = data.get('query')
        history = data.get('history', [])
        session_id = data.get('session_id')
        
        if not query:
            return JsonResponse({"error": "Missing query"}, status=400)

        schema_name = connection.schema_name
        
        # 1. Fetch Aggregated Institutional Context
        context = FahariIntelligenceService.get_institutional_context(schema_name)
        system_prompt = FahariIntelligenceService.build_chat_system_prompt(context)
        
        # Resolve session
        if session_id:
            try:
                session = IntelligenceChatSession.objects.get(id=session_id, user=request.user)
            except IntelligenceChatSession.DoesNotExist:
                return JsonResponse({"error": "Session not found"}, status=404)
        else:
            # Create a new session. Use first few words of query as title.
            title = ' '.join(query.split()[:5]) + '...'
            session = IntelligenceChatSession.objects.create(user=request.user, title=title)

        # Save user message
        IntelligenceChatMessage.objects.create(session=session, role='user', content=query)
        
        # Override history from DB if we want, but for now we'll just use what the frontend sent or build it.
        # Let's use the DB history so we don't rely on the frontend
        db_messages = session.messages.order_by('created_at')
        messages = [{"role": msg.role, "content": msg.content} for msg in db_messages]
        
        # Limit to last 10 messages to avoid token limit overflow
        messages = messages[-10:]
        
        api_key = get_anthropic_api_key()
        if not api_key:
            return JsonResponse({"error": "No active Anthropic API key found. Please configure one in the settings."}, status=400)
            
        client = Anthropic(api_key=api_key)
        
        def event_stream():
            try:
                assistant_response = ""
                with client.messages.stream(
                    max_tokens=500,
                    system=system_prompt,
                    messages=messages,
                    model="claude-sonnet-5",
                ) as stream:
                    # Inform frontend of the session_id so they can update their URL/state
                    yield f"data: {json.dumps({'session_id': session.id})}\n\n"
                    
                    for text in stream.text_stream:
                        assistant_response += text
                        yield f"data: {json.dumps({'text': text})}\n\n"
                
                # Save assistant message
                IntelligenceChatMessage.objects.create(session=session, role='assistant', content=assistant_response)
                
                # Log usage correctly based on the model
                try:
                    current_month = timezone.now().date().replace(day=1)
                    usage, created = IntelligenceUsage.objects.get_or_create(month=current_month)
                    usage.documents_generated += 1
                    usage.tokens_approx += 500
                    usage.save()
                except Exception as usage_err:
                    print("Error logging usage:", usage_err)
                    
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingHttpResponse(event_stream(), content_type='text/event-stream')

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": "Internal server error occurred."}, status=500)
