# Cooldown block policy action.
from app.domain.policy.base_policy_action import BasePolicyAction


class CooldownAction(BasePolicyAction):
    # Produces a cooldown block decision for protect mode.
    def apply(self, context: dict[str, object]) -> dict[str, object]:
        _ = context
        # TODO: Implement cooldown window calculation.
        return {}
