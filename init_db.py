from __future__ import annotations

from sqlalchemy import create_engine

from models import Base


def init_db(database_url: str = "sqlite:///./app.db") -> None:
    engine = create_engine(database_url, echo=True)
    Base.metadata.create_all(bind=engine)

    from dotenv import load_dotenv

    load_dotenv()
    import os
    from sqlalchemy.orm import sessionmaker
    from models import User
    from auth import create_access_token

    admin_email = os.getenv("ADMIN_EMAIL", "12130213@gmail.com")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    existing = session.query(User).filter(User.email == admin_email).first()
    if existing:
        print(f"Admin user already exists: {admin_email}")
    else:
        admin_name = os.getenv("ADMIN_NAME", "129Admin")
        admin_secondary = os.getenv("ADMIN_SECONDARY", "1")
        admin_status = os.getenv("ADMIN_STATUS", "active")
        new_admin = User(
            name=admin_name,
            secondary_name=admin_secondary,
            email=admin_email,
            status=admin_status,
            is_admin=True,
            email_verified=True,
            verification_code=None,
        )
        session.add(new_admin)
        session.commit()
        session.refresh(new_admin)
        print(new_admin.id)
        token = create_access_token({"sub": new_admin.id})
        print(f"Default admin created: {admin_email}")
        print(f"ADMIN_ACCESS_TOKEN={token}")



if __name__ == "__main__":
    import sys

    database_url = sys.argv[1] if len(sys.argv) > 1 else "sqlite:///./app.db"
    init_db(database_url)
