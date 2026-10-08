import logging
import threading
import string
from django.db import models
from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import close_old_connections
from django.utils import timezone

from random import randint, choices
from django.conf import settings

from core.models import BaseModel
from core.clients import EmailClient


logger = logging.getLogger(__name__)






class User(AbstractUser):
    class USERTYPE(models.TextChoices):
        CANDIDATE = "CANDIDATE", "Candidate"
        EMPLOYER = "EMPLOYER", "Employer"
        ADMIN = "ADMIN", "Admin"

    user_type = models.CharField(max_length=25, choices=USERTYPE.choices, default=USERTYPE.CANDIDATE)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, unique=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, default="Nigeria", blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    picture = models.ImageField(upload_to="profile_pictures/", blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name="referrals")
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)

    REQUIRED_FIELDS = ["email", "phone_number"]

    def __str__(self):
        return self.username

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.username

    @property
    def candidate_profile(self):
        return getattr(self, "candidate", None)

    @property
    def employer(self):
        return getattr(self, "company", None)

    @property
    def company_profile(self):
        return getattr(self, "company", None)

    @property
    def employer_profile(self):
        return getattr(self, "company", None)

    def has_business_details_setup(self):
        return self.business_details.filter(
            name__isnull=False,
            industry__isnull=False,
            account_type__isnull=False,
        ).exclude(
            name="",
        ).exclude(
            industry="",
        ).exclude(
            account_type="",
        ).exists()

    @staticmethod
    def notify(
        user,
        *,
        title: str,
        message: str,
        notification_type: str = "system",
        action_url: str | None = None,
        metadata: dict | None = None,
    ):
        return Notification.objects.create(
            user=user,
            title=title,
            message=message,
            type=notification_type,
            action_url=action_url,
            metadata=metadata or {},
        )

    def create_notification(
        self,
        *,
        title: str,
        message: str,
        notification_type: str = "system",
        action_url: str | None = None,
        metadata: dict | None = None,
    ):
        return self.notify(
            self,
            title=title,
            message=message,
            notification_type=notification_type,
            action_url=action_url,
            metadata=metadata,
        )
    
    def send_email(
        self,
        subject: str | None = None,
        context: dict | None = None,
        template_name: str | None = None,
        *,
        send_async: bool = True,
    ):
        """
        Send an email to this user.

        By default the actual email request runs in a daemon thread so views are
        not blocked by the SMTP/API round trip.
        """
        email = self.email
        context = dict(context or {})

        def send():
            # close_old_connections()
            try:
                client = EmailClient()
                return client.send_email(
                    to=email,
                    subject=subject,
                    context=context,
                    template_name=template_name,
                )
            except Exception:
                logger.exception("Failed to send email '%s' to %s", subject, email)
            finally:
                close_old_connections()

        if not send_async:
            return send()

        thread = threading.Thread(
            target=send,
            name=f"user-email-{self.pk or 'unknown'}",
            daemon=True,
        )
        thread.start()
        return thread



class OTP(BaseModel):
    DEFAULT_EXPIRY_MINUTES = 5

    class Purpose(models.TextChoices):
        ACCOUNT_VERIFICATION = "ACCOUNT_VERIFICATION", "Account verification"
        PASSWORD_RESET = "PASSWORD_RESET", "Password reset"
        LOGIN = "LOGIN", "Login"
        EMAIL_VERIFICATION = "EMAIL_VERIFICATION", "Email verification"
        PHONE_VERIFICATION = "PHONE_VERIFICATION", "Phone verification"

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="otps",
        blank=True,
        null=True,
    )
    code = models.CharField(max_length=6, db_index=True)
    purpose = models.CharField(
        max_length=25,
        choices=Purpose.choices,
        default=Purpose.ACCOUNT_VERIFICATION,
    )
    channel = models.CharField(
        max_length=10,
        choices=Channel.choices,
        default=Channel.EMAIL,
    )
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(blank=True, null=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code", "purpose"]),
            models.Index(fields=["user", "purpose", "is_used"]),
        ]

    def clean(self):
        super().clean()
        if self.channel == self.Channel.EMAIL and not self.email:
            raise ValidationError({"email": "Email is required for email OTPs."})
        if self.channel == self.Channel.SMS and not self.phone_number:
            raise ValidationError({"phone_number": "Phone number is required for SMS OTPs."})
        if self.max_attempts < 1:
            raise ValidationError({"max_attempts": "Max attempts must be at least 1."})

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_locked(self):
        return self.attempt_count >= self.max_attempts

    @classmethod
    def generate_otp(
        cls,
        *,
        user=None,
        purpose=Purpose.ACCOUNT_VERIFICATION,
        channel=Channel.EMAIL,
        email=None,
        phone_number=None,
        expires_in_minutes=DEFAULT_EXPIRY_MINUTES,
        max_attempts=5,
    ):
        if user and channel == cls.Channel.EMAIL and not email:
            email = user.email
        if user and channel == cls.Channel.SMS and not phone_number:
            phone_number = user.phone_number

        otp = cls(
            user=user,
            purpose=purpose,
            channel=channel,
            email=email,
            phone_number=phone_number,
            expires_at=timezone.now() + timedelta(minutes=expires_in_minutes),
            max_attempts=max_attempts,
        )
        otp.save()
        return otp

    def _generate_code(self):
        if self.channel == self.Channel.EMAIL:
            return str(randint(1000, 9999))
        return str(randint(100000, 999999))

    def mark_as_used(self):
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at", "updated_at"])

    def validate_otp(self, code):
        submitted_code = str(code).strip()

        if self.is_used:
            return False, "OTP has already been used."

        if self.is_expired:
            return False, "OTP has expired."

        if self.is_locked:
            return False, "Too many invalid attempts. Please request a new OTP."

        if self.code != submitted_code:
            self.attempt_count += 1
            self.save(update_fields=["attempt_count", "updated_at"])
            if self.is_locked:
                return False, "Too many invalid attempts. Please request a new OTP."
            return False, "Invalid OTP."

        self.mark_as_used()
        return True, "OTP verified successfully."

    def save(self, *args, **kwargs):
        if self.user:
            if self.channel == self.Channel.EMAIL and not self.email:
                self.email = self.user.email
            if self.channel == self.Channel.SMS and not self.phone_number:
                self.phone_number = self.user.phone_number

        if not self.code:
            self.code = self._generate_code()

        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=self.DEFAULT_EXPIRY_MINUTES)

        self.full_clean()
        return super().save(*args, **kwargs)
    

    def __str__(self):
        recipient = self.email or self.phone_number or (self.user.username if self.user else "unknown")
        return f"{self.purpose} OTP for {recipient}"


class Notification(BaseModel):
    class NotificationType(models.TextChoices):
        SYSTEM = "system", "System"
        OFFER = "offer", "Offer"
        WALLET = "wallet", "Wallet"
        DESIGN = "design", "Design"
        SECURITY = "security", "Security"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    action_url = models.CharField(max_length=255, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"], name="authy_notif_user_unread_idx"),
            models.Index(fields=["user", "type", "-created_at"], name="authy_notif_user_type_idx"),
        ]

    def mark_read(self):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at", "updated_at"])

    def __str__(self):
        return f"{self.user} - {self.title}"


class Candidate(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="candidate",
    )
    primary_role = models.CharField(max_length=255)
    year_of_experience = models.PositiveIntegerField(default=0)
    highest_education = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        full_name = self.user.get_full_name() if hasattr(self.user, "get_full_name") else str(self.user)
        if self.primary_role:
            return f"{full_name} - {self.primary_role}"
        return full_name

    @property
    def years_of_experience(self):
        return self.year_of_experience

    @years_of_experience.setter
    def years_of_experience(self, value):
        self.year_of_experience = value


class CandidateFile(BaseModel):
    class FileType(models.TextChoices):
        CV = "cv", "CV"
        VIDEO_INTRO = "video_intro", "Video Intro"

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="files",
    )
    file = models.FileField(upload_to="candidate_files/")
    type = models.CharField(
        max_length=20,
        choices=FileType.choices,
        default=FileType.CV,
    )

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.type == "video intro":
            self.type = self.FileType.VIDEO_INTRO

    def save(self, *args, **kwargs):
        if self.type == "video intro":
            self.type = self.FileType.VIDEO_INTRO
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.candidate} - {self.get_type_display()}"


class Reference(BaseModel):
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="references",
    )
    name = models.CharField(max_length=255)
    org = models.CharField(max_length=255, verbose_name="Organization")
    email = models.EmailField()
    phone = models.CharField(max_length=20)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.org}) - {self.candidate}"


class Education(BaseModel):
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="educations",
    )
    institution = models.CharField(max_length=255)
    degree = models.CharField(max_length=255)
    course = models.CharField(max_length=255)
    year = models.PositiveIntegerField(blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ["-start_date", "-created_at"]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be earlier than start date."})

    def __str__(self):
        return f"{self.degree} in {self.course} - {self.institution}"


class Experience(BaseModel):
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="experiences",
    )
    company_name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    is_present = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_present", "-start_date", "-created_at"]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be earlier than start date."})

    @property
    def enddate(self):
        return self.end_date

    @enddate.setter
    def enddate(self, value):
        self.end_date = value

    def __str__(self):
        return f"{self.title} at {self.company_name}"


class Skill(BaseModel):
    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"
    name = models.CharField(max_length=255)
    level = models.CharField(max_length=255, choices=Level.choices, default=Level.BEGINNER)
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="skills")


    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(BaseModel):
    name = models.CharField(max_length=255)


    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SubCategory(BaseModel):
    name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="subcategories")


    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class Industry(BaseModel):
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Company(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company",
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    registration_number = models.CharField(max_length=100, blank=True, null=True)
    industry = models.CharField(max_length=255, blank=True, null=True)
    size = models.CharField(max_length=100, blank=True, null=True)
    year_founded = models.PositiveIntegerField(blank=True, null=True)
    website_url = models.URLField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    postal = models.CharField(max_length=30, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"Company ({self.user})"

    @property
    def postal_code(self):
        return self.postal

    @postal_code.setter
    def postal_code(self, value):
        self.postal = value


# Alias for employer
Employer = Company