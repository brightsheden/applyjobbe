import os
import logging
from uuid import uuid4
from django.template.loader import render_to_string
from django.conf import settings
from background_task import background

try:
    import requests
except ModuleNotFoundError:  
    requests = None

logger = logging.getLogger(__name__)



class EmailClient:
    ZEPTO_URL = "https://api.zeptomail.com/v1.1/email"
    API_KEY = os.getenv("ZOHO_API_KEY")
    FROM_ADDRESS = os.getenv("ZOHO_MAIL_ADDRESS")
    FROM_NAME = "QwikMarka"

    @classmethod
    def send_email(
        cls, to, subject, html=None, template_name=None, context=None,
        from_email=None, from_name=None, reply_to=None, use_bcc=False
    ):
        """
        Send an email using ZeptoMail API.

        :param to: str or list of email addresses
        :param subject: Email subject
        :param html: Raw HTML string (optional)
        :param template_name: Django template path (optional)
        :param context: Context dict for rendering template
        :param from_email: Optional sender override
        :param from_name: Optional sender name
        :param reply_to: Optional reply-to email
        :param use_bcc: If True, send all recipients as BCC to hide addresses
        """

        if not html and template_name:
            html = render_to_string(template_name, context or {})

        if not html:
            raise ValueError("HTML content or template_name is required")

        if requests is None:
            return {
                "status": "skipped",
                "detail": "requests package is not installed",
            }

        if isinstance(to, str):
            to = [to]

        payload = {
            "from": {
                "address": from_email or cls.FROM_ADDRESS,
                "name": from_name or cls.FROM_NAME
            },
            "subject": subject,
            "htmlbody": html,
        }

        # Use BCC to hide recipients from each other
        if use_bcc:
            payload["to"] = [{"email_address": {"address": cls.FROM_ADDRESS}}]  # Send to self or a single address
            payload["bcc"] = [{"email_address": {"address": email}} for email in to]
        else:
            payload["to"] = [{"email_address": {"address": email}} for email in to]

        if reply_to:
            payload["reply_to"] = [{
                "address": reply_to,
                "name": from_name or cls.FROM_NAME
            }]

        headers = {
            "Authorization": f"{cls.API_KEY}",
            "Content-Type": "application/json"
        }

        if not cls.API_KEY or not (from_email or cls.FROM_ADDRESS):
            return {
                "status": "skipped",
                "detail": "Email client is not configured",
            }

        response = requests.post(cls.ZEPTO_URL, json=payload, headers=headers)

        # if response.status_code != 200:
        #     print("ZeptoMail Email send failed:", response.json())

        return response.json()
    
    @background(schedule=60)
    def send_email_task(cls, to, subject, html=None, template_name=None, context=None,
        from_email=None, from_name=None, reply_to=None, use_bcc=False ):

        cls.send_email(
            to=to,
            subject=subject,
            html=html,
            template_name=template_name,
            context=context,
            use_bcc=use_bcc
            
        )




class FlutterwavePaymentClient:
    def __init__(self):
        self.api_key = getattr(settings, "RAVE_SECRET_KEY", None) or os.getenv("RAVE_SECRET_KEY")
        self.base_url = "https://api.flutterwave.com/v3"
        self.v4_base_url = getattr(settings, "FLUTTERWAVE_V4_BASE_URL", None) or os.getenv(
            "FLUTTERWAVE_V4_BASE_URL",
            "https://api.flutterwave.com",
        )

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def initiate_payment(self, payment_data:dict):
        if requests is None:
            return {"status": "error", "message": "requests package is not installed"}
        url = f"{self.base_url}/payments"
        try:
            response = requests.post(url, json=payment_data, headers=self._headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception("Error initiating payment: %s", str(e))
            return {"status": "error", "message": str(e)}

    def initiate_bank_transfer(self, payment_data):
        if requests is None:
            return {"status": "error", "message": "requests package is not installed"}
        url = f"{self.base_url}/charges?type=bank_transfer"
        try:
            response = requests.post(url, json=payment_data, headers=self._headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception("Error initiating bank transfer: %s", str(e))
            return {"status": "error", "message": str(e)}

    def verify_transaction(self, transaction_id):
        if requests is None:
            return {"status": "error", "message": "requests package is not installed"}
        url = f"{self.base_url}/transactions/{transaction_id}/verify"
        try:
            response = requests.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception("Error verifying transaction: %s", str(e))
            return {"status": "error", "message": str(e)}

    def get_conversion_rate(self, source_currency: str, destination_currency: str, amount):
        """
        Fetch real-time conversion rate from Flutterwave.
        Docs: https://developer.flutterwave.com/reference/transfer_rates_post
        """
        if requests is None:
            return {"status": "error", "message": "requests package is not installed"}

        source_currency = source_currency.upper()
        destination_currency = destination_currency.upper()
        amount = str(amount)

        v4_url = f"{self.v4_base_url}/transfers/rates"
        payload = {
            "source": {
                "currency": source_currency,
                "amount": amount,
            },
            "destination": {
                "currency": destination_currency,
            },
            "precision": 6,
        }
        headers = {
            **self._headers(),
            "X-Trace-Id": f"qwikmarka-{uuid4().hex}",
            "X-Idempotency-Key": f"qwikmarka-rate-{uuid4().hex}",
        }
        try:
            response = requests.post(v4_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("Flutterwave v4 rate API failed; trying v3 fallback: %s", str(e))

        url = f"{self.base_url}/transfers/rates"
        params = {
            "source_currency": source_currency,
            "destination_currency": destination_currency,
            "amount": amount,
        }
        try:
            response = requests.get(url, params=params, headers=self._headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception("Error fetching conversion rate: %s", str(e))
            return {"status": "error", "message": str(e)}

    def verify_transaction_trx_ref(self, trx_ref):
        if requests is None:
            return {"status": "error", "message": "requests package is not installed"}
        url = f"{self.base_url}/transactions/verify_by_reference?tx_ref={trx_ref}"
        try:
            response = requests.get(url,  headers=self._headers())
            response.raise_for_status()
            # if response.status_code == 404:
            #     trx = TransactionHistory.objects.filter(trx_ref=trx_ref).first()
            #     if trx:
            #         trx.status = TransactionHistory.TransactionStatusEnums.CANCLED.value
            #         trx.save()
            return response.json()
        except Exception as e:
            logger.exception("Error verifying transaction by reference: %s", str(e))
            return {"status": "error", "message": str(e)}