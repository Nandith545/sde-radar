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
    "TypeScript": ["typescript", "ts"],
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
    "AWS": ["aws", "amazon web services", "ec2", "lambda", "dynamodb", "s3", "eks", "sqs", "cloudformation"],
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
    "Machine Learning": ["machine learning", "ml"],
    "Generative AI": ["generative ai", "genai", "gen ai"],
    "LangChain": ["langchain"],
    "RAG": ["retrieval-augmented generation", "retrieval augmented generation", " rag "],
    "LLM": ["llm", "large language model", "large language models"],
    "OpenAI API": ["openai"],
    "Anthropic API": ["anthropic", "claude api"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow"],
    "C++": ["c++"],
    "C#": ["c#", ".net"],
    "Go": ["golang", " go "],
    "Scala": ["scala"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "HTML/CSS": ["html", "css"],
    "Git": ["git", "gitlab", "github"],
    "Agile/Scrum": ["agile", "scrum"],
    "Observability": ["cloudwatch", "datadog", "splunk", "grafana", "prometheus", "observability"],
    "Data Engineering": ["etl", "data pipeline", "data engineering"],
    "Security": ["oauth", "security", "authentication", "authorization"],
}

CANONICAL_TAGS = list(SKILL_ALIASES.keys())

_COMPILED = {
    tag: [
        re.compile(r"(?<![a-zA-Z0-9])" + re.escape(alias.strip()) + r"(?![a-zA-Z0-9])", re.IGNORECASE)
        for alias in aliases
    ]
    for tag, aliases in SKILL_ALIASES.items()
}


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


def extract_years_experience(text: str) -> float | None:
    """Best-effort extraction of a stated years-of-experience figure, e.g.
    '9+ years of experience' -> 9.0. Returns None if nothing plausible found.
    """
    if not text:
        return None
    matches = re.findall(r"(\d{1,2})\s*\+?\s*years?", text, re.IGNORECASE)
    plausible = [int(m) for m in matches if 0 < int(m) <= 45]
    return float(max(plausible)) if plausible else None


def skills_union(skill_lists: Iterable[list[str]]) -> list[str]:
    out: set[str] = set()
    for lst in skill_lists:
        out.update(lst or [])
    return sorted(out)
