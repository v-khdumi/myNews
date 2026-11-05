import copy
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts.synthesize import (
    completion_url, enrich_edition, fingerprint, generate, MAX_SUMMARY_CHARS,
    MAX_SUMMARY_WORDS, SynthesisError, validate_output,
)

ENV = {
    "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
    "AZURE_OPENAI_API_KEY": "test-key-not-a-secret",
    "AZURE_OPENAI_DEPLOYMENT": "test-deployment", "AI_MAX_ARTICLES_PER_RUN": "2",
}
ARTICLE = {
    "id": "test", "title": "Original title", "excerpt": "A short factual RSS excerpt.",
    "source": "guardian", "url": "https://www.theguardian.com/world/test",
}
OUTPUT = {
    "ro": {"title": "Sinteză română", "summary": "O scurtă sinteză a faptelor disponibile."},
    "en": {"title": "English digest", "summary": "A short digest of the available facts."},
    "category": "general",
}


def fake_generate(article, endpoint, key, deployment):
    return {
        **copy.deepcopy(OUTPUT), "input_hash": fingerprint(article), "model": deployment,
        "source_url": article["url"], "generated_at": "2026-11-04T10:00:00Z",
    }


class SynthesisTests(unittest.TestCase):
    def test_only_azure_resource_endpoints_are_accepted(self):
        for endpoint in ("https://test.openai.azure.com", "https://test.openai.azure.com/openai/v1/",
                         "https://test.services.ai.azure.com/openai/v1"):
            self.assertTrue(completion_url(endpoint).endswith("/openai/v1/chat/completions"))
        for endpoint in ("http://test.openai.azure.com", "https://evil.test", "https://test.openai.azure.com.evil.test",
                         "https://test.services.ai.azure.com/api/projects/test", "https://test.openai.azure.com?q=secret"):
            with self.subTest(endpoint=endpoint), self.assertRaises(SynthesisError):
                completion_url(endpoint)

    def test_structured_output_requires_both_languages_and_bounded_text(self):
        self.assertEqual(validate_output(copy.deepcopy(OUTPUT)), OUTPUT)
        for changes in ({"ro": None}, {"category": []}, {"category": "invented"}, {"en": {}},
                        {"en": {"title": "T", "summary": "word " * (MAX_SUMMARY_WORDS + 1)}},
                        {"en": {"title": "T", "summary": "x" * (MAX_SUMMARY_CHARS + 1)}},
                        {"ro": {"title": "T", "summary": "<script>alert(1)</script>"}}):
            with self.subTest(changes=changes), self.assertRaises(SynthesisError):
                validate_output({**copy.deepcopy(OUTPUT), **changes})

    def test_extended_paragraphs_and_exact_upper_limits_are_accepted(self):
        output = copy.deepcopy(OUTPUT)
        output["ro"]["summary"] = "Detalii confirmate despre eveniment. " * 50
        output["en"]["summary"] = "Reported facts.\n\n" + "word " * 298
        self.assertEqual(validate_output(output), output)
        output["en"]["summary"] = "x" * MAX_SUMMARY_CHARS
        self.assertEqual(validate_output(output), output)

    def test_prompt_change_invalidates_previously_short_cached_stories(self):
        data = {"articles": [copy.deepcopy(ARTICLE)]}
        with patch("scripts.synthesize.PROMPT_VERSION", "1"):
            enrich_edition(data, ENV, fake_generate)
        enrich_edition(data, ENV, fake_generate)
        self.assertEqual(data["ai"]["processed_this_run"], 1)

    def test_request_has_grounded_input_json_mode_and_attribution(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            self.assertEqual(timeout, 45)
            return io.BytesIO(json.dumps({
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(OUTPUT)}}],
            }).encode())

        result = generate(ARTICLE, ENV["AZURE_OPENAI_ENDPOINT"], ENV["AZURE_OPENAI_API_KEY"],
                          ENV["AZURE_OPENAI_DEPLOYMENT"], opener)
        self.assertEqual(result["source_url"], ARTICLE["url"])
        self.assertEqual(result["input_hash"], fingerprint(ARTICLE))
        payload = json.loads(requests[0].data)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("untrusted", payload["messages"][0]["content"])
        self.assertIn("160-240 words", payload["messages"][0]["content"])
        self.assertIn("use a shorter brief if the source lacks detail", payload["messages"][0]["content"])
        self.assertEqual(payload["max_completion_tokens"], 3200)
        self.assertEqual(json.loads(payload["messages"][1]["content"])["excerpt"], ARTICLE["excerpt"])

    def test_transport_refusal_and_truncated_results_are_explicit_errors(self):
        for exception in (URLError("down"), HTTPError("https://test", 429, "limited", {}, None)):
            def fail(*_, **__):
                raise exception
            with self.assertRaises(SynthesisError):
                generate(ARTICLE, ENV["AZURE_OPENAI_ENDPOINT"], "key", "model", fail)
        for finish in ("length", "content_filter"):
            def response(*_, **__):
                return io.BytesIO(json.dumps({"choices": [{"finish_reason": finish}]}).encode())
            with self.assertRaises(SynthesisError):
                generate(ARTICLE, ENV["AZURE_OPENAI_ENDPOINT"], "key", "model", response)

    def test_missing_configuration_uses_honest_rss_mode(self):
        data = {"articles": [copy.deepcopy(ARTICLE)]}
        enrich_edition(data, {}, lambda *_: self.fail("AI must not run"))
        self.assertEqual(data["ai"]["status"], "disabled")
        self.assertNotIn("synthesis", data["articles"][0])

    def test_partial_configuration_and_invalid_budget_fail(self):
        for env in ({"AZURE_OPENAI_DEPLOYMENT": "model"}, {**ENV, "AI_MAX_ARTICLES_PER_RUN": "-1"},
                    {**ENV, "AI_MAX_ARTICLES_PER_RUN": "201"}, {**ENV, "AI_MAX_ARTICLES_PER_RUN": "bad"}):
            with self.subTest(env=env), self.assertRaises(SynthesisError):
                enrich_edition({"articles": []}, env)

    def test_budget_cache_and_changed_inputs(self):
        articles = [{**ARTICLE, "id": str(index), "url": f"{ARTICLE['url']}-{index}"} for index in range(4)]
        data = {"articles": articles}
        enrich_edition(data, ENV, fake_generate)
        self.assertEqual(data["ai"]["ready"], 2)
        self.assertEqual(data["ai"]["processed_this_run"], 2)
        enrich_edition(data, ENV, fake_generate)
        self.assertEqual(data["ai"]["ready"], 4)
        self.assertEqual(data["ai"]["processed_this_run"], 2)
        enrich_edition(data, ENV, lambda *_: self.fail("Do not charge twice for cached content"))
        self.assertEqual(data["ai"]["processed_this_run"], 0)
        articles[0]["excerpt"] = "Updated factual input."
        enrich_edition(data, ENV, fake_generate)
        self.assertEqual(data["ai"]["processed_this_run"], 1)

    def test_model_change_regenerates_but_disabling_ai_preserves_valid_digests(self):
        data = {"articles": [copy.deepcopy(ARTICLE)]}
        enrich_edition(data, ENV, fake_generate)
        enrich_edition(data, {}, lambda *_: self.fail("No network without configuration"))
        self.assertEqual(data["ai"]["ready"], 1)
        enrich_edition(data, {**ENV, "AZURE_OPENAI_DEPLOYMENT": "new-model"}, fake_generate)
        self.assertEqual(data["ai"]["processed_this_run"], 1)
        self.assertEqual(data["articles"][0]["synthesis"]["model"], "new-model")

    def test_failure_stops_requests_and_reports_degraded_state(self):
        def fail(*_):
            raise SynthesisError("HTTP 429")
        data = {"articles": [copy.deepcopy(ARTICLE) for _ in range(4)]}
        with self.assertLogs("mynews", "ERROR"):
            enrich_edition(data, ENV, fail)
        self.assertEqual(data["ai"]["status"], "degraded")
        self.assertEqual(data["ai"]["errors"], 1)
        self.assertEqual(data["ai"]["processed_this_run"], 1)
        self.assertEqual(data["ai"]["pending"], 4)
        self.assertIn("ai_error", data["articles"][0])

    def test_empty_excerpt_never_generates_a_full_story_from_a_headline(self):
        data = {"articles": [{**ARTICLE, "excerpt": ""}]}
        enrich_edition(data, ENV, lambda *_: self.fail("Not enough factual input"))
        self.assertEqual(data["ai"]["processed_this_run"], 0)

    def test_wall_clock_budget_preserves_completed_work(self):
        data = {"articles": [{**ARTICLE, "id": str(index)} for index in range(3)]}
        with patch("scripts.synthesize.time.monotonic", side_effect=[0, 0, 301, 302]):
            enrich_edition(data, ENV, fake_generate)
        self.assertEqual(data["ai"]["ready"], 1)
        self.assertEqual(data["ai"]["pending"], 2)

    def test_invalid_cached_provenance_is_regenerated(self):
        data = {"articles": [copy.deepcopy(ARTICLE)]}
        enrich_edition(data, ENV, fake_generate)
        data["articles"][0]["synthesis"]["generated_at"] = None
        with self.assertLogs("mynews", "WARNING"):
            enrich_edition(data, ENV, fake_generate)
        self.assertEqual(data["ai"]["processed_this_run"], 1)
