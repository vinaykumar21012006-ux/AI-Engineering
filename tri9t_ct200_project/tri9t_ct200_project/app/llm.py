import json, os
import httpx
from .schemas import GenerationPayload

def _fallback(text: str) -> dict:
    excerpt = text[:600].strip() or "Selected CT-200 section"
    return {"test_cases": [
      {"title":"Verify stated requirement","objective":"Confirm the selected requirement is implemented as documented.",
       "preconditions":["Device is available for controlled testing."],"steps":["Set up the device according to the manual.","Exercise the behavior described in the selected section.","Record the device response."],
       "expected_result":f"The observed behavior matches the selected requirement: {excerpt[:180]}","source_node_ids":[],"risk":"medium"},
      {"title":"Verify boundary conditions","objective":"Check behavior at the documented operating boundary.",
       "preconditions":["Test setup is calibrated and safe."],"steps":["Identify the limits stated in the selected section.","Test values at and immediately around each stated limit where safe.","Record warnings, outputs, and recovery behavior."],
       "expected_result":"Boundary behavior and any stated warnings match the manual; no unsupported threshold is assumed.","source_node_ids":[],"risk":"high"},
      {"title":"Verify error and recovery behavior","objective":"Check that abnormal conditions are handled predictably.",
       "preconditions":["Use a safe simulation or approved test fixture."],"steps":["Simulate a relevant abnormal condition described by the selected text.","Observe user-visible indication and device response.","Restore normal conditions and confirm recovery."],
       "expected_result":"The device indicates and recovers as specified in the selected section.","source_node_ids":[],"risk":"medium"}
    ]}

async def generate_cases(text: str) -> tuple[dict, str]:
    key = os.getenv("LLM_API_KEY")
    base = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    if not key:
        return _fallback(text), "fallback"
    prompt = ("Create 3 to 5 concrete QA test case ideas strictly grounded in the supplied medical-device manual text. "
      "Do not invent numeric limits. Return ONLY JSON matching {test_cases:[{title,objective,preconditions,steps,expected_result,source_node_ids,risk}]}. "
      "Each expected_result must be observable. risk is low, medium, or high.\n\nSOURCE TEXT:\n" + text)
    last_error = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                r = await client.post(base + "/chat/completions",
                    headers={"Authorization":"Bearer " + key, "Content-Type":"application/json"},
                    json={"model":model,"temperature":0.2,"messages":[{"role":"user","content":prompt}]})
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                validated = GenerationPayload.model_validate(data)
                return validated.model_dump(), model
        except Exception as exc:
            last_error = str(exc)
            prompt += "\nYour previous response was invalid. Return valid JSON only with 3-5 test_cases and all required fields."
    # Predictable fallback rather than storing malformed output.
    data = _fallback(text)
    GenerationPayload.model_validate(data)
    return data, "fallback_after_error:" + (last_error or "unknown")
