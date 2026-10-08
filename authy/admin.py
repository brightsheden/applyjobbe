from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Candidate,
    CandidateFile,
    Company,
    Education,
    Experience,
    Notification,
    OTP,
    Reference,
    User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "phone_number", "is_email_verified", "is_staff")
    search_fields = ("username", "email", "phone_number", "first_name", "last_name")


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ("code", "purpose", "channel", "email", "phone_number", "is_used", "expires_at", "created_at")
    list_filter = ("purpose", "channel", "is_used", "created_at")
    search_fields = ("code", "email", "phone_number", "user__username")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "type", "is_read", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("title", "message", "user__username", "user__email")


class CandidateFileInline(admin.TabularInline):
    model = CandidateFile
    extra = 1


class ReferenceInline(admin.TabularInline):
    model = Reference
    extra = 1


class EducationInline(admin.TabularInline):
    model = Education
    extra = 1


class ExperienceInline(admin.TabularInline):
    model = Experience
    extra = 1


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("user", "primary_role", "year_of_experience", "highest_education", "created_at")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "primary_role", "highest_education")
    list_filter = ("primary_role", "highest_education", "created_at")
    inlines = [CandidateFileInline, ReferenceInline, EducationInline, ExperienceInline]


@admin.register(CandidateFile)
class CandidateFileAdmin(admin.ModelAdmin):
    list_display = ("candidate", "type", "file", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("candidate__user__username", "candidate__user__email")


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ("candidate", "name", "org", "email", "phone", "created_at")
    search_fields = ("name", "org", "email", "phone", "candidate__user__username")


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "institution", "degree", "course", "year", "start_date", "end_date")
    search_fields = ("institution", "degree", "course", "candidate__user__username")


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = ("candidate", "company_name", "title", "start_date", "end_date", "is_present")
    list_filter = ("is_present",)
    search_fields = ("company_name", "title", "candidate__user__username")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "email", "industry", "size", "country", "city", "created_at")
    list_filter = ("industry", "country", "size", "created_at")
    search_fields = ("name", "email", "registration_number", "industry", "user__username", "user__email")


