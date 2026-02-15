"""Reconciliation job scaffold."""

from app.application.services.reconciliation_service import ReconciliationService


class ReconciliationWorker:
    """Background job to run reconciliation jobs."""

    def run(self, service: ReconciliationService) -> None:
        """Execute the reconciliation workflow."""
        _ = service
        # TODO: Trigger service.reconcile from task queue runtime.
