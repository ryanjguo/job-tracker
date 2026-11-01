"""Databases created before location/term/next_action/follow_up_date existed are upgraded in place."""
from datetime import date

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db import init_db
from app.models import Application

NEW = ("location", "term", "next_action", "follow_up_date")


def old_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    init_db(engine)
    with engine.begin() as c:
        for col in NEW:
            c.execute(text(f"ALTER TABLE applications DROP COLUMN {col}"))
        c.execute(text(
            "INSERT INTO applications (company, role, status, applied_date, job_url, notes, source, ats,"
            " email_message_id, created_at, status_changed_at) VALUES ('Globex', 'Intern', 'applied',"
            " '2026-09-19', '', :notes, 'import', '', '', '2026-11-01', '2026-11-01')"),
            {"notes": "Didn't do the OA\nLocation: Toronto, Waterloo\nTerm / Season: Summer 2027\n"
                      "Next Action: Email recruiter\nDeadline / Follow-up: 2026-11-05\nReferral: Jane"})
    assert not set(NEW) & {c["name"] for c in inspect(engine).get_columns("applications")}
    return engine


def test_old_database_gets_columns_and_note_lines_move(tmp_path):
    engine = old_database(tmp_path)
    init_db(engine)
    assert set(NEW) <= {c["name"] for c in inspect(engine).get_columns("applications")}
    with Session(engine) as s:
        a = s.query(Application).one()
        assert (a.location, a.term, a.next_action, a.follow_up_date) == (
            "Toronto, Waterloo", "Summer 2027", "Email recruiter", date(2026, 11, 5))
        assert a.notes == "Didn't do the OA\nReferral: Jane"


def test_upgrade_runs_once(tmp_path):
    engine = old_database(tmp_path)
    init_db(engine)
    with Session(engine) as s:
        a = s.query(Application).one()
        a.notes += "\nLocation: typed by hand later"
        s.commit()
    init_db(engine)  # columns already exist: notes are left alone
    with Session(engine) as s:
        assert s.query(Application).one().notes.endswith("Location: typed by hand later")
