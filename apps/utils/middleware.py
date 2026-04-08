"""
Middleware for normalizing and fixing content-type headers in requests.
"""
class NormalizeContentTypeMiddleware:
    """
    Middleware that normalizes Content-Type headers for API requests.
    
    Converts unsupported content types (like text/plain) to application/json
    for POST, PUT, PATCH requests if the body contains JSON-like data.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only process API requests with data mutation methods
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            content_type = request.META.get('CONTENT_TYPE', '').lower()
            
            # If content-type is text/plain and there's a body, assume JSON
            if 'text/plain' in content_type or content_type == '':
                if request.body:
                    request.META['CONTENT_TYPE'] = 'application/json'
        
        response = self.get_response(request)
        return response

