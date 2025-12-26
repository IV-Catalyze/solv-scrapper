# emrId Fix Update - Enhanced Extraction and Post-Processing

## Changes Made

Updated the emrId extraction and post-processing logic in `app/utils/azure_ai_agent_client.py` to follow the plan in `MAPPING_TO_CODE_PLAN.md` section 1.5.

## What Was Updated

### 1. Enhanced Pre-Extraction Logic (Lines 1041-1088)

**Before:**
- Only checked `queue_entry.emr_id` (Format 1)
- Didn't handle Format 2 (direct encounter object)

**After:**
- ✅ Checks multiple sources with priority:
  1. `queue_entry.emr_id` (Format 1 - highest priority)
  2. `encounter.emrId` (Format 2)
  3. `encounter.emr_id` (Format 2 - snake_case variant)
  4. `None` if not found (does NOT use `clientId` as fallback)

**Key Improvements:**
- Handles both Format 1 (queue entry wrapper) and Format 2 (direct encounter)
- Properly handles both `emrId` (camelCase) and `emr_id` (snake_case) in encounter data
- Sets `emrId` to `None` if missing (never uses `clientId` as fallback)
- Better logging to show which source was used

### 2. Simplified Post-Processing (Lines 1090-1118)

**Before:**
- Conditional logic: only fixed emrId if it was wrong
- Complex checks for clientId matching
- Could miss cases if structure wasn't found

**After:**
- ✅ **Always overwrites** LLM's emrId with pre-extracted value
- Simpler logic: no conditionals, just always set the pre-extracted value
- Better logging to show when corrections are made
- Handles all response structures (direct, wrapped, nested)

**Key Improvements:**
- Guarantees emrId is always correct (no conditional logic)
- Prevents LLM from using clientId (always overwrites)
- Works even if original_emr_id is None (sets to None explicitly)
- Clearer logging for debugging

## Code Changes Summary

### Extraction Logic
```python
# Priority order:
1. queue_entry.emr_id (Format 1)
2. encounter.emrId (Format 2 - camelCase)
3. encounter.emr_id (Format 2 - snake_case)
4. None (if not found - never use clientId)
```

### Post-Processing Logic
```python
# Always overwrite (no conditionals):
actions["emrId"] = original_emr_id  # Always set, even if None
```

## Benefits

1. ✅ **Handles both input formats** (queue entry wrapper and direct encounter)
2. ✅ **Always correct** (no conditional logic, always overwrites)
3. ✅ **Prevents clientId confusion** (never uses clientId as fallback)
4. ✅ **Better logging** (shows which source was used and when corrections are made)
5. ✅ **Simpler code** (removed complex conditional logic)

## Testing

The fix should be tested with:
- ✅ Format 1: Queue entry with `queue_entry.emr_id`
- ✅ Format 2: Direct encounter with `encounter.emrId`
- ✅ Format 2: Direct encounter with `encounter.emr_id` (snake_case)
- ✅ Missing emrId: Should set to `None` (not use clientId)
- ✅ LLM returns wrong emrId: Should be corrected to pre-extracted value
- ✅ LLM returns clientId as emrId: Should be corrected to pre-extracted value

## Related Files

- `app/utils/azure_ai_agent_client.py` - Main implementation
- `MAPPING_TO_CODE_PLAN.md` - Section 1.5 (emrId Extraction plan)
- `iv_to_experity_llm_prompt.txt` - Lines 355-365 (emrId vs clientId rules)

