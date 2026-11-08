"""Rule-based detection of application-confirmation emails.

Given one email (sender, subject, plain-text body), decide:
  - "confirmation": confident it's a "thanks for applying" email and we know the company
                    -> the sync creates an application automatically
  - "review":       looks like a confirmation but something's missing (usually the company)
                    -> goes into the review queue for a one-click accept
  - "ignore":       not a confirmation (job alert, rejection, OA invite, newsletter, ...)

Everything here is plain regex so it's free, private and predictable. If you add an LLM later,
the natural place is `classify()` as a fallback for "review" results.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parseaddr

# --------------------------------------------------------------------------------------
# Known applicant tracking systems (ATS), keyed by sender domain suffix
# --------------------------------------------------------------------------------------
ATS_DOMAINS: dict[str, str] = {
    "greenhouse.io": "greenhouse",
    "greenhouse-mail.io": "greenhouse",
    "lever.co": "lever",
    "myworkday.com": "workday",
    "myworkdayjobs.com": "workday",
    "workday.com": "workday",
    "ashbyhq.com": "ashby",
    "smartrecruiters.com": "smartrecruiters",
    "icims.com": "icims",
    "workable.com": "workable",
    "workablemail.com": "workable",
    "jobvite.com": "jobvite",
    "taleo.net": "taleo",
    "successfactors.com": "successfactors",
    "successfactors.eu": "successfactors",
    "bamboohr.com": "bamboohr",
    "applytojob.com": "jazzhr",
    "jazzhr.com": "jazzhr",
    "recruitee.com": "recruitee",
    "breezy.hr": "breezy",
    "rippling.com": "rippling",
    "dover.com": "dover",
    "wellfound.com": "wellfound",
    "joinhandshake.com": "handshake",
    "linkedin.com": "linkedin",
    "indeed.com": "indeed",
    "indeedemail.com": "indeed",
    "teamtailor.com": "teamtailor",
    "pinpointhq.com": "pinpoint",
    "oraclecloud.com": "oracle",
}

ATS_NAMES = set(ATS_DOMAINS.values()) | {"no-reply", "noreply", "notifications", "talent"}

FREE_MAIL = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me"}

# --------------------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------------------
CONFIRM_PHRASES = [
    r"thank(?:s| you) for (?:applying|your application|submitting your application)",
    r"(?:we(?:'ve| have)?|has been|have) received your application",
    r"your application (?:has been|was) (?:received|submitted|sent)",
    r"application (?:has been |was )?(?:received|submitted)",
    r"your application was sent to",
    r"successfully (?:applied|submitted your application)",
    r"thank(?:s| you) for (?:your )?interest in",
    r"application confirmation",
]
CONFIRM_RE = re.compile("|".join(CONFIRM_PHRASES), re.I)

# Things that are *not* new applications. Checked before confirmation phrases, because
# rejections and OA invites often also say "thank you for applying".
#
# Each rule: (reason, pattern, skip_conditional, subject_only_if_confirmation)
#   skip_conditional: ignore matches inside a conditional sentence ("If we decide not to move
#       forward...", "candidates may receive a HackerRank assessment"), which confirmations use
#       to describe what *might* happen next.
#   subject_only_if_confirmation: when the subject itself is a confirmation ("Thank you for
#       applying to Acme"), only count this rule if it matches the subject, not the body.
IGNORE_RULES: list[tuple[str, re.Pattern, bool, bool]] = [
    ("job alert / recommendations", re.compile(
        r"job alert|jobs? (?:for you|you may|recommended|matching)|recommended jobs|new jobs|"
        r"top job picks|is hiring|are hiring|people also viewed|similar jobs|jobs near you|"
        r"apply now to|still accepting applications|unsubscribe from (?:job|these) alerts", re.I),
     False, False),
    # No bare "unfortunately": confirmations say "Unfortunately, due to the high volume of
    # applications, we can't respond to everyone". Only phrases that actually reject.
    ("rejection", re.compile(
        r"regret to inform|not (?:to )?(?:be )?mov(?:e|ing) forward|"
        r"decided not to (?:proceed|pursue|move forward|continue|progress)|"
        r"(?:decided|chosen|elected) to (?:pursue|proceed with|move forward with|go with) (?:other|another)|"
        r"(?:go|proceed|move forward) with (?:other|another|a different) (?:candidate|applicant)|"
        r"pursue other (?:candidates|applicants)|other candidates (?:whose|who)|"
        r"position has been filled|no longer (?:under consideration|considering)|"
        r"not been selected|will not be proceeding|won't be moving forward|"
        r"not (?:be )?progress(?:ing)? (?:with )?your application|unable to offer you", re.I),
     True, False),
    ("assessment / OA", re.compile(
        r"online assessment|coding (?:challenge|assessment)|hackerrank|codesignal|codility|"
        r"take-?home|complete (?:the|your|this) assessment|assessment invitation", re.I),
     True, True),
    ("interview / scheduling", re.compile(
        r"schedule (?:a|an|your) (?:call|interview|chat|time)|interview (?:invitation|request|confirmation)|"
        r"invite you to (?:an )?interview|availability for (?:a|an)|calendly\.com|goodtime\.io", re.I),
     True, True),
    ("offer", re.compile(r"pleased to (?:offer|extend)|offer letter", re.I), True, True),
    ("incomplete application", re.compile(
        r"finish your application|complete your application|you started an application|"
        r"application (?:is )?incomplete", re.I),
     False, False),
]

# Words that make a sentence hypothetical: "if", "should", "may", ...
CONDITIONAL_RE = re.compile(
    r"\b(?:if|should|whether|unless|in case|in the event|may(?! we| i\b)|might|could(?! you| we)|once)\b", re.I
)
_SENTENCE_START_RE = re.compile(r"[.!?\n]")


def affirmative_match(rx: re.Pattern, text: str) -> bool:
    """True if `rx` matches somewhere that isn't inside a conditional sentence."""
    for m in rx.finditer(text):
        starts = [x.end() for x in _SENTENCE_START_RE.finditer(text, 0, m.start())]
        prefix = text[starts[-1] if starts else 0 : m.start()]
        if not CONDITIONAL_RE.search(prefix):
            return True
    return False


# Cheap header-only prefilter: is this email worth downloading the body for?
PREFILTER_SUBJECT_RE = re.compile(
    r"appl(?:y|ying|ied|ication)|candida|interest in|thank(?:s| you) for", re.I
)

# --------------------------------------------------------------------------------------
# Extraction patterns
# --------------------------------------------------------------------------------------
# "tempered" classes: a name may contain "." (Sr. Engineer, Acme Inc.) but never crosses a
# sentence boundary (". " or "." at end of line)
_NOT_SENTENCE_END = r"(?:(?!\.\s|\.$)[^\n!?|])"
_CO = rf"(?P<company>{_NOT_SENTENCE_END}{{2,80}}?)"
_ROLE = rf"(?P<role>{_NOT_SENTENCE_END}{{2,120}}?)"
_END = r"\s*[!.]*\s*$"

SUBJECT_PATTERNS = [
    re.compile(rf"^your application (?:for|to) (?:the )?{_ROLE} (?:at|with) {_CO}{_END}", re.I),
    re.compile(rf"^thank(?:s| you) for applying (?:for|to) (?:the )?{_ROLE} (?:position |role )?at {_CO}{_END}", re.I),
    re.compile(rf"^your application was sent to {_CO}{_END}", re.I),
    re.compile(rf"^indeed application:\s*{_ROLE}{_END}", re.I),
    # "Your application to Acme | Software Engineer Intern", "Thanks for applying to Acme - Data Intern"
    re.compile(rf"^(?:thank(?:s| you) for (?:applying|your application|your interest)(?: to| at| with| in)?|your application (?:to|at|with)) {_CO}\s+[-–—|]\s+{_ROLE}{_END}", re.I),
    re.compile(rf"^thank(?:s| you) for (?:applying|your application|your interest)(?: to| at| with| in)? {_CO}{_END}", re.I),
    re.compile(rf"^your application (?:to|at|with) {_CO}{_END}", re.I),
    re.compile(rf"^{_CO}\s*[-–—|:]\s*(?:application (?:received|confirmation|submitted)|thank(?:s| you) for (?:applying|your application)){_END}", re.I),
    re.compile(rf"^(?:application (?:received|confirmation|submitted)|thank(?:s| you) for (?:applying|your application))\s*[-–—|:]\s*{_ROLE}(?: (?:at|with|[-–—|]) {_CO})?{_END}", re.I),
    re.compile(rf"^we(?:'ve| have)? received your application(?: for (?:the )?{_ROLE})?(?: at {_CO})?{_END}", re.I),
]

_BODY_ROLE_AT_CO = [
    rf"(?:application|applying|applied) (?:for|to) (?:the |our )?{_ROLE} (?:position|role|job|opening|posting)?\s*(?:at|with) {_CO}(?=[.,!\n]|\s+(?:and|we|has|is|was)\b)",
    rf"interest in (?:the |our )?{_ROLE} (?:position|role|opening|job) (?:at|with) {_CO}(?=[.,!\n]|\s+(?:and|we)\b)",
]
_BODY_ROLE = [
    rf"(?:application|applying|applied|interest) (?:for|to|in) (?:the |our |a )?{_ROLE} (?:position|role|job|opening|posting)\b",
    r"\b(?:position|job title|role|job)\s*:\s*(?P<role>[^\n]{2,120})$",
    rf"(?:received your application|your application|application) for (?:the |our )?{_ROLE}(?=[,!\n]|\.\s|\.$|\s+(?:and|has|was|is)\b)",
]
_BODY_CO = [
    rf"(?:interest in|applying to|applying at|application to|application with|apply to|applied to|joining|here at|team at|career(?:s)? at) {_CO}(?=[.,!\n]|\s+(?:and|we|has|is|was|for)\b)",
]
BODY_ROLE_AT_CO_RES = [re.compile(p, re.I | re.M) for p in _BODY_ROLE_AT_CO]
BODY_ROLE_RES = [re.compile(p, re.I | re.M) for p in _BODY_ROLE]
# company patterns are case-sensitive on purpose: real company names start with a capital
BODY_CO_RES = [re.compile(p, re.M) for p in _BODY_CO]

SENDER_NOISE_RE = re.compile(
    r"\b(?:via \w+|recruit(?:ing|ment|er|ers)?|careers?|talent(?: acquisition)?|hiring(?: team)?|"
    r"hr|jobs?|people(?: team)?|team|no-?reply|notifications?|workday|talent team|"
    r"university|campus|early careers?)\b|@.*$",
    re.I,
)
BAD_COMPANY_RE = re.compile(
    r"^(?:the|our|a|an|this|your|us|you|position|role|job|team|company|applying|application)\b", re.I
)


@dataclass
class EmailInput:
    message_id: str
    sender: str
    subject: str
    body: str


@dataclass
class ParseResult:
    kind: str  # confirmation | review | ignore
    company: str = ""
    role: str = ""
    ats: str = ""
    reason: str = ""


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def sender_parts(sender: str) -> tuple[str, str, str]:
    """'Acme Recruiting <no-reply@us.greenhouse-mail.io>' -> (display, local, domain)"""
    name, addr = parseaddr(sender)
    local, _, domain = addr.lower().partition("@")
    return name.strip().strip('"'), local, domain


def detect_ats(domain: str) -> str:
    for suffix, ats in ATS_DOMAINS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return ats
    return ""


def is_prefilter_candidate(sender: str, subject: str) -> bool:
    """Header-only check so we only download bodies for plausible emails."""
    _, _, domain = sender_parts(sender)
    ats = detect_ats(domain)
    if ats and ats not in {"linkedin", "indeed"}:
        return True  # any ATS email is worth a look
    return bool(PREFILTER_SUBJECT_RE.search(subject or ""))


def clean_company(raw: str) -> str:
    s = (raw or "").strip().strip("\"'“”‘’ ")
    s = re.sub(r"[!.?,:;]+$", "", s).strip()
    s = re.sub(r"'s$|’s$", "", s).strip()
    s = re.sub(r"\s+(?:team|careers|recruiting|hiring team|talent team)$", "", s, flags=re.I).strip()
    s = re.sub(r"^the\s+", "", s, flags=re.I) if s.lower().startswith("the ") and len(s.split()) > 2 else s
    if not s or len(s) > 60 or len(s.split()) > 7:
        return ""
    if BAD_COMPANY_RE.match(s):
        return ""
    if s.lower() in ATS_NAMES:
        return ""
    return s


def clean_role(raw: str, company: str = "") -> str:
    s = (raw or "").strip().strip("\"'“”‘’ ")
    s = re.sub(r"^(?:the|our|a|an)\s+", "", s, flags=re.I)
    s = re.sub(r"\s+(?:position|role|job|opening|posting)$", "", s, flags=re.I)
    if company:
        s = re.sub(rf"\s+(?:at|with)\s+{re.escape(company)}.*$", "", s, flags=re.I)
    s = re.sub(r"[!.,:;]+$", "", s).strip()
    if not s or len(s) > 100 or len(s.split()) > 14:
        return ""
    if s.lower() in {"job", "position", "role", "opening", "application"}:
        return ""
    # "Thanks for applying to Acme - Application received": the second half isn't a role
    if CONFIRM_RE.search(s) or re.match(r"(?:application|thank)", s, re.I):
        return ""
    return s


def normalize_company(name: str) -> str:
    """For duplicate matching: 'Acme, Inc.' == 'acme'"""
    s = name.lower()
    s = re.sub(r"[^\w\s&]", " ", s)
    s = re.sub(r"\b(?:inc|llc|ltd|limited|corp|corporation|co|gmbh|plc|technologies|labs)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_role(role: str) -> str:
    s = role.lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)  # drop "(Remote)", "[2026]" etc
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def company_from_sender(sender: str, ats: str) -> str:
    name, local, domain = sender_parts(sender)
    # Workday sends from <tenant>@myworkday.com
    if ats == "workday" and local and local not in {"noreply", "no-reply", "donotreply"}:
        return clean_company(local.replace("_", " ").replace("-", " ").title())
    if name:
        stripped = SENDER_NOISE_RE.sub(" ", name)
        stripped = re.sub(r"[-|@:•·,]+", " ", stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        guess = clean_company(stripped)
        if guess and guess.lower() not in ATS_NAMES:
            return guess
    if not ats and domain and domain not in FREE_MAIL:
        parts = domain.split(".")
        label = parts[-2] if len(parts) >= 2 else parts[0]
        return clean_company(label.title())
    return ""


def linkedin_role(body: str, company: str) -> str:
    """LinkedIn bodies list the role on the line before '<Company> · <Location>'."""
    if not company:
        return ""
    lines = [ln.strip() for ln in body.splitlines()]
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(company)}\s*[·•]", ln):
            for prev in reversed(lines[:i]):
                if prev:
                    return clean_role(prev, company)
    return ""


# --------------------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------------------
def classify(email: EmailInput) -> ParseResult:
    subject = re.sub(r"\s+", " ", (email.subject or "")).strip()
    subject = re.sub(r"^(?:re|fwd?):\s*", "", subject, flags=re.I)
    # "Ryan, your application was sent to X" -> "your application was sent to X"
    subject = re.sub(r"^[A-Z][a-z]+,\s+(?=(?:your|thank|thanks|we)\b)", "", subject, flags=re.I)
    body = (email.body or "")[:8000]
    text = f"{subject}\n{body}"
    _, _, domain = sender_parts(email.sender)
    ats = detect_ats(domain)

    subject_confirms = bool(CONFIRM_RE.search(subject)) or any(p.match(subject) for p in SUBJECT_PATTERNS)
    for reason, rx, skip_conditional, subject_only in IGNORE_RULES:
        scope = subject if (subject_only and subject_confirms) else text
        hit = affirmative_match(rx, scope) if skip_conditional else bool(rx.search(scope))
        if hit:
            return ParseResult("ignore", ats=ats, reason=reason)

    if not CONFIRM_RE.search(text):
        return ParseResult("ignore", ats=ats, reason="no confirmation phrase")

    company, role = "", ""
    from_subject = False

    for rx in SUBJECT_PATTERNS:
        m = rx.match(subject)
        if not m:
            continue
        gd = m.groupdict()
        company = clean_company(gd.get("company") or "")
        role = clean_role(gd.get("role") or "", company)
        from_subject = bool(company)
        break

    if not (company and role):
        for rx in BODY_ROLE_AT_CO_RES:
            m = rx.search(body)
            if m:
                c = clean_company(m.group("company"))
                r = clean_role(m.group("role"), c)
                company = company or c
                role = role or r
                if company and role:
                    break

    if not role:
        for rx in BODY_ROLE_RES:
            m = rx.search(body)
            if m:
                role = clean_role(m.group("role"), company)
                if role:
                    break

    if not company:
        for rx in BODY_CO_RES:
            m = rx.search(body)
            if m:
                company = clean_company(m.group("company"))
                if company:
                    break

    if ats == "linkedin" and not role:
        role = linkedin_role(body, company)

    sender_guess = False
    if not company:
        company = company_from_sender(email.sender, ats)
        sender_guess = bool(company)

    if not company:
        return ParseResult("review", role=role, ats=ats, reason="confirmation, but company not found")

    # A company guessed only from the sender is trusted for ATS emails (their display name is
    # usually the company); for everything else ask for a quick review.
    if sender_guess and not ats:
        return ParseResult("review", company=company, role=role, ats=ats,
                           reason="company guessed from sender")

    reason = "subject match" if from_subject else ("sender name" if sender_guess else "body match")
    return ParseResult("confirmation", company=company, role=role, ats=ats, reason=reason)
