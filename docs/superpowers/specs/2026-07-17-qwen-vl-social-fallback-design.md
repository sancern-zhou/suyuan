# Qwen VL Social Fallback Design

## Goal

Add the configured Qwen visual model as the second candidate for social-mode
multimodal LLM requests, after MiMo. A transient MiMo failure must be eligible
to fall through to Qwen without restoring the retired general-purpose `qwen`
provider.

## Design

- Introduce a visual-only LLM provider identifier named `qwen_vl`.
- Load its credentials and endpoint from `QWEN_VL_API_KEY` and
  `QWEN_VL_BASE_URL`.
- Use the OpenAI-compatible chat-completions protocol for `qwen_vl`.
- Select the configured `QWEN_VISION_MODEL` (`qwen3.7-plus` in the current
  environment) in the multimodal candidate chain.
- Set the chain to
  `mimo/mimo-v2.5,qwen_vl/qwen3.7-plus`, preserving MiMo as primary.
- Keep the retired text provider name `qwen` unsupported and leave the OCR
  model `QWEN_VL_MODEL` out of the Agent fallback chain.

## Data Flow

1. Social mode requests the `multimodal` auto profile.
2. Auto-profile parsing chooses MiMo as the primary candidate and `qwen_vl`
   as its fallback.
3. If MiMo returns a failure classified as fallback-eligible, the LLM service
   loads the Qwen VL configuration and retries through the chat-completions
   adapter.
4. If both candidates fail, the existing aggregate failover error behavior is
   retained.

## Error Handling and Security

- Missing Qwen VL credentials continue to fail through the existing provider
  request path; secrets must never be printed by tests or verification output.
- Authentication and non-transient failures retain the existing failover
  classification behavior.
- No live, billable model request is required for automated verification.

## Verification

- Add a focused test proving `qwen_vl` loads the visual Qwen endpoint, key,
  model, and chat-completions mode.
- Add a focused test proving the multimodal profile resolves to MiMo followed
  by Qwen VL.
- Retain the existing test proving the retired `qwen` provider remains
  unsupported.
- Run the focused LLM service tests in the required backend conda environment.

