from datetime import datetime, timezone
from app import db


class Country(db.Model):
    """Country taxonomy model representing channel nationality."""
    __tablename__ = "countries"

    code = db.Column(db.String(10), primary_key=True)  # e.g., 'US', 'GB', 'IN', 'FR'
    name = db.Column(db.String(120), nullable=False, index=True)

    # Relationships
    channels = db.relationship("Channel", back_populates="country", lazy="dynamic")

    def __repr__(self):
        return f"<Country {self.code}: {self.name}>"

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name
        }
