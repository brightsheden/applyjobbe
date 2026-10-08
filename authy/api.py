from authy.models import Skill
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from asgiref.sync import sync_to_async
from ninja import File, Form, Router
from ninja.files import UploadedFile
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
import base64
import logging
import uuid
import os
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from authy.models import Notification, OTP, User, Company, Candidate,Education,Experience,Reference,Skill


from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from authy.schemas import (
   
    ForgetPasswordRequest,
    LoginResponse,
    LoginSchema,
    NotificationListResponse,
    NotificationUnreadCountResponse,
    OnboardingRequest,
    RegisterRequest,
    RessetPasswordRequest,
    RequestOtpRequest,
    #UpdateProfileRequest,
    VerifyOtpRequest,
    UserProfileSchema,
    UserProfileListResponse,
    AddUserRequest,
    GoogleLoginRequest,
    ChangePasswordRequest,
    CompanyRegisterSchema,
    CandidateProfileSchema,
    CandidateProfileListResponse,
    CompanyProfileSchema,
    CompanyProfileListResponse,
    CandidateProfileSetup,  
)
from core.schemas import BaseResponseSchema, ErrorResponse

router = Router(
    tags=["Authentication"]
)

logger = logging.getLogger(__name__)


def _schema_data(payload, *, exclude_none=False):
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=exclude_none)
    return payload.dict(exclude_none=exclude_none)


def _is_admin(user) -> bool:
    return bool(user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)))


def _admin_required(request):
    user = request.auth
    if not user:
        return None, ErrorResponse(message="User not found", code=404)
    if not _is_admin(user):
        return None, ErrorResponse(message="Admin access required", code=403)
    return user, None


def _serialize_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "state": user.state,
        "city": user.city,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_email_verified": user.is_email_verified,
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
    }


def _serialize_design(design):
    latest_job = getattr(design, "_latest_job", None)
    return {
        "id": design.id,
        "user_id": design.user_id,
        "user_email": design.user.email if getattr(design, "user", None) else "",
        "category": design.category.name if getattr(design, "category", None) else "",
        "design_type": design.design_type.name if getattr(design, "design_type", None) else "",
        "status": latest_job.status if latest_job else "",
        "is_template": design.is_template,
        "is_edited": design.is_edited,
        "credit_cost": design.credit_cost,
        "ai_cost_usd": str(design.ai_cost_usd),
        "created_at": design.created_at.isoformat() if design.created_at else None,
        "file_url": design.file.url if design.file else None,
    }


def _decode_data_url(data_url: str) -> tuple[str, bytes]:
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise ValueError("image_data_url must be a base64 image data URL")

    header, encoded = data_url.split(";base64,", 1)
    extension = header.replace("data:image/", "").split("+", 1)[0]
    if extension == "jpeg":
        extension = "jpg"
    if extension not in {"png", "jpg", "webp"}:
        raise ValueError("Only png, jpg, and webp exports are supported")

    return extension, base64.b64decode(encoded)


def _parse_id_list(*values) -> list[int]:
    ids = []
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, int):
            ids.append(value)
            continue
        for item in str(value).split(","):
            item = item.strip()
            if not item:
                continue
            try:
                ids.append(int(item))
            except ValueError:
                continue
    return list(dict.fromkeys(ids))


def _filter_design_queryset(
    queryset,
    *,
    search: str | None = None,
    category_id: int | None = None,
    category_ids: str | None = None,
    design_type_id: int | None = None,
    design_type_ids: str | None = None,
    category: str | None = None,
    design_type: str | None = None,
):
    category_id_list = _parse_id_list(category_id, category_ids)
    design_type_id_list = _parse_id_list(design_type_id, design_type_ids)

    if category_id_list:
        queryset = queryset.filter(category_id__in=category_id_list)
    if design_type_id_list:
        queryset = queryset.filter(design_type_id__in=design_type_id_list)
    if category:
        queryset = queryset.filter(category__name__icontains=category.strip())
    if design_type:
        queryset = queryset.filter(design_type__name__icontains=design_type.strip())

    if search and search.strip():
        term = search.strip()
        queryset = queryset.filter(
            Q(prompt_used__icontains=term)
            | Q(user_prompt_used__icontains=term)
            | Q(output_format__icontains=term)
            | Q(output_size__icontains=term)
            | Q(category__name__icontains=term)
            | Q(design_type__name__icontains=term)
        )

    return queryset


async def _paginate_queryset(queryset, page: int, page_size: int):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = await queryset.acount()
    offset = (page - 1) * page_size
    data = [item async for item in queryset[offset:offset + page_size]]

    return {
        "success": True,
        "data": data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": offset + page_size < total,
        "has_previous": page > 1,
    }



@router.post('/login',auth=None, response={200:LoginResponse, 400:ErrorResponse,500:ErrorResponse})
def login(request, payload:LoginSchema):
    try:
        if '@' in payload.username:
            user = User.objects.filter(email=payload.username).first()   
        else:
            user = User.objects.filter(username=payload.username).first()

        if not user:
            return 400, ErrorResponse(message="User not found", code=400)

        if user.check_password(payload.password):
            refresh_token = RefreshToken.for_user(user)
            # create_activity(user=user,action=PlatformActivity.ActivityEnums.LOGIN.value, description="User login")
            return 200, LoginResponse(user=user, access_token=str(refresh_token.access_token), refresh_token=str(refresh_token))
        else:
            return 400, ErrorResponse(message="Incorect password", code=400)
        
    except Exception as e:
        return 500, ErrorResponse(detail=str(e))

@router.post('/google', auth=None, response={200: LoginResponse, 400: ErrorResponse, 500: ErrorResponse})
def google_login(request, payload: GoogleLoginRequest):
    try:
        # Verify the Google token
        client_id = os.getenv("VITE_GOOGLE_CLIENT_ID", "")
        try:
            if client_id:
                id_info = id_token.verify_oauth2_token(payload.credential, google_requests.Request(), client_id)
            else:
                # If no client ID configured yet, verify signature without audience check (for dev/placeholder)
                # But google-auth library might require audience. Let's pass None and see, or catch the ValueError
                id_info = id_token.verify_oauth2_token(payload.credential, google_requests.Request(), audience=None)
        except ValueError as e:
            # Token invalid
            return 400, ErrorResponse(message=f"Invalid Google token: {str(e)}", code=400)

        email = id_info.get("email")
        if not email:
            return 400, ErrorResponse(message="Google token does not contain email", code=400)
            
        first_name = id_info.get("given_name", "")
        last_name = id_info.get("family_name", "")

        user = User.objects.filter(email=email).first()
        if not user:
            # Create a new user
            username = email.split('@')[0]
            # Ensure unique username
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
                
            user = User.objects.create_user(
                username=username,
                email=email,
                password=None,
                first_name=first_name,
                last_name=last_name,
                is_email_verified=True,
            )

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        return 200, LoginResponse(
            user=user,
            access_token=access_token,
            refresh_token=str(refresh)
        )
    except Exception as e:
        logger.exception("Google login failed")
        return 500, ErrorResponse(message="Internal server error", detail=str(e))


@router.post('/company_register',auth=None, response={200:LoginResponse, 400:ErrorResponse, 500:ErrorResponse})
def company_register(request, payload:CompanyRegisterSchema):
    try:
        username = payload.username or payload.email.split('@')[0]

        if User.objects.filter(username=username).exists():
            return 400, ErrorResponse(message="Username already exists")
        
        if User.objects.filter(email=payload.email).exists():
           return 400, ErrorResponse(message="Email already exists")

        if User.objects.filter(phone_number=payload.phone_number).exists():
            return 400, ErrorResponse(message="Phone number already exists")

        with transaction.atomic():
        
            user = User.objects.create_user(
                username=username,
                email=payload.email,
                password=payload.password,
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone_number=payload.phone_number,
            user_type=User.USERTYPE.EMPLOYER,
            )

            company = Company.objects.create(
                name=payload.company_name,
                user=user,
                email=payload.company_email,
                phone_number=payload.company_phone,
                registration_number=payload.registration_number,
                industry=payload.industry,
                company_size=payload.company_size,
                website_url=payload.website_url,
                location=payload.location,
                country=payload.country,
                state=payload.state,
                city=payload.city,
                address=payload.address,
            )

        return 200, LoginResponse(
            user=user,
            access_token="",
            refresh_token=""
        )
    except Exception as e:
        logger.exception("Company registration failed")
        return 500, ErrorResponse(message="Internal server error", detail=str(e))

@router.post('/register',auth=None, response={200:LoginResponse, 400:ErrorResponse, 500:ErrorResponse})
def register(request, payload:RegisterRequest):
    try:
        username = payload.username or payload.email.split('@')[0]

        if User.objects.filter(username=username).exists():
            return 400, ErrorResponse(message="Username already exists")
        
        if User.objects.filter(email=payload.email).exists():
           return 400, ErrorResponse(message="Email already exists")

        if User.objects.filter(phone_number=payload.phone_number).exists():
            return 400, ErrorResponse(message="Phone number already exists")

        try:
            user = User.objects.create_user(
                username=username,
                password=payload.password,
                email=payload.email,
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone_number=payload.phone_number,
                gender=payload.gender,
                user_type=User.USERTYPE.CANDIDATE,
                dob=payload.dob,
                country=payload.country,
                state=payload.state,
                city=payload.city,
                address=payload.address,   
            )

            Candidate.objects.create(
                user=user,
                primary_role=payload.primary_role,
                years_of_experience=payload.years_of_experience,
                highest_education=payload.education,
            )
            
        except IntegrityError:
            logger.exception(
                "Register integrity error for email=%s username=%s phone=%s",
                payload.email,
                username,
                payload.phone_number,
            )
            return 400, ErrorResponse(message="Account already exists with these details")

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        if payload.referral_code:
            referred_by = User.objects.filter(username=payload.referral_code).first()
            user.referred_by=referred_by
            user.save()

      

        return 200, LoginResponse(
            user = user,
            access_token=str(access_token),
            refresh_token=str(refresh)
  
        )
    except Exception as e:
        logger.exception(
            "Register failed for email=%s username=%s phone=%s",
            getattr(payload, "email", None),
            getattr(payload, "username", None),
            getattr(payload, "phone_number", None),
        )
        return 500, ErrorResponse(message="Internal server error", detail=str(e))

@router.post("/onboarding", response={200: BaseResponseSchema, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def onboarding(request, payload: OnboardingRequest, logo: UploadedFile | None = File(None)):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)

     
    except Exception as e:
        return 500, ErrorResponse(message="Unable to complete onboarding", detail=str(e))


@router.post("/verify_otp", auth=None, response={200:BaseResponseSchema, 400:ErrorResponse, 404:ErrorResponse, 500:ErrorResponse})
def verify_otp(request, payload: VerifyOtpRequest):
    try:
        if not payload.code:
            return 400, ErrorResponse(message="OTP code is required", code=400)

        if not payload.email and not payload.phone_number:
            return 400, ErrorResponse(
                message="Email or phone number is required",
                code=400,
            )

        filters = {"is_used": False}
        if payload.email:
            filters["email__iexact"] = payload.email
        if payload.phone_number:
            filters["phone_number"] = payload.phone_number
        if payload.purpose:
            filters["purpose"] = payload.purpose

        otp = (
            OTP.objects.select_related("user")
            .filter(**filters)
            .order_by("-created_at")
            .first()
        )

        if not otp:
            return 404, ErrorResponse(message="OTP not found", code=404)

        is_valid, message = otp.validate_otp(payload.code)
        if not is_valid:
            return 400, ErrorResponse(message=message, code=400)

        if otp.user and otp.purpose in {
            OTP.Purpose.ACCOUNT_VERIFICATION,
            OTP.Purpose.EMAIL_VERIFICATION,
            OTP.Purpose.PHONE_VERIFICATION,
        }:
            otp.user.is_email_verified = True
            otp.user.save(update_fields=["is_email_verified"])

        return 200, BaseResponseSchema(
            message=message,
            data={
                "purpose": otp.purpose,
                "channel": otp.channel,
                "user_id": otp.user_id,
            },
        )
    except Exception as e:
        return 500, ErrorResponse(message="Internal server error", detail=str(e))


@router.post("/request_otp", auth=None, response={200: BaseResponseSchema, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def request_otp(request, payload: RequestOtpRequest):
    """Generate and email a new account-verification OTP."""
    try:
        email = payload.email.strip()
        if not email:
            return 400, ErrorResponse(message="Email is required", code=400)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)

        if user.is_email_verified:
            return 400, ErrorResponse(message="Email is already verified", code=400)

        with transaction.atomic():
            now = timezone.now()
            OTP.objects.filter(
                user=user,
                purpose__in=[
                    OTP.Purpose.ACCOUNT_VERIFICATION,
                    OTP.Purpose.EMAIL_VERIFICATION,
                ],
                channel=OTP.Channel.EMAIL,
                is_used=False,
            ).update(is_used=True, used_at=now, updated_at=now)

            otp = OTP.generate_otp(
                user=user,
                purpose=OTP.Purpose.ACCOUNT_VERIFICATION,
                channel=OTP.Channel.EMAIL,
                email=user.email,
            )

        user.send_email(
            subject="Verify your QwikMarka email",
            context={
                "user_email": user.email,
                "otp": otp.code,
                "brand_name": "QwikMarka",
            },
            template_name="email_verification.html",
        )

        return 200, BaseResponseSchema(
            message="Verification OTP sent successfully",
            data={"email": user.email, "expires_at": otp.expires_at},
        )
    except Exception as e:
        logger.exception("Failed to regenerate verification OTP")
        return 500, ErrorResponse(
            message="Unable to send verification OTP",
            detail=str(e),
            code=500,
        )



@router.post("/forget-password",auth=None, response={200:BaseResponseSchema, 400:ErrorResponse, 404:ErrorResponse, 500:ErrorResponse})
def forget_password(request, payload:ForgetPasswordRequest):
    """forget password"""
    try:
        email = payload.email

        user = User.objects.filter(email=email).first()
        if not user:
            return 404,ErrorResponse(message="User not found", code=404)
        
        token = RefreshToken.for_user(user)
        access_token = str(token.access_token)
        base_url = settings.RESSET_URL.rstrip("/")
        frontend_url = f"{base_url}/?token={access_token}"
        context = {
            "reset_url": frontend_url
        }
        user.send_email(
            subject="Forget Password Request",
            context=context,
            template_name="resset_password.html"
        )

        return 200, BaseResponseSchema(message="Forget Password Request sent sucessfully")
    except Exception as e:
        return 500, ErrorResponse(message="An error occured while while sending forget password", detail=str(e))



@router.post("/reset-password", auth=None, response={200:BaseResponseSchema, 404:ErrorResponse, 400:ErrorResponse, 500:ErrorResponse})
def resset_password(request, payload:ForgetPasswordRequest):
    """resset password"""
    try:
        token = payload.token
        new_password = payload.new_password
        access_token = AccessToken(token)
        user_id = access_token.get("user_id")

        if not user_id:
            return 400, ErrorResponse(message="Invalid reset token", code=400)

        user = User.objects.filter(id=user_id).first()
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)

        if user.check_password(new_password):
            return 400, ErrorResponse(
                message="New password must be different from the current password",
                code=400,
            )

        validate_password(new_password, user=user)
        user.set_password(new_password)
        user.save(update_fields=["password"])

        return 200, BaseResponseSchema(message="Password reset successful")
    except TokenError:
        return 400, ErrorResponse(message="Invalid or expired reset token", code=400)
    except DjangoValidationError as e:
        return 400, ErrorResponse(message="Invalid password", detail=" ".join(e.messages), code=400)
    except Exception as e:
        return 500, ErrorResponse(message="Unable to reset password", detail=str(e))


@router.post("/change-password", response={200:BaseResponseSchema, 400:ErrorResponse, 404:ErrorResponse, 500:ErrorResponse})
def change_password(request, payload: ChangePasswordRequest):
    """change password for authenticated user"""
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)

        if not user.check_password(payload.old_password):
            return 400, ErrorResponse(message="Current password is incorrect", code=400)

        if payload.old_password == payload.new_password:
            return 400, ErrorResponse(
                message="New password must be different from the current password",
                code=400,
            )

        validate_password(payload.new_password, user=user)
        user.set_password(payload.new_password)
        user.save(update_fields=["password"])

        return 200, BaseResponseSchema(message="Password changed successfully")
    except DjangoValidationError as e:
        return 400, ErrorResponse(message="Invalid password", detail=" ".join(e.messages), code=400)
    except Exception as e:
        return 500, ErrorResponse(message="Unable to change password", detail=str(e))

@router.get("/profile", response={200:UserProfileSchema,404:ErrorResponse ,400:ErrorResponse, 500:ErrorResponse})
async def get_profile(request):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found")
        
        data = await User.objects.filter(id=user.id).afirst()
        if not data:
            return 404, ErrorResponse(message="User not found", code=404)

       
        
        return 200, UserProfileSchema(
            data=data
        )

    except Exception as e:
        return 500, ErrorResponse(message="An error occured while fetching Profile", detail=str(e))


# @router.put("/profile", response={200:UserProfileSchema, 400:ErrorResponse, 404:ErrorResponse, 500:ErrorResponse})
# async def update_profile(request, payload: UpdateProfileRequest):
#     try:
#         user = request.auth
#         if not user:
#             return 404, ErrorResponse(message="User not found", code=404)

#         if payload.username and await User.objects.exclude(id=user.id).filter(username=payload.username).aexists():
#             return 400, ErrorResponse(message="Username already exists", code=400)

#         if payload.email and await User.objects.exclude(id=user.id).filter(email=payload.email).aexists():
#             return 400, ErrorResponse(message="Email already exists", code=400)

#         if payload.phone_number and await User.objects.exclude(id=user.id).filter(phone_number=payload.phone_number).aexists():
#             return 400, ErrorResponse(message="Phone number already exists", code=400)

#         updated_fields = []
#         for field in ["username", "first_name", "last_name", "email", "phone_number", "state", "city"]:
#             value = getattr(payload, field)
#             if value is not None:
#                 setattr(user, field, value)
#                 updated_fields.append(field)

#         if not updated_fields:
#             return 400, ErrorResponse(message="No profile fields provided", code=400)

#         await user.asave(update_fields=updated_fields)
        

#         await user.arefresh_from_db()
       
#         return 200, UserProfileSchema(
#             message="Profile updated successfully",
#             data=user,
#         )
#     except Exception as e:
#         return 500, ErrorResponse(message="An error occured while updating profile", detail=str(e))



@router.get("/notifications", response={200: NotificationListResponse, 404: ErrorResponse, 500: ErrorResponse})
async def get_notifications(request, page: int = 1, page_size: int = 20, unread_only: bool = False):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)

        queryset = Notification.objects.filter(user_id=user.id).order_by("-created_at")
        if unread_only:
            queryset = queryset.filter(is_read=False)

        return 200, await _paginate_queryset(queryset, page, page_size)
    except Exception as e:
        return 500, ErrorResponse(message="An error occured while fetching notifications", detail=str(e))


@router.get("/notifications/unread-count", response={200: NotificationUnreadCountResponse, 404: ErrorResponse, 500: ErrorResponse})
async def get_unread_notification_count(request):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)

        unread_count = await Notification.objects.filter(user_id=user.id, is_read=False).acount()
        return 200, NotificationUnreadCountResponse(data={"unread_count": unread_count})
    except Exception as e:
        return 500, ErrorResponse(message="An error occured while fetching notification count", detail=str(e))


@router.patch("/notifications/{notification_id}/read", response={200: BaseResponseSchema, 404: ErrorResponse, 500: ErrorResponse})
async def mark_notification_read(request, notification_id: int):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)

        notification = await Notification.objects.filter(id=notification_id, user_id=user.id).afirst()
        if not notification:
            return 404, ErrorResponse(message="Notification not found", code=404)

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            await notification.asave(update_fields=["is_read", "read_at", "updated_at"])

        return 200, BaseResponseSchema(message="Notification marked as read", data={"id": notification.id})
    except Exception as e:
        return 500, ErrorResponse(message="An error occured while updating notification", detail=str(e))


@router.patch("/notifications/read-all", response={200: BaseResponseSchema, 404: ErrorResponse, 500: ErrorResponse})
async def mark_all_notifications_read(request):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)

        updated = await Notification.objects.filter(user_id=user.id, is_read=False).aupdate(
            is_read=True,
            read_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return 200, BaseResponseSchema(message="Notifications marked as read", data={"updated": updated})
    except Exception as e:
        return 500, ErrorResponse(message="An error occured while updating notifications", detail=str(e))


@router.get("candidate/profile", response={200:CandidateProfileSchema,404:ErrorResponse ,400:ErrorResponse, 500:ErrorResponse})
async def get_candidate_profile(request):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found")
        
        data = await Candidate.objects.filter(user_id=user.id).select_related('user').afirst()
        if not data:
            return 404, ErrorResponse(message="Candidate not found", code=404)

       
        
        return 200, CandidateProfileSchema(
            data=data
        )

    except Exception as e:
        return 500, ErrorResponse(message="An error occured while fetching candidate profile", detail=str(e))

@router.get("company/profile", response={200:CompanyProfileSchema,404:ErrorResponse ,400:ErrorResponse, 500:ErrorResponse})
async def get_company_profile(request):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found")
        
        data = await Company.objects.filter(user_id=user.id).select_related('user').afirst()
        if not data:
            return 404, ErrorResponse(message="Company not found", code=404)

        return 200, CompanyProfileSchema(
            data=data
        )

    except Exception as e:
        return 500, ErrorResponse(message="An error occured while fetching company profile", detail=str(e))

@router.get("candidates", response={200:CandidateProfileListResponse,404:ErrorResponse ,400:ErrorResponse, 500:ErrorResponse})
async def get_candidates(request,search: str | None = None,page: int = 1, page_size: int = 20):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found")
        
        queryset = await Candidate.objects.all().select_related('user')
        
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search) |
                Q(resume__icontains=search)
            )
        data = await _paginate_queryset(queryset, page, page_size)
        if not data:
            return 404, ErrorResponse(message="Candidate not found", code=404)

       
        
        return 200, CandidateProfileListResponse(
            data=queryset
        )

    except Exception as e:
        return 500, ErrorResponse(message="An error occured while fetching candidate profile", detail=str(e))



@router.post("candidate/setup-profile", response={200:BaseResponseSchema,404:ErrorResponse ,400:ErrorResponse, 500:ErrorResponse})
async def setup_candidate_profile(request,payload: CandidateProfileSetup):
    try:
        user = request.auth
        if not user:
            return 404, ErrorResponse(message="User not found", code=404)
        
        candidate = await Candidate.objects.filter(user_id=user.id).afirst()
        if not candidate:
            return 404, ErrorResponse(message="Candidate not found", code=404)

       # setup education
        for edu in payload.educations:
            Education.objects.create(
                candidate=candidate,
                institution=edu.institution,
                degree=edu.degree,
                field_of_study=edu.field_of_study,
                start_date=edu.start_date,
                end_date=edu.end_date,
                gpa=edu.gpa
            )

        # setup experience
        for exp in payload.experiences:
            Experience.objects.create(
                candidate=candidate,
                company=exp.company,
                position=exp.position,
                start_date=exp.start_date,
                end_date=exp.end_date,
                description=exp.description
            )

        # setup reference
        for ref in payload.references:
            Reference.objects.create(
                candidate=candidate,
                name=ref.name,
                relationship=ref.relationship,
                phone_number=ref.phone_number,
                email=ref.email
            )

        # setup skill
        for skill in payload.skills:
            Skill.objects.create(
                candidate=candidate,
                name=skill.name
            )

        return 200, BaseResponseSchema(message="Candidate profile setup successfully", data=candidate)
    except Exception as e:
        return 500, ErrorResponse(message="An error occured while setting up candidate profile", detail=str(e))