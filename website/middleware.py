from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.conf import settings


class JWTAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        access_token = request.COOKIES.get(settings.JWT_AUTH_COOKIE)
        if access_token and not request.user.is_authenticated:
            try:
                token = AccessToken(access_token)
                User = get_user_model()
                request.user = User.objects.get(id=token['user_id'])
            except (TokenError, InvalidToken, User.DoesNotExist):
                pass
        return self.get_response(request)
