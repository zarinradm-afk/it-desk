from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.database import Base


def test_create_ticket():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = models.User(username="ali", full_name="Ali", role="user")
        db.add(user)
        db.flush()
        ticket = models.Ticket(title="Printer is not working", requester_id=user.id)
        db.add(ticket)
        db.commit()
        assert ticket.id == 1
        assert ticket.status == "new"
        assert ticket.requester.username == "ali"

