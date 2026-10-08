from core.models import BaseModel
from django.db import models
from authy.models import Company, Candidate


class Job(BaseModel):
    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full Time"
        PART_TIME = "part_time", "Part-time"
        CONTRACT = "contract", "Contract"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        DRAFT = "draft", "Draft"

    employer = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    monthly_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
    )
    country = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    industry = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.employment_type in ["full time", "full-time"]:
            self.employment_type = self.EmploymentType.FULL_TIME
        elif self.employment_type in ["part time", "part-time"]:
            self.employment_type = self.EmploymentType.PART_TIME

    def save(self, *args, **kwargs):
        if self.employment_type in ["full time", "full-time"]:
            self.employment_type = self.EmploymentType.FULL_TIME
        elif self.employment_type in ["part time", "part-time"]:
            self.employment_type = self.EmploymentType.PART_TIME
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} at {self.employer.name}"


class JobApplication(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SHORT_LISTED = "short_listed", "Short-listed"
        INTERVIEWED = "interviewed", "Interviewed"
        OFFERED = "offered", "Offered"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="job_applications",
    )
    cover_letter = models.TextField(blank=True, null=True)
    cv_file = models.FileField(upload_to="cv", blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "candidate"],
                name="unique_job_candidate_application",
            )
        ]

    def clean(self):
        super().clean()
        if self.status == "short-listed":
            self.status = self.Status.SHORT_LISTED

    def save(self, *args, **kwargs):
        if self.status == "short-listed":
            self.status = self.Status.SHORT_LISTED
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.candidate} - {self.job.title} ({self.get_status_display()})"


class Interview(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        RESCHEDULED = "rescheduled", "Rescheduled"

    employer = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="interviews",
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="interviews",
    )
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="interviews",
    )
    application = models.ForeignKey(
        JobApplication,
        on_delete=models.SET_NULL,
        related_name="interviews",
        blank=True,
        null=True,
    )
    link = models.URLField(max_length=500, blank=True, null=True)
    schedule_date_and_time = models.DateTimeField(verbose_name="Schedule date and time")
    panel_name = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-schedule_date_and_time"]

    @property
    def scheduled_at(self):
        return self.schedule_date_and_time

    @scheduled_at.setter
    def scheduled_at(self, value):
        self.schedule_date_and_time = value

    def __str__(self):
        formatted_time = (
            self.schedule_date_and_time.strftime("%Y-%m-%d %H:%M")
            if self.schedule_date_and_time
            else "Unscheduled"
        )
        return f"Interview: {self.candidate} for {self.job.title} ({formatted_time})"
