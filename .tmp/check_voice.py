import json
from pathlib import Path
import importlib.util, sys

p = Path('contracts/agent/v5/voice-examples-v1.json')
data = json.loads(p.read_text(encoding='utf-8'))
print(f"loaded {len(data['examples'])} examples, version {data['version']}")
for ex in data["examples"]:
    t = ex["text"]
    assert 1 <= len(t) <= 2000, f"len fail {ex['id']}"
    assert ex["verdict"] in ("PASS","FAIL","BORDERLINE")
print("length check ok")

spec = importlib.util.spec_from_file_location("voice_check", "src/umbral/application/conversation/v5/voice_check.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["voice_check"] = mod
spec.loader.exec_module(mod)

for ex in data["examples"]:
    v = mod.lint_voice(ex["text"])
    verdict = ex["verdict"]
    is_pass = mod.is_pass(ex["text"])
    print(f"{ex['id']:8} {verdict:11} lint={v} is_pass={is_pass} rubric={mod.score_rubric(ex['text'])}")

prompt = Path("src/umbral/agent/prompts/reply-v5.md").read_text(encoding="utf-8")
assert "voice: voice-v1" in prompt
assert "voice_guide" in prompt
assert "copiloto sereno" in prompt.lower()
print("prompt header ok")

assert Path("docs/brand/voice-guide.md").exists()
print("voice-guide exists")
print("ALL CHECKS PASS")
