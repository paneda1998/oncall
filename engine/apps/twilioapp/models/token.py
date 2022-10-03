import uuid
from enum import Enum

from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models import CASCADE
from django.utils import timezone
import enum

from apps.user_management.models import User

class BaseModel(models.Model):
    secret_fields = []
    objects = models.Manager()
    self_objects = models.Manager()

def create_choices_from_enum(enum: enum.EnumMeta):
    return [(e.value, e.name) for e in enum]

class TokenType(Enum):
    ForgetPassword = "ForgetPassword"
    EmailVerification = "EmailVerify"
    TeamInvitation = "TeamInvitation"
    OrganizationInvitation = "OrganizationInvitation"
    MobileVerification = "MobileVerify"


class Tokenn(BaseModel):
    secret_fields = ["token"]
    objects = models.Manager()
    token_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creation_time = models.DateTimeField(default=timezone.now, blank=True)
    expiration_time = models.DateTimeField(null=False, blank=True)
    token = models.CharField(max_length=128, blank=False, null=False, db_index=True)
    token_type = models.CharField(max_length=25, choices=create_choices_from_enum(TokenType))
    is_used = models.BooleanField(default=False)
    specification = JSONField(blank=True, null=True)
    user = models.ForeignKey(User, on_delete=CASCADE, related_name="tokens", null=True, blank=True)

    def __str__(self):
        return f"{self.token_type}/{self.user_id}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expiration_time

    @property
    def is_usable(self) -> bool:
        if self.is_used:
            return False
        return not self.is_expired

    class Meta:
        ordering = ("-creation_time",)
