import logging

import requests
from django.apps import apps
from django.db import models

from apps.alerts.signals import user_notification_action_triggered_signal
from apps.twilioapp.kavenegar_client import kavenegar_client
from apps.twilioapp.constants import TwilioCallStatuses

logger = logging.getLogger(__name__)

class KavenegarPhoneCall(models.Model):
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
        choices=TwilioCallStatuses.CHOICES,
    )

    sid = models.CharField(
        blank=True,
        max_length=50,
    )

    created_at = models.DateTimeField(auto_now_add=True)


    class KavenegarPhoneCallsLimitExceeded(Exception):
        """Phone calls limit exceeded"""

    class PhoneNumberNotVerifiedError(Exception):
        """Phone number is not verified"""



    @classmethod
    def make_call(cls, user, alert_group, notification_policy, is_cloud_notification=False):
        UserNotificationPolicyLogRecord = apps.get_model("base", "UserNotificationPolicyLogRecord")
        log_record = None
        renderer = AlertGroupKavenegarPhoneCallRenderer(alert_group)
        message_body = renderer.render()
        try:
            cls._make_call(user, message_body, alert_group=alert_group, notification_policy=notification_policy)
        except KavenegarPhoneCall.KavenegarPhoneCallsLimitExceeded:
            log_record = UserNotificationPolicyLogRecord(
                author=user,
                type=UserNotificationPolicyLogRecord.TYPE_PERSONAL_NOTIFICATION_FAILED,
                notification_policy=notification_policy,
                alert_group=alert_group,
                notification_error_code=UserNotificationPolicyLogRecord.ERROR_NOTIFICATION_PHONE_CALLS_LIMIT_EXCEEDED,
                notification_step=notification_policy.step if notification_policy else None,
                notification_channel=notification_policy.notify_by if notification_policy else None,
            )
        except KavenegarPhoneCall.PhoneNumberNotVerifiedError:
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
            user_notification_action_triggered_signal.send(sender=KavenegarPhoneCall.make_call, log_record=log_record)


    @classmethod
    def _make_call(cls, user, message_body, alert_group=None, notification_policy=None, grafana_cloud=False):
        if not user.verified_phone_number:
            raise KavenegarPhoneCall.PhoneNumberNotVerifiedError("User phone number is not verified")

        phone_call = KavenegarPhoneCall(
            represents_alert_group=alert_group,
            receiver=user,
            notification_policy=notification_policy,
            grafana_cloud_notification=grafana_cloud,
        )
        phone_calls_left = user.organization.phone_calls_left(user)

        if phone_calls_left <= 0:
            phone_call.exceeded_limit = True
            phone_call.save()
            raise KavenegarPhoneCall.KavenegarPhoneCallsLimitExceeded("Organization calls limit exceeded")

        phone_call.exceeded_limit = False
        if phone_calls_left < 3:
            message_body += " {} phone calls left. Contact your admin.".format(phone_calls_left)

        kavenegar_call = kavenegar_client.make_call(message_body, user.verified_phone_number, grafana_cloud=grafana_cloud)
        phone_call.save()
        return phone_call
