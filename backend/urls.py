from ninja import NinjaAPI
from ninja.security import HttpBearer
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.authentication import JWTAuthentication as DRFJWTAuth
from rest_framework_simplejwt.exceptions import InvalidToken
from ninja.errors import HttpError

from authy.api import router as auth_router
from job_board.api import router as job_board_router



class JWTOrBearerKeyAuth(HttpBearer):
    def authenticate(self, request, token):
        if not token:
            return None
        try:
            drf_auth = DRFJWTAuth() 
            validated = drf_auth.authenticate(request)
            if validated is not None:
                user, _ = validated
                return user
        except InvalidToken as e:
            # Return HTTP 401 instead of raising AuthenticationFailed
            raise HttpError(401, f"Invalid or expired token: {str(e)}")
        except Exception:
            # Catch other unforeseen authentication issues gracefully
            raise HttpError(401, "Authentication failed. Invalid or expired token.")
        


api = NinjaAPI(
    title="APPLYJOB API",
    auth=[JWTOrBearerKeyAuth()],
    openapi_extra={
        "info": {"termsOfService": "www.applyjob.ng"}
    },
    description="Apply job api Docs",
)

api.add_router("auth", auth_router)
api.add_router("jobs", job_board_router)



urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls ),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)