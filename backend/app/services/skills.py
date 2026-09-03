"""A canonical skills taxonomy used to tag both resumes and job postings so
they can be compared on equal footing. Each canonical tag maps to a list of
surface forms/aliases that might appear in free text; matching is case
insensitive and uses word boundaries so "Go" doesn't match inside "Google".
"""

import re
from collections.abc import Iterable

SKILL_ALIASES: dict[str, list[str]] = {
    "Java": ["java"],
    "Spring Boot": ["spring boot", "springboot", "spring framework"],
    "Python": ["python"],
    "JavaScript": ["javascript", "js"],
    # "ts" is deliberately absent: SpaceX and Axon both post cleared roles,
    # and "TS/SCI clearance" tagged every one of them as TypeScript.
    "TypeScript": ["typescript"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "React": ["react.js", "reactjs", "react"],
    "Angular": ["angular"],
    "Vue": ["vue.js", "vuejs", "vue"],
    "FastAPI": ["fastapi"],
    "Flask": ["flask"],
    "Django": ["django"],
    "SQL": ["sql", "postgresql", "postgres", "mysql", "t-sql", "pl/sql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Kafka": ["kafka"],
    "RabbitMQ": ["rabbitmq"],
    # "lambda" is absent on purpose -- it is an ordinary word in Java, Python
    # and C++ prose, and tagged "lambda expressions in Java" as AWS.
    "AWS": ["aws", "amazon web services", "ec2", "dynamodb", "s3", "eks", "sqs", "cloudformation"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "CI/CD": [
        "ci/cd",
        "continuous integration",
        "continuous deployment",
        "gitlab ci",
        "github actions",
        "jenkins",
    ],
    "Microservices": ["microservices", "microservice"],
    "Distributed Systems": ["distributed systems", "distributed system"],
    "REST APIs": ["restful", "rest api", "rest apis"],
    "GraphQL": ["graphql"],
    "gRPC": ["grpc"],
    "Machine Learning": ["machine learning"],
    "Generative AI": ["generative ai", "genai", "gen ai"],
    "LangChain": ["langchain"],
    "RAG": ["retrieval-augmented generation", "retrieval augmented generation"],
    "LLM": ["llm", "large language model", "large language models"],
    "OpenAI API": ["openai"],
    "Anthropic API": ["anthropic", "claude api"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow"],
    "C++": ["c++"],
    "C#": ["c#", ".net"],
    "Go": ["golang"],
    "Scala": ["scala"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "HTML/CSS": ["html", "css"],
    "Git": ["git", "gitlab", "github"],
    "Agile/Scrum": ["agile", "scrum"],
    "Observability": ["cloudwatch", "datadog", "splunk", "grafana", "prometheus", "observability"],
    "Data Engineering": ["etl", "data pipeline", "data engineering"],
    # Bare "security" is absent: it matches background-check and clearance
    # boilerplate on postings that have nothing to do with security work.
    "Security": ["oauth", "authentication", "authorization"],
}

# Tokens that are a skill only when capitalised exactly, because the
# lowercase form is an ordinary English word. Written as full patterns rather
# than aliases because each needs its own guard; they are matched
# case-sensitively, unlike everything in SKILL_ALIASES.
#
# These used to live in SKILL_ALIASES as " go " and " rag " -- padded with
# spaces to force a word boundary. The padding never took effect: the
# compiler called .strip() on every alias, so both matched the English words,
# and any posting saying "we go above and beyond" listed Go as a requirement.
CASE_SENSITIVE_PATTERNS: dict[str, list[str]] = {
    # "Go to our careers page" is the one common capitalised false positive.
    "Go": [r"(?<![A-Za-z0-9])Go(?!\s+to\b)(?![A-Za-z0-9])"],
    "RAG": [r"(?<![A-Za-z0-9])RAG(?![A-Za-z0-9])"],
    # Lowercase "ml" is millilitres.
    "Machine Learning": [r"(?<![A-Za-z0-9])ML(?![A-Za-z0-9])"],
}

CANONICAL_TAGS = list(SKILL_ALIASES.keys())

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    tag: [
        re.compile(r"(?<![a-zA-Z0-9])" + re.escape(alias.strip()) + r"(?![a-zA-Z0-9])", re.IGNORECASE)
        for alias in aliases
    ]
    for tag, aliases in SKILL_ALIASES.items()
}

for _tag, _patterns in CASE_SENSITIVE_PATTERNS.items():
    _COMPILED.setdefault(_tag, []).extend(re.compile(p) for p in _patterns)


def extract_skills(text: str) -> list[str]:
    """Return the sorted list of canonical skill tags found in free text."""
    if not text:
        return []
    found = set()
    for tag, patterns in _COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                found.add(tag)
                break
    return sorted(found)


# A years figure only counts when the surrounding text ties it to the
# candidate's experience. Taking the largest "N years" anywhere in the
# document -- which is what this did -- read "Acme, founded 30 years ago" as
# thirty years of experience, and "a 12 years running migration project" as
# twelve. Both then inferred senior, which penalises every mid-level posting
# by eight to sixteen points. Taking the maximum made it pick the worst
# reading available.
_YEARS_THEN_EXPERIENCE = re.compile(
    r"(\d{1,2})\s*\+?\s*years?(?:\s+[\w/&-]+){0,4}?\s+experience", re.IGNORECASE
)
_EXPERIENCE_THEN_YEARS = re.compile(r"experience[^.\n]{0,40}?(\d{1,2})\s*\+?\s*years?", re.IGNORECASE)


def extract_years_experience(text: str) -> float | None:
    """A stated years-of-experience figure, e.g. '9+ years of experience'.

    Returns None when nothing anchors a number to the candidate's own
    experience. That is deliberate rather than a fallback to guessing: an
    absent reading leaves seniority to the user's stated preference, while a
    wrong one silently mis-levels every job they see. It is the same
    fail-quiet stance work mode, country and ambiguous cities already take.
    """
    if not text:
        return None
    found = [
        int(m)
        for pattern in (_YEARS_THEN_EXPERIENCE, _EXPERIENCE_THEN_YEARS)
        for m in pattern.findall(text)
        if 0 < int(m) <= 45
    ]
    return float(max(found)) if found else None


def skills_union(skill_lists: Iterable[list[str]]) -> list[str]:
    out: set[str] = set()
    for lst in skill_lists:
        out.update(lst or [])
    return sorted(out)
