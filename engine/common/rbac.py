import typing
from rest_access_policy import AccessPolicy


def _generate_permission_string(resource: str, action: str) -> str:
    return f"grafana-oncall-app.{resource}:{action}"


PERMISSIONS = {
    "schedules": {
        "read": _generate_permission_string("schedules", "read"),
        "write": _generate_permission_string("schedules", "write"),
    },
}


class GrafanaRBACAccessPolicy(AccessPolicy):
    id = 'grafana-rbac-policy'

    # https://rsinger86.github.io/drf-access-policy/customization.html#customizing-principal-prefixes
    group_prefix = "permission:"

    def get_user_group_values(self, user) -> typing.List[str]:
        # TODO: make network call to Grafana API access-policy endpoint to fetch current
        # authed user's permissions
        if user.id == 1:
            return [PERMISSIONS["schedules"]["read"]]
        return []


class ScheduleAccessPolicy(GrafanaRBACAccessPolicy):
    statements = [
        {
            "action": ["list", "retrieve"],
            "principal": [f"permission:{PERMISSIONS['schedules']['read']}"],
            "effect": "allow"
        },
    ]
