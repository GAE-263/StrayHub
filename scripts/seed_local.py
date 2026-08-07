"""Create fictional multi-tenant local seed data."""

import asyncio

from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from sqlalchemy import select


async def seed() -> None:
    hasher = Argon2PasswordHasher()
    async with session_factory() as session:
        async with session.begin():
            organizations = []
            for code, name in (("ORG-A", "虛構收容所 A"), ("ORG-B", "虛構收容所 B")):
                organization = (
                    await session.execute(select(Organization).where(Organization.code == code))
                ).scalar_one_or_none()
                if organization is None:
                    organization = Organization(code=code, name=name, status="active")
                    session.add(organization)
                    await session.flush()
                organizations.append(organization)
            for index, organization in enumerate(organizations):
                username = f"volunteer-{index + 1}"
                user = (
                    await session.execute(select(User).where(User.username == username))
                ).scalar_one_or_none()
                if user is None:
                    user = User(
                        username=username,
                        display_name=f"虛構志工 {index + 1}",
                        password_hash=hasher.hash("local-only-password"),
                        status="active",
                    )
                    session.add(user)
                    await session.flush()
                    session.add(
                        OrganizationMembership(
                            organization_id=organization.id,
                            user_id=user.id,
                            role="VOLUNTEER",
                            status="active",
                        )
                    )
                animal = (
                    await session.execute(
                        select(Animal).where(
                            Animal.organization_id == organization.id,
                            Animal.shelter_number == "VAAAG114080610",
                        )
                    )
                ).scalar_one_or_none()
                if animal is None:
                    session.add(
                        Animal(
                            organization_id=organization.id,
                            name="小黑",
                            shelter_number="VAAAG114080610",
                            status="active",
                        )
                    )


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
