from datetime import datetime, timezone
from app import db


class StreamCheck(db.Model):
    """Historical audit record of a stream health check."""
    __tablename__ = "stream_checks"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    channel_id = db.Column(
        db.Integer,
        db.ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    checked_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    outcome = db.Column(
        db.String(30),
        nullable=False,
        index=True
    )  # 'healthy', 'degraded', 'unavailable', 'unsupported', 'unknown'
    http_status = db.Column(db.Integer, nullable=True)
    response_time_ms = db.Column(db.Float, nullable=True)
    diagnostic_reason = db.Column(db.String(255), nullable=True)

    # Relationships
    channel = db.relationship("Channel", back_populates="stream_checks")

    __table_args__ = (
        db.Index("idx_streamcheck_channel_checked", "channel_id", "checked_at"),
    )

    def __repr__(self):
        return f"<StreamCheck channel_id={self.channel_id} outcome={self.outcome} at={self.checked_at}>"

    def to_dict(self):
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "outcome": self.outcome,
            "http_status": self.http_status,
            "response_time_ms": self.response_time_ms,
            "diagnostic_reason": self.diagnostic_reason
        }
