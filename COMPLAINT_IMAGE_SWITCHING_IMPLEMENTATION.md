# Complaint Image Switching Implementation

## Overview
Fixed the issue where HPI images from all complaints were visible when switching between complaint tabs on the validation page. Now only the active complaint's image is displayed.

## Changes Made

### 1. JavaScript Updates
Updated the `switchComplaint()` function in both templates to explicitly handle image visibility:

**Files Modified:**
- `app/templates/queue_validation_comparison.html`
- `app/templates/queue_validation_manual.html`

**Implementation:**
- Hides all images when switching complaints
- Shows only the image for the active complaint
- Handles both image elements and "no-image" placeholder divs

### 2. CSS Backup Rules
Added CSS rules to ensure images are hidden when their parent complaint-content is not active:

```css
.complaint-content:not(.active) .screenshot-container img {
    display: none !important;
}
.complaint-content:not(.active) .screenshot-container .no-image {
    display: none !important;
}
```

## How It Works

1. **When a complaint tab is clicked:**
   - All complaint-content divs are hidden (CSS: `display: none`)
   - All images are explicitly hidden via JavaScript (`display: 'none'`)
   - The selected complaint-content is shown (CSS: `display: block`)
   - Only the image within the active complaint-content is shown (`display: 'block'`)

2. **Dual Protection:**
   - JavaScript handles the switching explicitly
   - CSS provides backup protection in case JavaScript fails

## Testing

### Automated Test
Run the test script:
```bash
python3 test_complaint_image_switching.py
```

### Manual Testing Steps
1. Start the server:
   ```bash
   uvicorn app.api.routes:app --host 0.0.0.0 --port 8000 --reload
   ```

2. Navigate to a validation page with multiple complaints:
   - Go to `/queue/validation/{encounter_id}` where the encounter has multiple complaints

3. Test complaint switching:
   - Click on different complaint tabs
   - Verify only the active complaint's image is visible
   - Verify images from other complaints are hidden

4. Test edge cases:
   - Complaints with images
   - Complaints without images (should show "Screenshot not available")
   - Rapid tab switching

## Expected Behavior

✅ **Before Fix:**
- All complaint images visible simultaneously
- Images overlapping or showing incorrectly

✅ **After Fix:**
- Only active complaint's image is visible
- Smooth switching between complaints
- No image overlap or visibility issues

## Files Changed

1. `app/templates/queue_validation_comparison.html`
   - Updated `switchComplaint()` function (lines ~1305-1338)
   - Added CSS rules (lines ~172-177)

2. `app/templates/queue_validation_manual.html`
   - Updated `switchComplaint()` function (lines ~903-946)
   - Added CSS rules (lines ~172-177)

## Verification Checklist

- [x] JavaScript function hides all images on switch
- [x] JavaScript function shows active complaint image
- [x] Handles "no-image" placeholder divs
- [x] CSS backup rules added
- [x] Both templates updated
- [x] Test script created and passing

## Notes

- Images are mapped by complaint ID: `{complaint_id}_hpi.png`
- Each complaint has its own image element with ID: `screenshot_{complaint_id}`
- The implementation uses both JavaScript and CSS for maximum reliability
