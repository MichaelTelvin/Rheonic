# Cap tokens policy action.
from app.domain.policy.base_policy_action import BasePolicyAction


class CapTokensAction(BasePolicyAction):
    # Produces token-cap decision constraints for protect mode.
    def apply(self, context: dict[str, object]) -> dict[str, object]:
        _ = context
        # TODO: Implement deterministic token cap strategy.
        return {}
