from app import db

# Many-to-many association table between Channel and Genre
channel_genres = db.Table(
    "channel_genres",
    db.Column("channel_id", db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True),
    db.Column("genre_id", db.Integer, db.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True, index=True)
)



class Genre(db.Model):
    """Genre / Category taxonomy model."""
    __tablename__ = "genres"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)  # e.g., 'news', 'sports'
    name = db.Column(db.String(120), nullable=False)                          # e.g., 'News', 'Sports'

    # Relationship
    channels = db.relationship(
        "Channel",
        secondary=channel_genres,
        back_populates="genres",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<Genre {self.slug}: {self.name}>"

    def to_dict(self):
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name
        }
