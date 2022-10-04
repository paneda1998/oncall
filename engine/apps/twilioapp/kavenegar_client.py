import logging
from django.apps import apps

from apps.twilioapp.constants import TEST_CALL_TEXT
import kavenegar
import os
logger = logging.getLogger(__name__)


class KavenegarClient:
    @property
    def kavenegar_api_client(self):
        # return kavenegar.KavenegarAPI(apikey=os.getenv("KAVENEGAR_API_KEY"))
        return kavenegar.KavenegarAPI(apikey="74576A6E376350306144306468634956316D4478483964717535424B77575154")


    def send_message(self, body, to):
        try:
            params = {
                "receptor": to,  # multiple mobile number, split by comma
                "message": body,
            }
            self.kavenegar_api_client.sms_send(params)
        except:
            pass # capture in sentry


    def make_test_call(self, to):
        message = TEST_CALL_TEXT.format(
            channel_name="Test call",
            alert_group_name="Test notification",
            alerts_count=2,
        )
        self.make_call(message=message, to=to)

    def make_call(self, message, to):
        try:
            params = {"receptor": to, "message": message}
            response = self.kavenegar_api_client.call_maketts(params)
            print(response)
        except Exception:
            pass

    def create_log_record(self, **kwargs):
        TwilioLogRecord = apps.get_model("twilioapp", "TwilioLogRecord")
        TwilioLogRecord.objects.create(**kwargs)


kavenegar_client = KavenegarClient()
