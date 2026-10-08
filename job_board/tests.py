import datetime
from django.test import TestCase, Client
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from authy.models import User, Company, Candidate
from job_board.models import Job, JobApplication, Interview


class JobBoardApiTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Employer User & Company
        self.employer_user = User.objects.create_user(
            username="employer1",
            email="employer1@company.com",
            phone_number="1234567890",
            user_type=User.USERTYPE.EMPLOYER,
            password="testpassword123",
        )
        self.company = Company.objects.create(
            user=self.employer_user,
            name="Acme Corp",
            industry="Technology",
            city="Lagos",
            country="Nigeria",
        )
        self.employer_token = str(RefreshToken.for_user(self.employer_user).access_token)
        self.employer_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.employer_token}"}

        # Create Second Employer (for permission tests)
        self.employer_user2 = User.objects.create_user(
            username="employer2",
            email="employer2@company.com",
            phone_number="1234567891",
            user_type=User.USERTYPE.EMPLOYER,
            password="testpassword123",
        )
        self.company2 = Company.objects.create(
            user=self.employer_user2,
            name="Beta Inc",
            industry="Healthcare",
        )
        self.employer_token2 = str(RefreshToken.for_user(self.employer_user2).access_token)
        self.employer_headers2 = {"HTTP_AUTHORIZATION": f"Bearer {self.employer_token2}"}

        # Create Candidate User & Candidate Profile
        self.candidate_user = User.objects.create_user(
            username="candidate1",
            email="candidate1@example.com",
            phone_number="0987654321",
            first_name="Jane",
            last_name="Doe",
            user_type=User.USERTYPE.CANDIDATE,
            password="testpassword123",
        )
        self.candidate = Candidate.objects.create(
            user=self.candidate_user,
            primary_role="Backend Developer",
            year_of_experience=4,
        )
        self.candidate_token = str(RefreshToken.for_user(self.candidate_user).access_token)
        self.candidate_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.candidate_token}"}

        # Create a Job
        self.job = Job.objects.create(
            employer=self.company,
            title="Senior Python Engineer",
            description="Build scalable APIs using Django and Ninja.",
            monthly_salary=5000.00,
            country="Nigeria",
            city="Lagos",
            employment_type=Job.EmploymentType.FULL_TIME,
            industry="Technology",
            status=Job.Status.OPEN,
        )

    # =========================================================================
    # Job CRUD Tests
    # =========================================================================

    def test_create_job_by_employer(self):
        payload = {
            "title": "Frontend Engineer",
            "description": "React / TypeScript specialist.",
            "monthly_salary": 4500,
            "country": "Nigeria",
            "city": "Abuja",
            "employment_type": "full_time",
            "industry": "Fintech",
            "status": "open",
        }
        res = self.client.post(
            "/api/jobs/create_job",
            data=payload,
            content_type="application/json",
            **self.employer_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["title"], "Frontend Engineer")
        self.assertEqual(data["data"]["employer"]["name"], "Acme Corp")

    def test_candidate_cannot_create_job(self):
        payload = {
            "title": "Illegal Job",
            "description": "Should fail",
        }
        res = self.client.post(
            "/api/jobs/create_job",
            data=payload,
            content_type="application/json",
            **self.candidate_headers,
        )
        self.assertEqual(res.status_code, 403)

    def test_update_job_by_owner(self):
        payload = {"title": "Lead Python Engineer", "monthly_salary": 6500}
        res = self.client.patch(
            f"/api/jobs/update_job/{self.job.id}",
            data=payload,
            content_type="application/json",
            **self.employer_headers,
        )
        self.assertEqual(res.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "Lead Python Engineer")
        self.assertEqual(float(self.job.monthly_salary), 6500.0)

    def test_other_employer_cannot_update_job(self):
        payload = {"title": "Hacked Title"}
        res = self.client.patch(
            f"/api/jobs/update_job/{self.job.id}",
            data=payload,
            content_type="application/json",
            **self.employer_headers2,
        )
        self.assertEqual(res.status_code, 403)

    def test_public_get_jobs_and_get_job(self):
        # Public listing
        res = self.client.get("/api/jobs/get_jobs")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total"], 1)

        # Single job detail
        res = self.client.get(f"/api/jobs/get_job/{self.job.id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"]["id"], self.job.id)

    def test_company_jobs_endpoint(self):
        res = self.client.get("/api/jobs/company_jobs", **self.employer_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["data"][0]["id"], self.job.id)

    # =========================================================================
    # Application Tests
    # =========================================================================

    def test_candidate_apply_for_job(self):
        payload = {"cover_letter": "I am passionate about building APIs."}
        res = self.client.post(
            f"/api/jobs/job/{self.job.id}/apply",
            data=payload,
            content_type="application/json",
            **self.candidate_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["status"], JobApplication.Status.PENDING)
        self.assertEqual(data["data"]["candidate"]["primary_role"], "Backend Developer")

        # Duplicate application rejected
        dup_res = self.client.post(
            f"/api/jobs/job/{self.job.id}/apply",
            data=payload,
            content_type="application/json",
            **self.candidate_headers,
        )
        self.assertEqual(dup_res.status_code, 400)

    def test_cannot_apply_to_closed_job(self):
        self.job.status = Job.Status.CLOSED
        self.job.save(update_fields=["status"])

        payload = {"cover_letter": "Please consider me."}
        res = self.client.post(
            f"/api/jobs/job/{self.job.id}/apply",
            data=payload,
            content_type="application/json",
            **self.candidate_headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_employer_and_candidate_applications_list(self):
        # Create an application
        app = JobApplication.objects.create(
            job=self.job,
            candidate=self.candidate,
            cover_letter="Cover letter here",
            status=JobApplication.Status.PENDING,
        )

        # Candidate view
        res = self.client.get("/api/jobs/candidate/applications", **self.candidate_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 1)

        # Employer view for job
        res = self.client.get(f"/api/jobs/job/{self.job.id}/applications", **self.employer_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 1)

        # Employer view for all jobs
        res = self.client.get("/api/jobs/employer/applications", **self.employer_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 1)

        # Get application by ID
        res = self.client.get(f"/api/jobs/application/{app.id}", **self.candidate_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"]["id"], app.id)

    def test_update_application_status(self):
        app = JobApplication.objects.create(
            job=self.job,
            candidate=self.candidate,
            status=JobApplication.Status.PENDING,
        )

        payload = {"status": "short_listed"}
        res = self.client.patch(
            f"/api/jobs/application/{app.id}/status",
            data=payload,
            content_type="application/json",
            **self.employer_headers,
        )
        self.assertEqual(res.status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.status, JobApplication.Status.SHORT_LISTED)

    def test_candidate_withdraw_application(self):
        app = JobApplication.objects.create(
            job=self.job,
            candidate=self.candidate,
            status=JobApplication.Status.PENDING,
        )
        res = self.client.delete(
            f"/api/jobs/application/{app.id}/withdraw",
            **self.candidate_headers,
        )
        self.assertEqual(res.status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.status, JobApplication.Status.WITHDRAWN)

    # =========================================================================
    # Interview Tests
    # =========================================================================

    def test_interview_lifecycle(self):
        app = JobApplication.objects.create(
            job=self.job,
            candidate=self.candidate,
            status=JobApplication.Status.SHORT_LISTED,
        )

        interview_time = timezone.now() + datetime.timedelta(days=2)
        payload = {
            "job_id": self.job.id,
            "candidate_id": self.candidate.id,
            "application_id": app.id,
            "schedule_date_and_time": interview_time.isoformat(),
            "link": "https://meet.google.com/xyz-abc-def",
            "panel_name": "Technical Hiring Panel",
            "notes": "Bring portfolio and system design preparation.",
        }

        # 1. Create Interview
        create_res = self.client.post(
            "/api/jobs/create_interview",
            data=payload,
            content_type="application/json",
            **self.employer_headers,
        )
        self.assertEqual(create_res.status_code, 200)
        interview_id = create_res.json()["data"]["id"]

        # App status updated to interviewed
        app.refresh_from_db()
        self.assertEqual(app.status, JobApplication.Status.INTERVIEWED)

        # 2. Get Interview by ID
        get_res = self.client.get(f"/api/jobs/interview/{interview_id}", **self.candidate_headers)
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["data"]["panel_name"], "Technical Hiring Panel")

        # 3. Candidate views interviews
        cand_res = self.client.get("/api/jobs/candidate/interviews", **self.candidate_headers)
        self.assertEqual(cand_res.status_code, 200)
        self.assertEqual(cand_res.json()["total"], 1)

        # 4. Employer views interviews
        emp_res = self.client.get("/api/jobs/employer/interviews", **self.employer_headers)
        self.assertEqual(emp_res.status_code, 200)
        self.assertEqual(emp_res.json()["total"], 1)

        # 5. Update interview
        new_time = timezone.now() + datetime.timedelta(days=3)
        patch_payload = {
            "schedule_date_and_time": new_time.isoformat(),
            "panel_name": "Executive Panel",
        }
        patch_res = self.client.patch(
            f"/api/jobs/interview/{interview_id}",
            data=patch_payload,
            content_type="application/json",
            **self.employer_headers,
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["data"]["panel_name"], "Executive Panel")

        # 6. Status update
        status_payload = {"status": "completed"}
        status_res = self.client.patch(
            f"/api/jobs/interview/{interview_id}/status",
            data=status_payload,
            content_type="application/json",
            **self.candidate_headers,
        )
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json()["data"]["status"], "completed")

        # 7. Delete interview
        del_res = self.client.delete(f"/api/jobs/interview/{interview_id}", **self.employer_headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(Interview.objects.filter(id=interview_id).exists())
