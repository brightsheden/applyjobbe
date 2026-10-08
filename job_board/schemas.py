from ninja import ModelSchema, Schema
import datetime
from core.schemas import BaseResponseSchema, PaginatedResponse
from authy.schemas import CompanySchema, CandidateSchema
from job_board.models import Job, JobApplication, Interview


class JobSchema(ModelSchema):
    employer: CompanySchema | None = None

    class Meta:
        model = Job
        fields = "__all__"


class JobResponse(BaseResponseSchema):
    data: JobSchema | None = None


class JobListResponse(PaginatedResponse):
    data: list[JobSchema] | None = None


class JobRequestSchema(Schema):
    title: str | None = None
    description: str | None = None
    monthly_salary: float | None = None
    country: str | None = None
    city: str | None = None
    employment_type: str | None = None
    industry: str | None = None


class JobApplicationSchema(ModelSchema):
    job: JobSchema | None = None
    candidate: CandidateSchema | None = None

    class Meta:
        model = JobApplication
        fields = "__all__"


class JobApplicationResponse(BaseResponseSchema):
    data: JobApplicationSchema | None = None


class JobApplicationListResponse(PaginatedResponse):
    data: list[JobApplicationSchema] | None = None


class JobApplicationRequestSchema(Schema):
    cover_letter: str | None = None


class JobApplicationStatusUpdateSchema(Schema):
    status: str


class InterviewSchema(ModelSchema):
    job: JobSchema | None = None
    candidate: CandidateSchema | None = None
    employer: CompanySchema | None = None

    class Meta:
        model = Interview
        fields = "__all__"


class InterviewResponse(BaseResponseSchema):
    data: InterviewSchema | None = None


class InterviewListResponse(PaginatedResponse):
    data: list[InterviewSchema] | None = None


class InterviewRequestSchema(Schema):
    job_id: int
    candidate_id: int
    application_id: int | None = None
    link: str | None = None
    schedule_date_and_time: datetime.datetime | None = None
    panel_name: str | None = None
    notes: str | None = None


class InterviewUpdateRequestSchema(Schema):
    link: str | None = None
    schedule_date_and_time: datetime.datetime | None = None
    panel_name: str | None = None
    status: str | None = None
    notes: str | None = None


class InterviewStatusUpdateSchema(Schema):
    status: str