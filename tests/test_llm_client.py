"""Tests for llm_client.py — centralized LLM provider abstraction."""

from unittest.mock import MagicMock, patch

import pytest

from llm_client import LLMClient, OpenAIClient, create_llm_client


class TestLLMClientProtocol:
    def test_protocol_is_runtime_checkable(self):
        """Verify the protocol can be used with isinstance checks."""
        mock = MagicMock(spec=LLMClient)
        assert isinstance(mock, LLMClient)

    def test_custom_implementation_satisfies_protocol(self):
        """A class with a complete() method satisfies LLMClient."""
        class MyClient:
            def complete(self, system_prompt, user_prompt, temperature=0.4, max_tokens=500):
                return "response"

        client = MyClient()
        assert isinstance(client, LLMClient)


class TestOpenAIClient:
    @patch("llm_client.OpenAI")
    def test_successful_call(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = "  Great sprint.  "
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        result = client.complete("system", "user")
        assert result == "Great sprint."

    @patch("llm_client.OpenAI")
    def test_empty_choices_returns_none(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(choices=[])

        client = OpenAIClient(api_key="sk-test")
        assert client.complete("system", "user") is None

    @patch("llm_client.OpenAI")
    def test_null_content_returns_none(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        client = OpenAIClient(api_key="sk-test")
        assert client.complete("system", "user") is None

    @patch("llm_client.OpenAI")
    def test_api_error_returns_none(self, MockOpenAI):
        import openai
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("fail")

        client = OpenAIClient(api_key="sk-test")
        assert client.complete("system", "user") is None

    @patch("llm_client.OpenAI")
    def test_model_passed_to_api(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = "Summary"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        client = OpenAIClient(api_key="sk-test", model="gpt-3.5-turbo")
        client.complete("sys", "user")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-3.5-turbo"

    @patch("llm_client.OpenAI")
    def test_temperature_and_max_tokens_passed(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = "Summary"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )

        client = OpenAIClient(api_key="sk-test")
        client.complete("sys", "user", temperature=0.8, max_tokens=1000)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.8
        assert call_kwargs["max_tokens"] == 1000

    @patch("llm_client.OpenAI")
    def test_model_property(self, MockOpenAI):
        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        assert client.model == "gpt-4o"


class TestCreateLLMClient:
    def test_no_api_key_returns_none(self):
        assert create_llm_client(api_key=None) is None

    def test_empty_api_key_returns_none(self):
        assert create_llm_client(api_key="") is None

    @patch("llm_client.OpenAIClient")
    def test_openai_provider(self, MockOpenAIClient):
        MockOpenAIClient.return_value = MagicMock()
        client = create_llm_client(provider="openai", api_key="sk-test", model="gpt-4o")
        assert client is not None
        MockOpenAIClient.assert_called_once_with(api_key="sk-test", model="gpt-4o")

    def test_unknown_provider_returns_none(self):
        result = create_llm_client(provider="unknown", api_key="key")
        assert result is None

    def test_default_provider_is_openai(self):
        with patch("llm_client.OpenAIClient") as MockOpenAIClient:
            MockOpenAIClient.return_value = MagicMock()
            create_llm_client(api_key="sk-test")
            MockOpenAIClient.assert_called_once()
