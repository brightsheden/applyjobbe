from django.contrib import admin
from .models import Job, JobApplication, Interview


class JobApplicationInline(admin.TabularInline):
    model = JobApplication
    extra = 0
    readonly_fields = ("created_at",)


class InterviewInline(admin.TabularInline):
    model = Interview
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "employer",
        "employment_type",
        "monthly_salary",
        "status",
        "country",
        "city",
        "industry",
        "created_at",
    )
    list_filter = ("status", "employment_type", "industry", "country", "created_at")
    search_fields = ("title", "description", "employer__name", "city", "country")
    inlines = [JobApplicationInline, InterviewInline]


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "job", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = (
        "candidate__user__username",
        "candidate__user__email",
        "job__title",
        "job__employer__name",
    )


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = (
        "job",
        "candidate",
        "employer",
        "status",
        "schedule_date_and_time",
        "panel_name",
        "created_at",
    )
    list_filter = ("status", "schedule_date_and_time", "created_at")
    search_fields = (
        "job__title",
        "candidate__user__username",
        "candidate__user__email",
        "employer__name",
        "panel_name",
    )
