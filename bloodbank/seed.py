from bloodbank.constants import BLOOD_GROUPS
from bloodbank.extensions import db
from bloodbank.models import BloodInventory, User


def seed_database():
    if not BloodInventory.query.first():
        for group in BLOOD_GROUPS:
            db.session.add(BloodInventory(blood_group=group, units=25))
        db.session.commit()

    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@bloodbank.local",
            full_name="System Administrator",
            role="admin",
            email_verified=True,
        )
        admin.set_password("admin")
        db.session.add(admin)
        db.session.commit()
    elif not admin.email_verified:
        admin.email_verified = True
        db.session.commit()

    if not User.query.filter_by(username="user1").first():
        user = User(
            username="user1",
            email="user1@example.com",
            full_name="Demo User",
            phone="555-0100",
            role="recipient",
        )
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
