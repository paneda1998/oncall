import logging

import requests
from django.apps import apps
from django.conf import settings
from django.db import models
from rest_framework import status
from twilio.base.exceptions import TwilioRestException

from apps.alerts.incident_appearance.renderers.sms_renderer import AlertGroupSmsRenderer
from apps.alerts.signals import user_notification_action_triggered_signal
from apps.base.utils import live_settings
from apps.twilioapp.constants import TwilioMessageStatuses
from apps.twilioapp.kavenegar_client import kavenegar_client
from apps.twilioapp.twilio_client import twilio_client
from common.api_helpers.utils import create_engine_url
from common.utils import clean_markup

logger = logging.getLogger(__name__)



class KavenegarKavenegarSMSMessage(models.Model):

    exceeded_limit = models.BooleanField(null=True, default=None)
    represents_alert = models.ForeignKey("alerts.Alert", on_delete=models.SET_NULL, null=True, default=None)
    represents_alert_group = models.ForeignKey("alerts.AlertGroup", on_delete=models.SET_NULL, null=True, default=None)
    notification_policy = models.ForeignKey(
        "base.UserNotificationPolicy", on_delete=models.SET_NULL, null=True, default=None
    )

    receiver = models.ForeignKey("user_management.User", on_delete=models.CASCADE, null=True, default=None)

    status = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        choices=TwilioMessageStatuses.CHOICES,
    )
    grafana_cloud_notification = models.BooleanField(default=False)

    # https://www.twilio.com/docs/sms/api/message-resource#message-properties
    sid = models.CharField(
        blank=True,
        max_length=50,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class SMSLimitExceeded(Exception):
        """SMS limit exceeded"""

    class PhoneNumberNotVerifiedError(Exception):
        """Phone number is not verified"""

  
    @classmethod
    def send_sms(cls, user, alert_group, notification_policy, is_cloud_notification=False):
        UserNotificationPolicyLogRecord = apps.get_model("base", "UserNotificationPolicyLogRecord")

        log_record = None
        renderer = AlertGroupSmsRenderer(alert_group)
        message_body = renderer.render()
        try:
            cls._send_sms(user, message_body, alert_group=alert_group, notification_policy=notification_policy)
        except KavenegarKavenegarSMSMessage.SMSLimitExceeded as e:
            logger.warning(f"Unable to send sms. Exception {e}")
            log_record = UserNotificationPolicyLogRecord(
                author=user,
                type=UserNotificationPolicyLogRecord.TYPE_PERSONAL_NOTIFICATION_FAILED,
                notification_policy=notification_policy,
                alert_group=alert_group,
                notification_error_code=UserNotificationPolicyLogRecord.ERROR_NOTIFICATION_SMS_LIMIT_EXCEEDED,
                notification_step=notification_policy.step if notification_policy else None,
                notification_channel=notification_policy.notify_by if notification_policy else None,
            )
        except KavenegarSMSMessage.PhoneNumberNotVerifiedError as e:
            logger.warning(f"Unable to send sms. Exception {e}")
            log_record = UserNotificationPolicyLogRecord(
                author=user,
                type=UserNotificationPolicyLogRecord.TYPE_PERSONAL_NOTIFICATION_FAILED,
                notification_policy=notification_policy,
                alert_group=alert_group,
                notification_error_code=UserNotificationPolicyLogRecord.ERROR_NOTIFICATION_PHONE_NUMBER_IS_NOT_VERIFIED,
                notification_step=notification_policy.step if notification_policy else None,
                notification_channel=notification_policy.notify_by if notification_policy else None,
            )

        if log_record is not None:
            log_record.save()
            user_notification_action_triggered_signal.send(sender=KavenegarSMSMessage.send_sms, log_record=log_record)

   
    @classmethod
    def _send_sms(cls, user, message_body, alert_group=None, notification_policy=None, grafana_cloud=False):
        if not user.verified_phone_number:
            raise KavenegarSMSMessage.PhoneNumberNotVerifiedError("User phone number is not verified")

        sms_message = KavenegarSMSMessage(
            represents_alert_group=alert_group,
            receiver=user,
            notification_policy=notification_policy,
            grafana_cloud_notification=grafana_cloud,
        )
        sms_left = user.organization.sms_left(user)

        if sms_left <= 0:
            sms_message.exceeded_limit = True
            sms_message.save()
            raise KavenegarSMSMessage.SMSLimitExceeded("Organization sms limit exceeded")

        sms_message.exceeded_limit = False
        if sms_left < 3:
            message_body += " {} sms left. Contact your admin.".format(sms_left)

        kavenegar_message = kavenegar_client.send_message(message_body, user.verified_phone_number)
        sms_message.save()

        return sms_message
