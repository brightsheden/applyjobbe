from typing import Any
from pydantic import Field, ConfigDict

from ninja import ModelSchema, Schema
import datetime
from core.schemas import BaseResponseSchema,PaginatedResponse
from authy.models import  Notification, OTP, User,Candidate,Company, CandidateFile, Education,Experience,Reference, Skill






class UserSchema(ModelSchema):
    full_name: str | None = None
    is_business_details_setup: bool = False
    has_completed_onboarding: bool = False
    # instructor: InstructorSchema | None = None

    @staticmethod
    def resolve_is_business_details_setup(obj):
        cached_value = getattr(obj, "_is_business_details_setup", None)
        if cached_value is not None:
            return cached_value
        return obj.has_business_details_setup()

    class Meta:
        model = User
        fields = "__all__"
        exclude=["password","groups","user_permissions"] 
      


class UserProfileSchema(BaseResponseSchema):
    data : UserSchema | None = None

class UserProfileListResponse(PaginatedResponse):
    data:list[UserSchema]



class NotificationSchema(ModelSchema):
    class Meta:
        model = Notification
        fields = "__all__"


class NotificationListResponse(PaginatedResponse):
    data: list[NotificationSchema]


class NotificationUnreadCountSchema(Schema):
    unread_count: int = 0


class NotificationUnreadCountResponse(BaseResponseSchema):
    data: NotificationUnreadCountSchema | None = None






class LoginSchema(Schema):
    username: str
    password: str

class GoogleLoginRequest(Schema):
    credential: str


class LoginResponse(Schema):
    user: UserSchema
    access_token: str
    refresh_token: str



class CompanyRegisterSchema(Schema):
    company_name: str
    company_email: str
    company_phone: str
    registration_number: str
    industry:str | None = None
    company_size:str | None = None
    website_url: str | None = None
    location: str | None = None
    country:str | None = None
    state:str | None = None
    city:str | None = None
    address:str | None = None
    


    password: str
    username: str | None = None
    referral_code: str | None = None
    first_name:str | None = None
    last_name:str| None = None
    email: str | None = None
    job_title: str | None = None
    user_type: User.USERTYPE | None = User.USERTYPE.EMPLOYER
   

class RegisterRequest(Schema):
    first_name: str 
    last_name:str
    email: str
    phone_number:str
    password: str
    username:str | None =None
    referral_code:str | None = None
    gender:str | None = None
    user_type: User.USERTYPE | None =None
    dob: datetime.date | None = None
    country: str | None = None 
    state: str | None = None
    city: str | None = None
    address: str | None = None
    primary_role:str | None = None
    years_of_experience: int | None = None
    education: str | None = None



class OnboardingRequest(Schema):
    model_config = ConfigDict(extra="forbid")
    phone_number:str | None =None
    dob: datetime.date | None = None
    state: str | None = None
    city : str | None = None
    id_number: str | None = None
    id_type: str | None = None



class AddUserRequest(Schema):
    first_name: str 
    last_name:str
    email: str
    phone_number:str
    password: str
    username:str | None =None
    state: str | None = None
    city: str | None = None
    is_staff: bool = False
    role_id: int | None = None



class VerifyOtpRequest(Schema):
    phone_number:str | None = None
    email: str | None = None
    code: str | None = None
    purpose: OTP.Purpose | None = None


class RequestOtpRequest(Schema):
    email: str


class ForgetPasswordRequest(Schema):
    email: str


class RessetPasswordRequest(Schema):
    email: str
    otp: str
    new_password: str


class ChangePasswordRequest(Schema):
    old_password: str
    new_password: str



class EducationSchema(ModelSchema):
    class Meta:
        model = Education
        fields = "__all__"


class ExperienceSchema(ModelSchema):
    class Meta:
        model = Experience
        fields = "__all__"

class ReferenceSchema(ModelSchema):
    class Meta:
        model = Reference
        fields = "__all__"



class SkillSchema(ModelSchema):
    class Meta:
        model = Skill
        fields = "__all__"



class CandidateProfileSetup(Schema):
    educations: list[EducationSchema] | None = None
    experiences: list[ExperienceSchema] | None = None
    references: list[ReferenceSchema] | None = None
    skills: list[SkillSchema] | None = None
    

class CandidateSchema(ModelSchema):
    user: UserSchema | None = None
    education: list[EducationSchema] | None = None
    experience: list[ExperienceSchema] | None = None
    reference: list[ReferenceSchema] | None = None
    skill: list[SkillSchema] | None = None
    class Meta:
        model = Candidate
        fields = "__all__"

class CandidateProfileSchema(BaseResponseSchema):
    data: CandidateSchema | None = None

class CandidateProfileListResponse(PaginatedResponse):
    data: list[CandidateSchema]


class CompanySchema(ModelSchema):
    user: UserSchema | None = None
    class Meta:
        model = Company
        fields = "__all__"

class CompanyProfileSchema(BaseResponseSchema):
    data: CompanySchema | None = None

class CompanyProfileListResponse(PaginatedResponse):
    data: list[CompanySchema]


