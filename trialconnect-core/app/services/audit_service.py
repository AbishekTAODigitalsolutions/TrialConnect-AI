import structlog


class AuditService:
    def __init__(self) -> None:
        self.logger = structlog.get_logger("audit")

    def record_event(self, event_name: str, **payload: object) -> None:
        self.logger.info("audit_event", event_name=event_name, **payload)
