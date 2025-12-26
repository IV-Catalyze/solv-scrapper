# Prompt Update: emrId Handling

## What Needs to be Updated

Based on the emrId fix implementation, the following sections in `iv_to_experity_llm_prompt.txt` should be updated:

## 1. Line 75: emrId Extraction Instructions

**Current Text:**
```
- emrId = emrId field from the encounter object (CRITICAL: Use the emrId field if present, NOT clientId. emrId and clientId are different fields. If emrId is null or missing, use null - do NOT substitute clientId)
```

**Updated Text:**
```
- emrId = Use the emrId field that is already provided in the encounter data (it has been pre-extracted and set for you)
- CRITICAL: The emrId field in the encounter data is already correctly set - use it exactly as provided
- If emrId is null or missing in the encounter data, set it to null in your output
- NEVER use clientId as a substitute for emrId - these are different identifiers
- The emrId value you receive has been pre-extracted from the correct source (queue_entry.emr_id or encounter.emrId/emr_id) with proper priority handling
```

## 2. Lines 361-365: Rules for emrId Section

**Current Text:**
```
**Rules for emrId:**
- If `emrId` field exists in the encounter data, use it exactly as provided
- If `emrId` is null or missing, set it to null in the output
- **NEVER use `clientId` as a substitute for `emrId`**
- **NEVER copy `clientId` into the `emrId` field**
- These are separate identifiers for different purposes
```

**Updated Text:**
```
**Rules for emrId:**
- The `emrId` field in the encounter data has been pre-extracted and set for you
- Use the `emrId` value exactly as provided in the encounter data (it's already correctly extracted from the right source)
- If `emrId` is null or missing in the encounter data, set it to null in your output
- **NEVER use `clientId` as a substitute for `emrId`** - even if emrId is missing
- **NEVER copy `clientId` into the `emrId` field**
- These are separate identifiers for different purposes
- Note: The emrId extraction follows this priority: queue_entry.emr_id > encounter.emrId > encounter.emr_id > null
```

## 3. Line 353: Edge Cases Section

**Current Text:**
```
Missing part=Generalized | No side=Left | Missing vitals=null | No guardian=present:false | No labs=[] | No ICD updates=[] (automatically handled) | Missing emrId=null (DO NOT use clientId as fallback) | Missing queueId=null
```

**Updated Text:**
```
Missing part=Generalized | No side=Left | Missing vitals=null | No guardian=present:false | No labs=[] | No ICD updates=[] (automatically handled) | Missing emrId=null (DO NOT use clientId as fallback - the emrId field in encounter data is already set correctly, use it as-is) | Missing queueId=null
```

## Summary of Changes

The key updates reflect that:
1. **emrId is pre-extracted** - The LLM doesn't need to extract it, it's already provided in the encounter data
2. **Use the provided value** - The emrId in the encounter data is already correctly set with proper priority handling
3. **Still enforce null handling** - If emrId is missing/null, set it to null (and post-processing will enforce it)
4. **Never use clientId** - This rule remains the same, but emphasize that the pre-extracted emrId is already correct

## Why These Updates?

The code now:
- Pre-extracts emrId before sending to LLM (with proper priority: queue_entry.emr_id > encounter.emrId > encounter.emr_id > null)
- Always overwrites LLM's emrId with the pre-extracted value in post-processing
- Ensures emrId is never set to clientId

So the prompt should reflect that:
- The LLM receives encounter data with emrId already correctly set
- The LLM should use that value as-is
- The LLM should never try to extract or derive emrId from other sources
- If emrId is null, keep it null (don't use clientId)

