"""Rate limit policy action."""

from app.domain.policy.base_policy_action import BasePolicyAction


class RateLimitAction(BasePolicyAction):
    """Produces a rate-limit decision for protect mode."""

    def apply(self, context: dict[str, object]) -> dict[str, object]:
        _ = context
        # TODO: Implement rate-limit policy output.
        return {}
