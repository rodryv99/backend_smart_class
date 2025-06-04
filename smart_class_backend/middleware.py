# smart_class_backend/middleware.py
class NoCacheMiddleware:
    """
    Middleware para deshabilitar el caché en las respuestas de la API
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Solo aplicar a rutas de API
        if request.path.startswith('/api/'):
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            response['Last-Modified'] = None
            response['ETag'] = None
        
        return response