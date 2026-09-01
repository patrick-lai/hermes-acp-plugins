from hermes_acp.completion import make_completion


def test_completion_has_openai_attribute_shape_and_zero_usage() -> None:
    completion = make_completion(model="grok", content="answer", reasoning="thought")
    assert completion.model == "grok"
    assert completion.provider == "acp"
    assert completion.acp_backend == "grok"
    assert completion.choices[0].message.content == "answer"
    assert completion.choices[0].message.tool_calls is None
    assert completion.choices[0].message.reasoning == "thought"
    assert completion.choices[0].message.reasoning_content == "thought"
    assert completion.choices[0].finish_reason == "stop"
    assert completion.usage.prompt_tokens == 0
    assert completion.usage.completion_tokens == 0
    assert completion.usage.total_tokens == 0
