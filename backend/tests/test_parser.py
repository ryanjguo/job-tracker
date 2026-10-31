"""Parser tests using realistic (made-up) emails modelled on common ATS templates.

When the tracker misses one of your real emails, paste a sanitized copy in here as a new case.
"""
import pytest

from app.parser import EmailInput, classify, normalize_company


def mk(sender, subject, body=""):
    return EmailInput(message_id="<x@y>", sender=sender, subject=subject, body=body)


CONFIRMATIONS = [
    # (sender, subject, body, expected company, expected role)
    (
        "Acme Robotics <no-reply@us.greenhouse-mail.io>",
        "Thank you for applying to Acme Robotics!",
        "Hi Ryan,\n\nThanks for your interest in Acme Robotics! We wanted to let you know we "
        "received your application for Backend Engineer, and we are delighted that you would "
        "consider joining our team.\n\nBest,\nAcme Robotics Recruiting",
        "Acme Robotics", "Backend Engineer",
    ),
    (
        "Northwind <no-reply@hire.lever.co>",
        "Thank you for your application to Northwind",
        "Hi Ryan,\n\nThank you for applying to the Software Engineer, Platform position at "
        "Northwind. We'll review your application shortly.\n\nThe Northwind Team",
        "Northwind", "Software Engineer, Platform",
    ),
    (
        "LinkedIn <jobs-noreply@linkedin.com>",
        "Ryan, your application was sent to Globex",
        "Your application was sent to Globex\n\nData Analyst\nGlobex · Vancouver, BC (Hybrid)\n"
        "Applied on October 30, 2026\n\nView job",
        "Globex", "Data Analyst",
    ),
    (
        "Ashby <no-reply@ashbyhq.com>",
        "Thanks for applying to Initech",
        "Hi Ryan, thanks for applying to the Full Stack Developer role at Initech. "
        "Our team will review your application.",
        "Initech", "Full Stack Developer",
    ),
    (
        "talent@umbrella.com",
        "Your application for Junior QA Analyst at Umbrella Corp",
        "We have received your application and will be in touch.",
        "Umbrella Corp", "Junior QA Analyst",
    ),
    (
        "Hooli Careers <hooli@myworkday.com>",
        "Thank you for applying!",
        "Dear Ryan,\n\nThank you for your interest in Hooli. We have received your application "
        "for the Site Reliability Engineer position.\n\nHooli Talent Acquisition",
        "Hooli", "Site Reliability Engineer",
    ),
    (
        "Stark Industries <noreply@candidates.workablemail.com>",
        "Stark Industries - Application Received",
        "Thanks for applying to Stark Industries. Position: Mobile Developer (iOS)",
        "Stark Industries", "Mobile Developer (iOS)",
    ),
    (
        "Indeed <indeedapply@indeed.com>",
        "Indeed Application: Customer Success Associate",
        "Your application has been submitted to Wayne Enterprises.\nGood luck!",
        None, "Customer Success Associate",  # company found from body or left for review
    ),
]


@pytest.mark.parametrize("sender,subject,body,company,role", CONFIRMATIONS)
def test_confirmations(sender, subject, body, company, role):
    r = classify(mk(sender, subject, body))
    assert r.kind in ("confirmation", "review"), r
    if company:
        assert r.kind == "confirmation", r
        assert r.company == company
    assert r.role == role


def test_indeed_company_from_body():
    r = classify(mk(
        "Indeed <indeedapply@indeed.com>",
        "Indeed Application: Customer Success Associate",
        "Your application has been submitted.\n\nThanks for applying to Wayne Enterprises.",
    ))
    assert r.kind == "confirmation"
    assert r.company == "Wayne Enterprises"


IGNORED = [
    ("LinkedIn <jobalerts-noreply@linkedin.com>", "30+ new jobs for you: Software Engineer",
     "Top job picks for you. Apply now to Acme.", "job alert / recommendations"),
    ("Acme <no-reply@greenhouse.io>", "Your application to Acme",
     "Thank you for applying. Unfortunately, we have decided to move forward with other candidates.",
     "rejection"),
    ("Acme <no-reply@greenhouse.io>", "Next steps with Acme",
     "Thanks for applying! Please complete the coding challenge on HackerRank within 7 days.",
     "assessment / OA"),
    ("Recruiter <jane@acme.com>", "Acme interview",
     "Thanks for your application! I'd like to schedule a call — pick a time at calendly.com/jane",
     "interview / scheduling"),
    ("Acme <noreply@myworkday.com>", "Complete your application",
     "You started an application for Analyst. Finish your application to be considered.",
     "incomplete application"),
    ("Newsletter <news@somecompany.com>", "This week in tech", "Lots of news.",
     "no confirmation phrase"),
]


@pytest.mark.parametrize("sender,subject,body,reason", IGNORED)
def test_ignored(sender, subject, body, reason):
    r = classify(mk(sender, subject, body))
    assert r.kind == "ignore"
    assert r.reason == reason


def test_unknown_company_goes_to_review():
    r = classify(mk("noreply@jobs-mailer.net", "Thank you for applying!",
                    "We received your application and will be in touch."))
    assert r.kind == "review"


def test_non_ats_sender_guess_needs_review():
    r = classify(mk("careers@pied-piper.com", "Application received",
                    "Thank you for applying. We'll be in touch."))
    assert r.kind == "review"
    assert r.company == "Pied-Piper"


def test_normalize_company():
    assert normalize_company("Acme, Inc.") == normalize_company("ACME")
    assert normalize_company("Globex Corporation") == "globex"
