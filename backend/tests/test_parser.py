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


# Confirmations that describe possible next steps must not be mistaken for rejections, OA invites
# or interview requests (#26).
NEXT_STEP_CONFIRMATIONS = [
    ("Acme Robotics <no-reply@us.greenhouse-mail.io>", "Thank you for applying to Acme Robotics!",
     "Thanks for your interest in Acme Robotics! We received your application for Software "
     "Engineering Intern (Summer 2027). If we decide not to move forward with your application, "
     "we will let you know by email.", "Acme Robotics", "Software Engineering Intern (Summer 2027)"),
    ("Northwind <no-reply@hire.lever.co>", "Thank you for your application to Northwind",
     "Thank you for applying to the Software Engineer Intern position at Northwind. If your "
     "background is a fit, a recruiter will reach out to schedule an interview.",
     "Northwind", "Software Engineer Intern"),
    ("Initech <no-reply@ashbyhq.com>", "Thanks for applying to Initech",
     "Thanks for applying to the Backend Intern role at Initech. Next steps: shortlisted "
     "candidates may receive a HackerRank online assessment.", "Initech", "Backend Intern"),
    ("Hooli Careers <hooli@myworkday.com>", "Thank you for applying!",
     "Thank you for your interest in Hooli. We have received your application for the Data Intern "
     "position. Unfortunately, due to the high volume of applications, we are unable to respond "
     "to each applicant individually.", "Hooli", "Data Intern"),
]


@pytest.mark.parametrize("sender,subject,body,company,role", NEXT_STEP_CONFIRMATIONS)
def test_confirmations_that_mention_next_steps(sender, subject, body, company, role):
    r = classify(mk(sender, subject, body))
    assert (r.kind, r.company, r.role) == ("confirmation", company, role), r


REAL_REJECTIONS = [
    "Thank you for your interest in Acme. After careful consideration, we will not be moving "
    "forward with your application.",
    "Thank you for applying. Unfortunately, we have decided to go with other candidates.",
    "We appreciate your interest. We have decided to pursue other applicants for this role.",
    "Thanks for applying to Acme. We will not be progressing your application at this time.",
    "Unfortunately, the position has been filled.",
]


@pytest.mark.parametrize("body", REAL_REJECTIONS)
def test_real_rejections_are_still_ignored(body):
    r = classify(mk("Acme <no-reply@greenhouse.io>", "Your application to Acme", body))
    assert (r.kind, r.reason) == ("ignore", "rejection"), r


def test_oa_or_interview_in_the_subject_still_wins():
    r = classify(mk("Acme <no-reply@greenhouse.io>", "Acme online assessment invitation",
                    "Thanks for applying! Please complete the assessment within 7 days."))
    assert (r.kind, r.reason) == ("ignore", "assessment / OA")
    r = classify(mk("Recruiter <jane@acme.com>", "Interview request - Acme",
                    "Thank you for your application! Could you share your availability for a call?"))
    assert (r.kind, r.reason) == ("ignore", "interview / scheduling")


def test_polite_questions_are_not_conditional():
    r = classify(mk("Recruiter <jane@acme.com>", "Next steps with Acme",
                    "Thanks for your application! Could you share your availability for a call?"))
    assert (r.kind, r.reason) == ("ignore", "interview / scheduling")


@pytest.mark.parametrize("subject", [
    "Your application to Acme | Software Engineer Intern",
    "Thank you for applying to Acme - Software Engineer Intern",
    "Thanks for applying to Acme – Software Engineer Intern!",
    "Your application with Acme — Software Engineer Intern",
])
def test_role_after_a_separator_in_the_subject(subject):
    r = classify(mk("Acme <no-reply@greenhouse.io>", subject, "Thanks for applying."))
    assert (r.kind, r.company, r.role) == ("confirmation", "Acme", "Software Engineer Intern"), r


def test_confirmation_words_after_a_separator_are_not_a_role():
    r = classify(mk("Acme <no-reply@greenhouse.io>", "Thank you for applying to Acme - Application received",
                    "We received your application."))
    assert (r.kind, r.company, r.role) == ("confirmation", "Acme", ""), r


def test_hyphenated_company_names_survive():
    r = classify(mk("Rolls-Royce <no-reply@greenhouse.io>", "Thank you for applying to Rolls-Royce",
                    "Thanks for applying."))
    assert (r.kind, r.company) == ("confirmation", "Rolls-Royce"), r


# Wrong data is worse than missing data (#38): each of these used to be saved incorrectly.
WRONG_DATA_CASES = [
    ("Acme Careers <acme@myworkday.com>", "Thank you for applying!",
     "Thank you for applying for the position of Software Engineer Intern at Acme. We will review "
     "your qualifications.", "Acme", "Software Engineer Intern"),
    ("Acme <noreply@icims.com>", "Thank you for your interest in Acme",
     "Thank you for your interest in the role of Data Analyst Co-op. Your application has been received.",
     "Acme", "Data Analyst Co-op"),
    ("Acme <no-reply@ashbyhq.com>", "Your Acme application",
     "Thanks for applying to the Platform Engineer role.", "Acme", "Platform Engineer"),
    ("Acme Hiring <no-reply@greenhouse-mail.io>", "Thank you for applying to Acme!",
     "Thank you for your interest in Acme! We wanted to let you know we received your application for "
     "Software Engineer, New Grad - 2027, and we are delighted that you would consider joining our team.",
     "Acme", "Software Engineer, New Grad - 2027"),
    ("SAP SuccessFactors <noreply@successfactors.com>", "Acme: Application Received",
     "We have received your application for Requisition 12345 - Software Engineer.",
     "Acme", "Software Engineer"),
    ("Workday <acme@myworkday.com>", "Application Received",
     "Thank you for submitting your application for the role of Product Manager Intern, Summer 2027 "
     "(R-12345). We will be in touch.", "Acme", "Product Manager Intern, Summer 2027"),
    ("Acme Talent <talent@smartrecruiters.com>", "Your application for Software Developer has been received",
     "Thanks for applying to Acme.", "Acme", "Software Developer"),
    ("Acme <no-reply@greenhouse.io>", "We've received your application to Acme",
     "Hi Ryan, thanks for applying.", "Acme", ""),
]


@pytest.mark.parametrize("sender,subject,body,company,role", WRONG_DATA_CASES)
def test_extracts_the_right_company_and_role(sender, subject, body, company, role):
    r = classify(mk(sender, subject, body))
    assert (r.kind, r.company, r.role) == ("confirmation", company, role), r


def test_subject_company_beats_sender_for_received_to():
    r = classify(mk("Recruiting <no-reply@greenhouse.io>", "We've received your application to Acme",
                    "Thanks for applying."))
    assert (r.company, r.reason) == ("Acme", "subject match")


@pytest.mark.parametrize("raw,expected", [
    ("Software Engineer (R-12345)", "Software Engineer"),
    ("Software Engineer - JR123456", "Software Engineer"),
    ("Req #4521 - Data Analyst", "Data Analyst"),
    ("Software Engineer Intern (2027)", "Software Engineer Intern (2027)"),
    ("Intern - Fall2027", "Intern - Fall2027"),
    ("the", ""),
])
def test_clean_role(raw, expected):
    from app.parser import clean_role
    assert clean_role(raw) == expected


def test_confirmation_of_application_subject_gives_the_role():
    r = classify(mk("Acme Recruiting <recruiting@acme.com>", "Confirmation of your application - QA Engineer",
                    "Thank you for applying. Our team will review your application."))
    assert r.role == "QA Engineer"
