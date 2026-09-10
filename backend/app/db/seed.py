"""Seed the three official MVP achievement categories and their dynamic fields."""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.dain import AchievementCategory, CategoryFieldDefinition


CATEGORIES = [
    {
        "slug": "academic",
        "name": "Academic",
        "description": "Research, publications, scholarships, awards, and academic milestones.",
        "fields": [("publication_link", "Publication or evidence link", "url", True), ("award_or_outlet", "Award, journal, or outlet", "text", False)],
    },
    {
        "slug": "startup",
        "name": "Startup",
        "description": "Startup launches, investment, product milestones, and business impact.",
        "fields": [("funding_amount", "Funding amount", "number", True), ("startup_link", "Startup or evidence link", "url", False)],
    },
    {
        "slug": "social-impact",
        "name": "Social Impact",
        "description": "Community initiatives, volunteering, and measurable social impact.",
        "fields": [("impact_measure", "Impact measure", "text", True), ("beneficiaries", "Number of beneficiaries", "number", False)],
    },
]


def seed() -> None:
    database = SessionLocal()
    try:
        for category_data in CATEGORIES:
            category = database.scalar(select(AchievementCategory).where(AchievementCategory.slug == category_data["slug"]))
            if category is not None:
                continue
            category = AchievementCategory(
                slug=category_data["slug"], name=category_data["name"], description=category_data["description"]
            )
            database.add(category)
            database.flush()
            for order, (key, label, field_type, required) in enumerate(category_data["fields"]):
                database.add(
                    CategoryFieldDefinition(
                        category_id=category.id,
                        field_key=key,
                        label=label,
                        field_type=field_type,
                        is_required=required,
                        display_order=order,
                    )
                )
        database.commit()
    finally:
        database.close()


if __name__ == "__main__":
    seed()
