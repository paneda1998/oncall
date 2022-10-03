import logging
from django.utils import timezone
import datetime
import random
from twilio.base.exceptions import TwilioRestException
from rest_framework.exceptions import Throttled

from apps.twilioapp.kavenegar_client import kavenegar_client
from apps.twilioapp.models.token import Tokenn, TokenType
logger = logging.getLogger(__name__)




class PhoneManager:
    def __init__(self, user):
        self.user = user

    def send_verification_code(self):
        throttling_seconds = 120
        recent_token = Tokenn.objects.filter(
            user=self.user,
            token_type=TokenType.MobileVerification.value,
            creation_time__gt=timezone.now() - datetime.timedelta(seconds=throttling_seconds),
            specification={"mobile": self.user.unverified_phone_number},
        ).first()
        if recent_token:
            remaining_wait_seconds = int(
                throttling_seconds - (timezone.now() - recent_token.creation_time).total_seconds()
            )
            raise Throttled(
                detail=_("Verification request was just sent. Please wait {remaining_wait_seconds} seconds.").format(
                    remaining_wait_seconds=remaining_wait_seconds
                )
            )
        total_tokens_count = Tokenn.objects.filter(user=self.user, token_type=TokenType.MobileVerification.value).count()
        if total_tokens_count >= 20:
            raise Throttled(
                detail=_(
                    "You requested too many times for verification SMS. If you have any problem please contact us."
                )
            )

        token_value = "".join(random.sample("0123456789", 6))
        mobile_verification_token = Tokenn.objects.create(
            user=self.user,
            token_type=TokenType.MobileVerification.value,
            token=token_value,
            expiration_time=timezone.now() + timezone.timedelta(minutes=15),
            specification={"mobile": self.user.unverified_phone_number},
        )
        kavenegar_client.send_message(mobile_verification_token.token, self.user.unverified_phone_number)
        return True



    def verify_phone_number(self, code):
        try:
            mobile_verification_token = Tokenn.objects.filter(
                token=code,
                user=self.user,
                token_type=TokenType.MobileVerification.value,
                specification={"mobile": self.user.unverified_phone_number},
                creation_time__gte=timezone.now() - timezone.timedelta(minutes=5),
            ).first()
        except:
            return False, None
        if mobile_verification_token is not None and mobile_verification_token.is_usable:
            self.user.unverified_phone_number = self.user.verified_phone_number
            # todo remove this after smtp fixing
            self.user.save()
            mobile_verification_token.is_used = True
            mobile_verification_token.save()
        else:
            return False, None
        return True, None




    def forget_phone_number(self):
        if self.user.verified_phone_number or self.user.unverified_phone_number:
            old_verified_phone_number = self.user.verified_phone_number
            self.user.clear_phone_numbers()
            if old_verified_phone_number:
                self.notify_about_changed_verified_phone_number(old_verified_phone_number)
            return True
        return False

    def notify_about_changed_verified_phone_number(self, phone_number, connected=False):
        text = (
            f"This phone number has been {'connected to' if connected else 'disconnected from'} Grafana OnCall team "
            f'"{self.user.organization.stack_slug}"\nYour Grafana OnCall <3'
        )
        try:
            kavenegar_client.send_message(text, phone_number)
        except TwilioRestException as e:
            logger.error(
                f"Failed to notify user {self.user.pk} about phone number "
                f"{'connection' if connected else 'disconnection'}:\n{e}"
            )
