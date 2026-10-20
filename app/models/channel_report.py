from datetime import datetime, timezone
from app import db


class ChannelReport(db.Model):
    """
    User-submitted stream issue report.
    Stores diagnostic feedback without collecting personal information or user tracking identifiers.
    """
    __tablename__ = "channel_reports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    channel_id = db.Column(
        db.Integer,
        db.ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    issue_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    reported_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

    channel = db.relationship(
        "Channel",
        backref=db.backref("reports", lazy="dynamic", cascade="all, delete-orphan")
    )

    def __repr__(self):
        return f"<ChannelReport id={self.id} channel_id={self.channel_id} issue_type='{self.issue_type}'>"

    def to_dict(self):
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "issue_type": self.issue_type,
            "description": self.description,
            "reported_at": self.reported_at.isoformat() if self.reported_at else None
        }
