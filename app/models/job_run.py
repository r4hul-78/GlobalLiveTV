from datetime import datetime, timezone
from app import db


class JobRun(db.Model):
    """
    Audit log of catalog ingestion and stream health check runs.
    Tracks execution status, timing, processed record metrics, and failures.
    """
    __tablename__ = "job_runs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(50), nullable=False, index=True)  # 'ingest', 'health_check', 'refresh'
    status = db.Column(db.String(30), nullable=False, default="running", index=True)  # 'running', 'completed', 'failed'
    started_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)

    # Metrics
    records_processed = db.Column(db.Integer, default=0, nullable=False)
    records_imported = db.Column(db.Integer, default=0, nullable=False)
    records_updated = db.Column(db.Integer, default=0, nullable=False)
    records_skipped = db.Column(db.Integer, default=0, nullable=False)
    records_failed = db.Column(db.Integer, default=0, nullable=False)

    # Summaries & Diagnostics
    summary = db.Column(db.String(500), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.Index("idx_job_run_type_started", "job_type", "started_at"),
    )

    def __repr__(self):
        return f"<JobRun id={self.id} type='{self.job_type}' status='{self.status}' started='{self.started_at}'>"

    def to_dict(self):
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "records_processed": self.records_processed,
            "records_imported": self.records_imported,
            "records_updated": self.records_updated,
            "records_skipped": self.records_skipped,
            "records_failed": self.records_failed,
            "summary": self.summary,
            "error_message": self.error_message
        }
