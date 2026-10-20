from app import db

# Many-to-many association table between Channel and Language
channel_languages = db.Table(
    "channel_languages",
    db.Column("channel_id", db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True),
    db.Column("language_code", db.String(10), db.ForeignKey("languages.code", ondelete="CASCADE"), primary_key=True, index=True)
)



class Language(db.Model):
    """Language taxonomy model."""
    __tablename__ = "languages"

    code = db.Column(db.String(10), primary_key=True)   # e.g., 'eng', 'spa', 'fra', 'hin'
    name = db.Column(db.String(120), nullable=False, index=True)

    # Relationship
    channels = db.relationship(
        "Channel",
        secondary=channel_languages,
        back_populates="languages",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<Language {self.code}: {self.name}>"

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name
        }
