from datetime import datetime, timezone
from app import db
from app.models.genre import channel_genres
from app.models.language import channel_languages


class Channel(db.Model):
    """Channel entity representing a television broadcast stream."""
    __tablename__ = "channels"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    external_id = db.Column(db.String(120), nullable=True, index=True)  # tvg-id e.g. 'CNN.us'
    name = db.Column(db.String(255), nullable=False, index=True)
    logo_url = db.Column(db.String(1024), nullable=True)
    stream_url = db.Column(db.String(2048), nullable=False, index=True)

    # Country taxonomy
    country_code = db.Column(
        db.String(10),
        db.ForeignKey("countries.code", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    country = db.relationship("Country", back_populates="channels")

    # Categories and Languages (Many-to-Many)
    genres = db.relationship(
        "Genre",
        secondary=channel_genres,
        back_populates="channels",
        lazy="joined"
    )
    languages = db.relationship(
        "Language",
        secondary=channel_languages,
        back_populates="channels",
        lazy="joined"
    )

    # Health & Operational Status
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    health_status = db.Column(
        db.String(30),
        default="unknown",
        nullable=False,
        index=True
    )  # 'healthy', 'degraded', 'unavailable', 'unsupported', 'unknown'
    last_health_check = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    last_successful_check = db.Column(db.DateTime(timezone=True), nullable=True)
    consecutive_failures = db.Column(db.Integer, default=0, nullable=False)
    response_time_ms = db.Column(db.Float, nullable=True)
    diagnostic_reason = db.Column(db.String(255), nullable=True)

    # Auditing timestamps
    first_seen_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    last_updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Health check history (cascade delete if channel deleted)
    stream_checks = db.relationship(
        "StreamCheck",
        back_populates="channel",
        cascade="all, delete-orphan",
        order_by="desc(StreamCheck.checked_at)",
        lazy="dynamic"
    )

    __table_args__ = (
        db.Index("idx_channel_active_health", "is_active", "health_status"),
        db.Index("idx_channel_country_active", "country_code", "is_active"),
        db.Index("idx_channel_active_name", "is_active", "name"),
        db.Index("idx_channel_active_last_check", "is_active", "last_health_check"),
    )

    def __repr__(self):
        return f"<Channel id={self.id} name='{self.name}' external_id='{self.external_id}'>"

    def to_dict(self, include_checks=False):
        """Serialize model to clean JSON-compatible dictionary."""
        data = {
            "id": self.id,
            "external_id": self.external_id,
            "name": self.name,
            "logo_url": self.logo_url,
            "stream_url": self.stream_url,
            "country": self.country.to_dict() if self.country else None,
            "genres": [g.to_dict() for g in self.genres],
            "languages": [l.to_dict() for l in self.languages],
            "is_active": self.is_active,
            "health_status": self.health_status,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "last_successful_check": self.last_successful_check.isoformat() if self.last_successful_check else None,
            "consecutive_failures": self.consecutive_failures,
            "response_time_ms": self.response_time_ms,
            "diagnostic_reason": self.diagnostic_reason,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None
        }
        if include_checks:
            data["recent_checks"] = [c.to_dict() for c in self.stream_checks.limit(5)]
        return data
