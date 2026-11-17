import pytest

import rag


@pytest.mark.parametrize(
    "question",
    [
        "What is MSME?",
        "how do I apply for a loan",
        "tell me about the CM Yuva scheme",
        "Which schemes are available?",
        "Are there any subsidies for startups",
        "Ramp yojana details",
        "How to register on msmeosem.in",
        "Visit www.upicon.in for training",
        "what services does cm youth adda offer",
        "एमएसएमई क्या है",
        "योजनाओं की जानकारी दें",
        "मुझे ऋण चाहिए",
        "How are loans processed?",
    ],
)
def test_supported_questions_pass(question):
    assert rag._is_supported_question(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "What is the capital of France?",
        "Tell me a joke",
        "Write a python function to sort a list",
        "Who won the cricket match yesterday",
        "How do I ramble through a forest",
        "Give me an example of recursion",
        "investigation of a crime",
        "आज मौसम कैसा है",
    ],
)
def test_unsupported_questions_are_rejected(question):
    assert rag._is_supported_question(question) is False


def test_short_keywords_do_not_match_inside_other_words():
    assert rag._match_topic_urls("give me an example") == []
    assert rag._match_topic_urls("I will investigate this") == []
    assert rag._match_topic_urls("a rampage of contactless cards") == []
    assert rag._match_topic_urls("the loaner car") == []


def test_keywords_still_match_as_whole_words():
    assert "https://cmyuva.org.in/" in rag._match_topic_urls("what is ramp")
    assert "https://invest.up.gov.in" in rag._match_topic_urls("invest up summit")
    assert "https://upicon.in/contact" in rag._match_topic_urls("upicon contact details")


def test_msme_and_osem_urls_are_prioritized():
    urls = rag._match_topic_urls("msme loan scheme")
    assert urls[:2] == ["https://msmeosem.in/", "https://msme.up.gov.in/"]


def test_hostname_must_be_a_whole_token():
    assert rag._match_topic_urls("notmsmeosem.in is a fake site") == []
    assert "https://msmeosem.in/" in rag._match_topic_urls("open msmeosem.in now")


def test_unsupported_question_gets_refusal_without_llm(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("LLM must not be called for off-topic questions")

    monkeypatch.setattr(rag.groq_client, "generate_answer", fail)
    answer, lang = rag.answer_query("Tell me a joke", "en")
    assert "Sorry" in answer
    assert lang == "en"
