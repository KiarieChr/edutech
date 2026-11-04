from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.core.cache import cache
from student_management.utils.excel_utils import ExcelImportUtils
import uuid


class StudentImportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated] # Restrict to Admin/Registrar in production
    parser_classes = [MultiPartParser, JSONParser]

    @action(detail=False, methods=['get'])
    def template(self, request):
        """
        Download Excel template for student bulk import
        """
        try:
            return ExcelImportUtils.generate_template()
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def upload(self, request):
        """
        Upload filled Excel template.
        Supports 'dry_run' query param to validate without saving.
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check extension
        if not file_obj.name.endswith('.xlsx'):
             return Response({'error': 'Invalid file format. Please upload .xlsx file.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from core.campus_filter import get_effective_campus_id
            from workforce.models import Campus

            effective_cid = get_effective_campus_id(request)
            target_campus = None
            if effective_cid:
                target_campus = Campus.objects.filter(id=effective_cid).first()

            # 1. Parse and Validate with target_campus fallback
            result = ExcelImportUtils.parse_and_validate(file_obj, target_campus=target_campus)
            
            # If critical structure errors
            if result.get('critical_error'):
                 return Response(result, status=status.HTTP_400_BAD_REQUEST)

            dry_run = request.query_params.get('dry_run', 'false').lower() == 'true'
            
            if dry_run or not result['success']:
                # Return validation results (preview / errors)
                # Sanitize result for JSON response
                safe_result = {
                    'success': result['success'],
                    'total_rows': result['total_rows'],
                    'preview': result['preview'],
                    'valid_rows': [], # Placeholder to satisfy frontend .length check
                    'errors': [],
                    'target_campus': target_campus.name if target_campus else None
                }
                safe_result['valid_rows'] = [{} for _ in result['valid_rows']]

                # Sanitize errors data
                for error in result['errors']:
                    safe_data = {k: str(v) for k, v in error['data'].items() if not k in ['curriculum', 'level', 'grade', 'stream', 'intake', 'year', 'term', 'dob_obj', 'adm_date_obj', 'campus']}
                    if error['data'].get('campus'):
                        safe_data['campus'] = getattr(error['data']['campus'], 'name', str(error['data']['campus']))
                    safe_result['errors'].append({
                        'row': error['row'],
                        'errors': error['errors'],
                        'data': safe_data
                    })

                # Cache validated rows for chunked processing
                if result['success'] and result['valid_rows']:
                    import_id = str(uuid.uuid4())
                    serialized = ExcelImportUtils._serialize_valid_rows(result['valid_rows'], target_campus_id=effective_cid)
                    cache.set(f'import_{import_id}', serialized, timeout=1800)
                    cache.set(f'import_campus_{import_id}', effective_cid, timeout=1800)
                    safe_result['import_id'] = import_id

                return Response(safe_result)
            
            # 2. Process Import (only if valid and not dry run)
            created_count = ExcelImportUtils.process_import(result['valid_rows'], user=request.user, target_campus=target_campus)
            
            return Response({
                'success': True,
                'message': f'Successfully imported {created_count} students.',
                'created_count': created_count
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': f"Import failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='process-chunk')
    def process_chunk(self, request):
        """
        Process a chunk of previously validated rows.
        Body: { import_id, offset, chunk_size }
        """
        import_id = request.data.get('import_id')
        offset = int(request.data.get('offset', 0))
        chunk_size = int(request.data.get('chunk_size', 50))

        if not import_id:
            return Response({'error': 'import_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f'import_{import_id}'
        all_rows = cache.get(cache_key)

        if all_rows is None:
            return Response(
                {'error': 'Import session expired or not found. Please re-validate the file.'},
                status=status.HTTP_404_NOT_FOUND
            )

        total = len(all_rows)
        chunk = all_rows[offset:offset + chunk_size]

        if not chunk:
            return Response({
                'processed': total,
                'total': total,
                'chunk_created': 0,
                'complete': True,
            })

        try:
            from core.campus_filter import get_effective_campus_id
            target_cid = cache.get(f'import_campus_{import_id}') or get_effective_campus_id(request)

            created = ExcelImportUtils.process_chunk(chunk, importing_user=request.user, target_campus_id=target_cid)
            processed = min(offset + chunk_size, total)
            complete = processed >= total

            # Clear cache when done
            if complete:
                cache.delete(cache_key)
                cache.delete(f'import_campus_{import_id}')

            return Response({
                'processed': processed,
                'total': total,
                'chunk_created': created,
                'complete': complete,
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed at rows {offset + 1}-{offset + len(chunk)}: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
