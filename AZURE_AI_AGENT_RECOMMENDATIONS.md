# Azure AI Agent Configuration Recommendations

## Current Issues

### Issue 1: "Parsed response is not a JSON object"
**Problem:** The LLM sometimes returns an array or other format instead of the expected JSON object.

**Root Cause:** The prompt expects a JSON object, but the LLM might be:
- Returning an array (old format)
- Adding explanatory text before/after JSON
- Returning a different structure

**Solution Applied:**
- ✅ Improved validation with better error messages
- ✅ Detects if response is an array vs object
- ✅ Shows preview of what was actually returned

### Issue 2: "Azure AI agent response is incomplete - file_search_call detected"
**Problem:** The agent is trying to search for configuration files but can't find them.

**Root Cause:** The prompt has placeholders:
```
PROBLEM_SETS: {{PROBLEM_SETS_JSON}}
BODY_AREAS: {{BODY_AREAS_JSON}}
NOTES_TEMPLATES: {{NOTES_TEMPLATES_JSON}}
COORDS: {{COORDS_JSON}}
```

The Azure AI agent is configured to use file_search to find these files, but:
1. The files aren't in the vector store, OR
2. The agent configuration needs the files to be injected into the prompt

## Recommendations

### Option 1: Inject Configuration Files into Prompt (Recommended)

**Action:** Update the Azure AI agent configuration to inject the actual JSON files into the prompt before sending to the LLM.

**Steps:**
1. Load the configuration files:
   - `app/mappers/experity_problem_sets.json`
   - `app/mappers/experity_body_areas.json`
   - `app/mappers/experity_notes_templates.json`
   - `app/mappers/coords_only.json`

2. Replace placeholders in the prompt:
   - Replace `{{PROBLEM_SETS_JSON}}` with the actual JSON content
   - Replace `{{BODY_AREAS_JSON}}` with the actual JSON content
   - Replace `{{NOTES_TEMPLATES_JSON}}` with the actual JSON content
   - Replace `{{COORDS_JSON}}` with the actual JSON content

3. This should be done in the Azure AI agent configuration, not in our code.

**Benefits:**
- ✅ No file_search needed
- ✅ Faster responses (no file search delay)
- ✅ More reliable (no dependency on vector store)
- ✅ Configuration is always up-to-date

### Option 2: Add Files to Vector Store

**Action:** Upload the configuration files to the Azure AI agent's vector store.

**Steps:**
1. In Azure Portal → Your Azure AI Project → Vector Stores
2. Upload these files to vector store `vs_X6N6lUufnqJ9my2vN6OW0ddK`:
   - `experity_problem_sets.json`
   - `experity_body_areas.json`
   - `experity_notes_templates.json`
   - `coords_only.json`

3. Ensure the agent has file_search enabled and can access these files

**Benefits:**
- ✅ Files are available for file_search
- ✅ Agent can find them automatically

**Drawbacks:**
- ⚠️ Slower (file_search adds latency)
- ⚠️ Need to keep vector store updated when files change

### Option 3: Update Agent Prompt (Alternative)

**Action:** Modify the prompt to not require file_search, or make it optional.

**Steps:**
1. Update `iv_to_experity_llm_prompt.txt` to either:
   - Remove the configuration placeholders if not needed
   - Make file_search optional with fallback logic
   - Include minimal configuration directly in prompt

**Note:** This might reduce accuracy if the LLM doesn't have access to the full configuration.

## Immediate Actions

### For "Parsed response is not a JSON object" Error:

1. **Check the actual response** - The improved error messages will now show what type was returned
2. **Verify prompt format** - Ensure the prompt clearly states "return ONLY this JSON structure"
3. **Check LLM temperature** - Lower temperature (0.1-0.3) for more deterministic output

### For "file_search_call detected" Error:

1. **Short-term:** Wait longer (timeout is now 120 seconds)
2. **Long-term:** Implement Option 1 (inject files into prompt) - this is the best solution

## Code Improvements Made

✅ **Better validation:**
- Detects if response is array vs object
- Shows preview of actual response
- Clearer error messages

✅ **Improved timeout:**
- Increased from 60s to 120s for file search operations

✅ **Better error handling:**
- Detects incomplete responses
- Identifies file_search_call issues
- Provides actionable error messages

## Next Steps

1. **Contact Azure AI team** to:
   - Inject configuration files into the agent prompt (Option 1)
   - OR ensure files are in vector store (Option 2)

2. **Monitor errors** after deployment:
   - Check if "not a JSON object" errors show what type was returned
   - Check if file_search issues persist

3. **Consider prompt adjustments:**
   - Add explicit instruction: "Return ONLY a JSON object, not an array"
   - Add example of correct format at the end of prompt

## Testing

After implementing Option 1 (injecting files), test with:
```json
{
  "queue_entry": {
    "encounter_id": "test-123",
    "raw_payload": {
      "chiefComplaints": [{
        "id": "test-1",
        "description": "cut on hand",
        "type": "trauma",
        "part": "hand"
      }]
    }
  }
}
```

Expected: Should return a JSON object (not array) with the full structure.

