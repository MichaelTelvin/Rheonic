# Reconciliation job scaffold.
from app.application.services.reconciliation_service import ReconciliationService
from app.logger import get_logger

logger = get_logger(__name__)


class ReconciliationWorker:
    # Background job to run reconciliation jobs.

    def run(self, service: ReconciliationService) -> None:
        # Execute the reconciliation workflow.
        try:
            service.reconcile()
            logger.info("Reconciliation worker completed")
        except Exception:
            logger.exception("Reconciliation worker failed")
            raise
