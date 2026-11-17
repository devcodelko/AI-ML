import rag


def test_exact_pattern_returns_intent_response():
    answer = rag._intent_answer("What is CMYUVA?")
    assert answer is not None
    assert "CMYUVA" in answer


def test_case_and_punctuation_are_ignored():
    assert rag._intent_answer("what is cmyuva") == rag._intent_answer("What is CMYUVA?")


def test_close_paraphrase_matches():
    assert rag._intent_answer("Tell me about CMYUVA please") == rag._intent_answer("What is CMYUVA?")


def test_unrelated_question_does_not_match():
    assert rag._intent_answer("what is the capital of france") is None


def test_empty_question_does_not_match():
    assert rag._intent_answer("") is None
    assert rag._intent_answer("?!") is None


def test_fallback_intent_is_never_returned():
    fallback_responses = {
        response
        for intent in rag.INTENTS
        if intent.get("intent") == "fallback"
        for response in intent["responses"]
    }
    assert rag._intent_answer("zzz qqq") not in fallback_responses
