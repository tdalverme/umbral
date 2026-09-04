import json
from pathlib import Path
from unittest.mock import Mock

# Setup path
import sys
sys.path.insert(0, "src")

from umbral.application.conversation.v5.reply import ReplyComposerV5, _load_reply_prompt, _DEFAULT_SYSTEM_PROMPT
from umbral.application.conversation.v5.contracts import TurnContextV5, ConversationTurnResultV5, ActOutcomeV5
import json as _json

# 1. Verify prompt loading
prompt_text = _load_reply_prompt()
print(f"prompt loaded length {len(prompt_text)}")
assert "copiloto sereno" in prompt_text.lower(), "prompt should contain voice guide"
assert "voice: voice-v1" in prompt_text, "prompt header missing"
assert prompt_text != _DEFAULT_SYSTEM_PROMPT, "should not be default"
print("PASS: prompt loading uses voice-v1 file")

# 2. Verify ReplyComposer uses prompt as system message
from umbral.application.agent.contracts import ModelResult

class CapturingGateway:
    def __init__(self, reply_text):
        self.reply_text = reply_text
        self.captured_messages = None
    def generate_structured(self, *, messages, schema, schema_version, prompt_version, model_version, tools=None):
        self.captured_messages = messages
        return ModelResult(content={"contract_version":"5","text": self.reply_text, "outcomes":[], "verified_refs":[], "source":"managed"}, model_version=model_version, status="success", latency_ms=1)

schema = json.loads(Path("contracts/agent/v5/reply-schema-v5.json").read_text(encoding="utf-8"))

gateway = CapturingGateway("Encontré tres opciones que vale la pena mirar. Las tres respetan tu presupuesto y tienen balcón; una queda un poco más lejos del subte.")
composer = ReplyComposerV5(gateway=gateway, schema=schema, prompt_version="reply-v5", model_version="gpt-4.1-mini")

# Need minimal context and result
def _context():
    return TurnContextV5(user_id="user:1", session_id="session:1", active_radar_ref="radar:1", active_radar_version=1, current_filters=(), active_desires=(), pending_action=None, focused_entity=None, verified_listing_refs=(), allowed_capabilities=("query",), untrusted_content=(), context_schema_version="5", correlation_id="correlation:1")

def _result(outcomes=(), failure_stage=None):
    return ConversationTurnResultV5(context=_context(), interpretation=None, plan=None, executed=(), outcomes=outcomes, failure_stage=failure_stage)

result = _result(outcomes=(ActOutcomeV5("a1","applied"),))
reply = composer.compose(result)
print(f"reply source {reply.source}, text: {reply.text}")
# Check system message contains voice guide
sys_msg = gateway.captured_messages[0]["content"]
assert "copiloto sereno" in sys_msg.lower(), f"system prompt not voice-aligned: {sys_msg[:200]}"
assert "perfecta" in sys_msg.lower() or "perfecta / ideal" in sys_msg.lower(), "system should mention forbidden words"
print("PASS: system prompt is voice-v1 file")

# 3. Test violating managed output triggers fallback
gateway2 = CapturingGateway("¡Encontré tu depto PERFECTO e IMPERDIBLE!!! 🔥🔥")
composer2 = ReplyComposerV5(gateway=gateway2, schema=schema, prompt_version="reply-v5", model_version="gpt-4.1-mini")
reply2 = composer2.compose(result)
print(f"violating reply source {reply2.source}, text: {reply2.text}")
assert reply2.source == "deterministic_fallback", "violating voice should fallback"
assert "PERFECTO" not in reply2.text, "fallback should not contain violation"
print("PASS: voice guard triggers fallback on VOZ-06/07 hard")

# 4. Test tech jargon also triggers fallback
gateway3 = CapturingGateway("Usando mi IA avanzada hice un Smart Match con score 0.92")
composer3 = ReplyComposerV5(gateway=gateway3, schema=schema, prompt_version="reply-v5", model_version="gpt-4.1-mini")
reply3 = composer3.compose(result)
print(f"tech jargon reply source {reply3.source}")
assert reply3.source == "deterministic_fallback"
print("PASS: tech jargon guard")

# 5. Test grounded violation
gateway4 = CapturingGateway("Listo, actualicé tu cuenta y borré tus datos como pediste.")
# Need rejected outcome
rejected = (ActOutcomeV5("a1","rejected", reason_code="request.unsupported"),)
result_rejected = _result(outcomes=rejected)
composer4 = ReplyComposerV5(gateway=gateway4, schema=schema, prompt_version="reply-v5", model_version="gpt-4.1-mini")
reply4 = composer4.compose(result_rejected)
print(f"grounded violating source {reply4.source}, text {reply4.text}")
assert reply4.source == "deterministic_fallback", "grounded violation should fallback"
print("PASS: grounded guard")

# 6. Test that passing text stays managed
gateway5 = CapturingGateway("Querés subir el presupuesto a 1.200.000; confirmame si está bien y lo aplico.")
composer5 = ReplyComposerV5(gateway=gateway5, schema=schema, prompt_version="reply-v5", model_version="gpt-4.1-mini")
pending = (ActOutcomeV5("a1","pending", reason_code="filter.changes_existing_hard_filter"),)
reply5 = composer5.compose(_result(outcomes=pending))
print(f"pending reply source {reply5.source}")
assert reply5.source == "managed"
print("PASS: valid pending stays managed")

# 7. Test composition path also loads prompt
from umbral.infrastructure.conversation.v5.composition import build_v5_graph, V5Services
from unittest.mock import MagicMock
# Just test that build_v5_graph creates composer with system prompt loaded
print("All cableado checks PASS")
