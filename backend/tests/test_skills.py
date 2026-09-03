"""Skill extraction and resume parsing.

This is keyword/alias matching by design (no LLM), so the tests pin the
behaviour that matters: aliases resolve to one canonical tag, and substrings
inside unrelated words don't produce false hits.
"""

from app.services.resume_parser import parse_resume
from app.services.skills import extract_skills, extract_years_experience


def test_extracts_skills_named_directly() -> None:
    found = extract_skills("Experience with Python, Java and Kubernetes.")
    assert "Python" in found
    assert "Java" in found
    assert "Kubernetes" in found


def test_extraction_is_case_insensitive() -> None:
    assert extract_skills("python and JAVA") == extract_skills("Python and Java")


def test_aliases_collapse_to_a_single_canonical_tag() -> None:
    """'k8s' and 'Kubernetes' are the same skill and must not both appear."""
    found = extract_skills("We run k8s in production.")
    assert "Kubernetes" in found
    assert "k8s" not in found


def test_results_have_no_duplicates() -> None:
    found = extract_skills("Python Python python PYTHON")
    assert found.count("Python") == 1


def test_empty_input_yields_no_skills() -> None:
    assert extract_skills("") == []


def test_unrelated_prose_does_not_produce_false_positives() -> None:
    found = extract_skills("I enjoy hiking, cooking and playing the guitar.")
    assert found == []


def test_java_is_not_matched_inside_javascript() -> None:
    """A naive substring match would tag every JavaScript CV as a Java CV."""
    found = extract_skills("Frontend work in JavaScript only.")
    assert "JavaScript" in found
    assert "Java" not in found


def test_years_of_experience_is_extracted() -> None:
    assert extract_years_experience("Senior engineer with 8 years of experience") == 8.0


def test_missing_years_of_experience_returns_none() -> None:
    assert extract_years_experience("Senior engineer") is None


def test_parse_resume_returns_text_skills_and_experience() -> None:
    content = b"Jane Dev\n10 years of experience\nSkills: Python, AWS, Docker"
    parsed = parse_resume("resume.txt", content)

    assert "Jane Dev" in parsed["raw_text"]
    assert "Python" in parsed["skills"]
    assert parsed["years_experience"] == 10.0


def test_parse_resume_tolerates_undecodable_bytes() -> None:
    """A mislabelled or binary upload should degrade gracefully, not raise."""
    parsed = parse_resume("resume.txt", b"\xff\xfe\x00Python\x00")
    assert isinstance(parsed["raw_text"], str)
    assert isinstance(parsed["skills"], list)


# ---- Words that are skills only in the right shape ----------------------


def test_english_verbs_are_not_programming_languages() -> None:
    """The aliases were written " go " and " rag " to force a word boundary,
    but the compiler stripped the padding, so ordinary prose tagged both."""
    assert extract_skills("We go above and beyond. Please go to our careers page.") == []
    assert extract_skills("Bring a rag and elbow grease.") == []


def test_go_is_still_found_when_it_is_the_language() -> None:
    assert "Go" in extract_skills("Experience with Go and Java")
    assert "Go" in extract_skills("golang microservices")


def test_rag_and_ml_are_found_when_capitalised() -> None:
    assert "RAG" in extract_skills("RAG pipelines over a vector store")
    assert "Machine Learning" in extract_skills("ML infrastructure")
    assert extract_skills("Pipetting 50 ml samples") == []


def test_lambda_in_a_language_sense_is_not_aws() -> None:
    assert extract_skills("Comfortable with lambda expressions in Java") == ["Java"]


def test_a_security_clearance_is_not_typescript() -> None:
    """SpaceX and Axon both post cleared roles; "TS/SCI" tagged every one of
    them as a TypeScript job."""
    assert extract_skills("Must hold an active TS/SCI clearance.") == []


def test_background_check_boilerplate_is_not_a_security_skill() -> None:
    assert extract_skills("Offers are contingent on a security background check.") == []
    assert "Security" in extract_skills("OAuth and authorization flows")
