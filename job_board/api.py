import logging
from django.core.paginator import Paginator
from django.db.models import Q
from ninja import Router, File
from ninja.files import UploadedFile

from core.schemas import BaseResponseSchema, ErrorResponse
from authy.models import Company, Candidate
from job_board.models import Job, JobApplication, Interview
from job_board.schemas import (
    JobSchema,
    JobResponse,
    JobListResponse,
    JobRequestSchema,
    JobApplicationSchema,
    JobApplicationResponse,
    JobApplicationListResponse,
    JobApplicationRequestSchema,
    JobApplicationStatusUpdateSchema,
    InterviewSchema,
    InterviewResponse,
    InterviewListResponse,
    InterviewRequestSchema,
    InterviewUpdateRequestSchema,
    InterviewStatusUpdateSchema,
)

logger = logging.getLogger(__name__)
router = Router(tags=["Job Board"])




@router.post("/create_job", response={200: JobResponse, 400: ErrorResponse, 403: ErrorResponse, 500: ErrorResponse})
def create_job(request, payload: JobRequestSchema):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        if not company:
            return 403, ErrorResponse(message="Company not found")

        job = Job.objects.create(
            employer=company,
            title=payload.title,
            description=payload.description,
            monthly_salary=payload.monthly_salary,
            country=payload.country,
            city=payload.city,
            employment_type=payload.employment_type or Job.EmploymentType.FULL_TIME,
            industry=payload.industry,
        )
        return 200, JobResponse(data=job)
    except Exception as e:
        logger.error(f"Error creating job: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.patch("/update_job/{job_id}", response={200: JobResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def update_job(request, job_id: int, payload: JobRequestSchema):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        job = Job.objects.get(id=job_id)
        if company and job.employer_id != company.id:
            return 403, ErrorResponse(message="You do not have permission to update this job")

        if payload.title:
            job.title = payload.title
        if payload.description:
            job.description = payload.description
        if payload.monthly_salary is not None:
            job.monthly_salary = payload.monthly_salary
        if payload.country:
            job.country = payload.country
        if payload.city:
            job.city = payload.city
        if payload.employment_type:
            job.employment_type = payload.employment_type
        if payload.industry:
            job.industry = payload.industry
        job.save()
        return 200, JobResponse(data=job)
    except Job.DoesNotExist:
        return 404, ErrorResponse(message="Job not found")
    except Exception as e:
        logger.error(f"Error updating job: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.delete("/delete_job/{job_id}", response={200: BaseResponseSchema, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def delete_job(request, job_id: int):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        job = Job.objects.get(id=job_id)
        if company and job.employer_id != company.id:
            return 403, ErrorResponse(message="You do not have permission to delete this job")

        job.delete()
        return 200, BaseResponseSchema(message="Job deleted successfully")
    except Job.DoesNotExist:
        return 404, ErrorResponse(message="Job not found")
    except Exception as e:
        logger.error(f"Error deleting job: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/get_job/{job_id}", auth=None, response={200: JobResponse, 404: ErrorResponse, 500: ErrorResponse})
def get_job(request, job_id: int):
    try:
        job = Job.objects.select_related("employer").get(id=job_id)
        return 200, JobResponse(data=job)
    except Job.DoesNotExist:
        return 404, ErrorResponse(message="Job not found")
    except Exception as e:
        logger.error(f"Error getting job: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/get_jobs", auth=None, response={200: JobListResponse, 400: ErrorResponse, 500: ErrorResponse})
def get_jobs(request, search: str = None, page: int = 1, page_size: int = 10):
    try:
        jobs = Job.objects.select_related("employer").all()
        if search:
            jobs = jobs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(country__icontains=search)
                | Q(city__icontains=search)
                | Q(employment_type__icontains=search)
                | Q(industry__icontains=search)
            )

        paginator = Paginator(jobs, page_size)
        page_obj = paginator.get_page(page)
        return 200, JobListResponse(
            data=page_obj.object_list,
            total=paginator.count,
            page=page,
            page_size=page_size,
            has_next=page_obj.has_next(),
            has_previous=page_obj.has_previous(),
        )
    except Exception as e:
        logger.error(f"Error getting jobs: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/company_jobs", response={200: JobListResponse, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def company_jobs(request, page: int = 1, page_size: int = 10):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        if not company:
            return 404, ErrorResponse(message="Company not found")

        jobs = Job.objects.select_related("employer").filter(employer=company)
        paginator = Paginator(jobs, page_size)
        page_obj = paginator.get_page(page)
        return 200, JobListResponse(
            data=page_obj.object_list,
            total=paginator.count,
            page=page,
            page_size=page_size,
            has_next=page_obj.has_next(),
            has_previous=page_obj.has_previous(),
        )
    except Exception as e:
        logger.error(f"Error getting company jobs: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))




@router.post("/job/{job_id}/apply", response={200: JobApplicationResponse, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def apply_for_job(request, job_id: int, payload: JobApplicationRequestSchema, cv_file: UploadedFile| None=File(None)):
    try:
        user = request.auth or request.user
        candidate = getattr(user, "candidate", None)
        if not candidate:
            return 400, ErrorResponse(message="Candidate profile not found")

        job = Job.objects.get(id=job_id)
        if job.status == Job.Status.CLOSED:
            return 400, ErrorResponse(message="Job is closed")

        if JobApplication.objects.filter(candidate=candidate, job=job).exists():
            return 400, ErrorResponse(message="You have already applied for this job")

        job_application = JobApplication.objects.create(
            candidate=candidate,
            job=job,
            cover_letter=payload.cover_letter,
        )

        if cv_file:
            job_application.cv_file = cv_file
            job_application.save(update_fields=["cv_file"])

        return 200, JobApplicationResponse(data=job_application)
    except Job.DoesNotExist:
        return 404, ErrorResponse(message="Job not found")
    except Exception as e:
        logger.error(f"Error applying for job: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/job/{job_id}/applications", response={200: JobApplicationListResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def get_job_applications(request, job_id: int, page: int = 1, page_size: int = 10):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        job = Job.objects.get(id=job_id)
        if company and job.employer_id != company.id:
            return 403, ErrorResponse(message="You do not have permission to view these applications")

        applications = JobApplication.objects.select_related("job", "job__employer", "candidate", "candidate__user").filter(job=job)
        paginator = Paginator(applications, page_size)
        page_obj = paginator.get_page(page)
        return 200, JobApplicationListResponse(
            data=page_obj.object_list,
            total=paginator.count,
            page=page,
            page_size=page_size,
            has_next=page_obj.has_next(),
            has_previous=page_obj.has_previous(),
        )
    except Job.DoesNotExist:
        return 404, ErrorResponse(message="Job not found")
    except Exception as e:
        logger.error(f"Error getting applications: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/candidate/applications", response={200: JobApplicationListResponse, 400: ErrorResponse, 500: ErrorResponse})
def candidate_job_applications(request, page: int = 1, page_size: int = 10):
    try:
        user = request.auth or request.user
        candidate = getattr(user, "candidate", None)
        if not candidate:
            return 400, ErrorResponse(message="Candidate profile not found")

        applications = JobApplication.objects.select_related("job", "job__employer", "candidate", "candidate__user").filter(candidate=candidate)
        paginator = Paginator(applications, page_size)
        page_obj = paginator.get_page(page)
        return 200, JobApplicationListResponse(
            data=page_obj.object_list,
            total=paginator.count,
            page=page,
            page_size=page_size,
            has_next=page_obj.has_next(),
            has_previous=page_obj.has_previous(),
        )
    except Exception as e:
        logger.error(f"Error getting candidate applications: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/employer/applications", response={200: JobApplicationListResponse, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def employer_job_applications(request, page: int = 1, page_size: int = 10):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        if not company:
            return 404, ErrorResponse(message="Company not found")

        applications = JobApplication.objects.select_related("job", "job__employer", "candidate", "candidate__user").filter(job__employer=company)
        paginator = Paginator(applications, page_size)
        page_obj = paginator.get_page(page)
        return 200, JobApplicationListResponse(
            data=page_obj.object_list,
            total=paginator.count,
            page=page,
            page_size=page_size,
            has_next=page_obj.has_next(),
            has_previous=page_obj.has_previous(),
        )
    except Exception as e:
        logger.error(f"Error getting employer applications: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/application/{application_id}", response={200: JobApplicationResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def get_application_by_id(request, application_id: int):
    try:
        user = request.auth or request.user
        application = JobApplication.objects.select_related("job", "job__employer", "candidate", "candidate__user").get(id=application_id)

        is_candidate = hasattr(user, "candidate") and application.candidate_id == user.candidate.id
        is_employer = hasattr(user, "company") and application.job.employer_id == user.company.id
        if not (is_candidate or is_employer):
            return 403, ErrorResponse(message="You do not have permission to view this application")

        return 200, JobApplicationResponse(data=application)
    except JobApplication.DoesNotExist:
        return 404, ErrorResponse(message="Application not found")
    except Exception as e:
        logger.error(f"Error getting application: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.patch("/application/{application_id}/status", response={200: JobApplicationResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def update_application_status(request, application_id: int, payload: JobApplicationStatusUpdateSchema):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        application = JobApplication.objects.select_related("job", "job__employer", "candidate", "candidate__user").get(id=application_id)
        if company and application.job.employer_id != company.id:
            return 403, ErrorResponse(message="You do not have permission to update this application")

        application.status = payload.status
        application.save(update_fields=["status"])
        return 200, JobApplicationResponse(data=application)
    except JobApplication.DoesNotExist:
        return 404, ErrorResponse(message="Application not found")
    except Exception as e:
        logger.error(f"Error updating application status: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.delete("/application/{application_id}/withdraw", response={200: BaseResponseSchema, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def withdraw_application(request, application_id: int):
    try:
        user = request.auth or request.user
        candidate = getattr(user, "candidate", None)
        application = JobApplication.objects.get(id=application_id)
        if candidate and application.candidate_id != candidate.id:
            return 403, ErrorResponse(message="You do not have permission to withdraw this application")

        application.status = JobApplication.Status.WITHDRAWN
        application.save(update_fields=["status"])
        return 200, BaseResponseSchema(message="Application withdrawn successfully")
    except JobApplication.DoesNotExist:
        return 404, ErrorResponse(message="Application not found")
    except Exception as e:
        logger.error(f"Error withdrawing application: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.post("/create_interview", response={200: InterviewResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def create_interview(request, payload: InterviewRequestSchema):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        if not company:
            return 403, ErrorResponse(message="Company not found")

        job = Job.objects.get(id=payload.job_id)
        candidate = Candidate.objects.get(id=payload.candidate_id)
        application = None
        if payload.application_id:
            application = JobApplication.objects.filter(id=payload.application_id).first()

        interview = Interview.objects.create(
            employer=company,
            job=job,
            candidate=candidate,
            application=application,
            link=payload.link,
            schedule_date_and_time=payload.schedule_date_and_time,
            panel_name=payload.panel_name,
            notes=payload.notes,
        )
        if application:
            application.status = JobApplication.Status.INTERVIEWED
            application.save(update_fields=["status"])

        return 200, InterviewResponse(data=interview)
    except Job.DoesNotExist:
        return 404, ErrorResponse(message="Job not found")
    except Candidate.DoesNotExist:
        return 404, ErrorResponse(message="Candidate not found")
    except Exception as e:
        logger.error(f"Error creating interview: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/interview/{interview_id}", response={200: InterviewResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def get_interview(request, interview_id: int):
    try:
        user = request.auth or request.user
        interview = Interview.objects.select_related("employer", "job", "candidate", "candidate__user").get(id=interview_id)
        is_candidate = hasattr(user, "candidate") and interview.candidate_id == user.candidate.id
        is_employer = hasattr(user, "company") and interview.employer_id == user.company.id
        if not (is_candidate or is_employer):
            return 403, ErrorResponse(message="You do not have permission to view this interview")

        return 200, InterviewResponse(data=interview)
    except Interview.DoesNotExist:
        return 404, ErrorResponse(message="Interview not found")
    except Exception as e:
        logger.error(f"Error getting interview: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.patch("/interview/{interview_id}", response={200: InterviewResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def update_interview(request, interview_id: int, payload: InterviewUpdateRequestSchema):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        interview = Interview.objects.select_related("employer", "job", "candidate", "candidate__user").get(id=interview_id)
        if company and interview.employer_id != company.id:
            return 403, ErrorResponse(message="You do not have permission to update this interview")

        if payload.link:
            interview.link = payload.link
        if payload.schedule_date_and_time:
            interview.schedule_date_and_time = payload.schedule_date_and_time
        if payload.panel_name:
            interview.panel_name = payload.panel_name
        if payload.status:
            interview.status = payload.status
        if payload.notes:
            interview.notes = payload.notes
        interview.save()
        return 200, InterviewResponse(data=interview)
    except Interview.DoesNotExist:
        return 404, ErrorResponse(message="Interview not found")
    except Exception as e:
        logger.error(f"Error updating interview: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.delete("/interview/{interview_id}", response={200: BaseResponseSchema, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def delete_interview(request, interview_id: int):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        interview = Interview.objects.get(id=interview_id)
        if company and interview.employer_id != company.id:
            return 403, ErrorResponse(message="You do not have permission to delete this interview")

        interview.delete()
        return 200, BaseResponseSchema(message="Interview deleted successfully")
    except Interview.DoesNotExist:
        return 404, ErrorResponse(message="Interview not found")
    except Exception as e:
        logger.error(f"Error deleting interview: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.patch("/interview/{interview_id}/status", response={200: InterviewResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def update_interview_status(request, interview_id: int, payload: InterviewStatusUpdateSchema):
    try:
        user = request.auth or request.user
        interview = Interview.objects.select_related("employer", "job", "candidate", "candidate__user").get(id=interview_id)

        is_candidate = hasattr(user, "candidate") and interview.candidate_id == user.candidate.id
        is_employer = hasattr(user, "company") and interview.employer_id == user.company.id
        if not (is_candidate or is_employer):
            return 403, ErrorResponse(message="You do not have permission to update this interview status")

        interview.status = payload.status
        interview.save(update_fields=["status"])
        return 200, InterviewResponse(data=interview)
    except Interview.DoesNotExist:
        return 404, ErrorResponse(message="Interview not found")
    except Exception as e:
        logger.error(f"Error updating interview status: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/candidate/interviews", response={200: InterviewListResponse, 400: ErrorResponse, 500: ErrorResponse})
def candidate_interviews(request, page: int = 1, page_size: int = 10):
    try:
        user = request.auth or request.user
        candidate = getattr(user, "candidate", None)
        if not candidate:
            return 400, ErrorResponse(message="Candidate profile not found")

        interviews = Interview.objects.select_related("employer", "job", "candidate", "candidate__user").filter(candidate=candidate)
        paginator = Paginator(interviews, page_size)
        page_obj = paginator.get_page(page)
        return 200, InterviewListResponse(
            data=page_obj.object_list,
            total=paginator.count,
            page=page,
            page_size=page_size,
            has_next=page_obj.has_next(),
            has_previous=page_obj.has_previous(),
        )
    except Exception as e:
        logger.error(f"Error getting candidate interviews: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))


@router.get("/employer/interviews", response={200: InterviewListResponse, 400: ErrorResponse, 404: ErrorResponse, 500: ErrorResponse})
def employer_interviews(request, page: int = 1, page_size: int = 10):
    try:
        user = request.auth or request.user
        company = getattr(user, "company", None)
        if not company:
            return 404, ErrorResponse(message="Company not found")

        interviews = Interview.objects.select_related("employer", "job", "candidate", "candidate__user").filter(employer=company)
        paginator = Paginator(interviews, page_size)
        page_obj = paginator.get_page(page)
        return 200, InterviewListResponse(
            data=page_obj.object_list,
            total=paginator.count,
            page=page,
            page_size=page_size,
            has_next=page_obj.has_next(),
            has_previous=page_obj.has_previous(),
        )
    except Exception as e:
        logger.error(f"Error getting employer interviews: {str(e)}", exc_info=True)
        return 500, ErrorResponse(message="An error occurred", detail=str(e))
