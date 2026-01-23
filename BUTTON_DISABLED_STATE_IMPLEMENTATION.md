# Button Disabled State Implementation

## Overview
Updated image buttons (ICD, Historian, Vitals, Summary) to always be visible, but disabled when the corresponding image doesn't exist. This provides better UX by showing all available options while clearly indicating which images are available.

## Changes Made

### 1. Template Changes

**Both Templates Updated:**
- `app/templates/queue_validation_comparison.html`
- `app/templates/queue_validation_manual.html`

**Changes:**
1. **Removed Conditional Wrappers:** Removed all `{% if has_*_image %}` conditionals around buttons
2. **Added Disabled Attributes:** Added `{% if not has_*_image %}disabled{% endif %}` to each button
3. **Updated onclick Handlers:** Changed from direct `viewScreenshotFullscreen()` calls to `handleImageButtonClick()` function
4. **Enhanced CSS:** Added better disabled button styling

### 2. JavaScript Function

**Added `handleImageButtonClick()` function:**
```javascript
function handleImageButtonClick(hasImage, imageUrl) {
    // Check if image exists (handle both boolean and string 'true'/'false')
    if (hasImage === true || hasImage === 'true' || hasImage === 'True') {
        viewScreenshotFullscreen(imageUrl);
    } else {
        // Button is disabled, do nothing
        return false;
    }
}
```

### 3. CSS Enhancements

**Enhanced disabled button styling:**
```css
.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    background: #9ca3af !important;
}
.btn:disabled:hover {
    background: #9ca3af !important;
}
```

## Implementation Details

### Button Structure

**Before:**
```html
{% if has_icd_image %}
<button class="btn btn-secondary" 
        onclick="viewScreenshotFullscreen('/queue/validation/{{ encounter_id }}/image/icd')">
    View ICD Screenshot
</button>
{% endif %}
```

**After:**
```html
<button class="btn btn-secondary" 
        {% if not has_icd_image %}disabled{% endif %}
        onclick="handleImageButtonClick({{ has_icd_image|lower }}, '/queue/validation/{{ encounter_id }}/image/icd')">
    View ICD Screenshot
</button>
```

### How It Works

1. **All buttons are always rendered** - No conditional hiding
2. **Disabled state** - When `has_*_image` is `False`, the button gets the `disabled` attribute
3. **Visual feedback** - Disabled buttons have:
   - 50% opacity
   - Gray background (#9ca3af)
   - "not-allowed" cursor
   - No hover effect
4. **Functional behavior** - Disabled buttons don't trigger the image viewer

### Jinja2 Template Syntax

- Uses `{{ has_icd_image|lower }}` to convert boolean to lowercase string ("true"/"false")
- JavaScript function handles both boolean and string comparisons for robustness

## Benefits

✅ **Better UX:** Users can see all available image types at a glance
✅ **Clear Indication:** Disabled state clearly shows which images are missing
✅ **Consistent Layout:** Buttons always in the same position
✅ **Accessibility:** Proper disabled state for screen readers

## Testing

### Verification Checklist
- [x] All 4 buttons always visible
- [x] Buttons disabled when image doesn't exist
- [x] Buttons enabled when image exists
- [x] Disabled buttons have proper styling
- [x] Disabled buttons don't trigger image viewer
- [x] Enabled buttons work correctly
- [x] Both templates updated
- [x] JavaScript function handles all cases

### Manual Testing Steps

1. **Test with all images:**
   - Navigate to validation page where all images exist
   - Verify all 4 buttons are enabled and clickable

2. **Test with no images:**
   - Navigate to validation page where no images exist
   - Verify all 4 buttons are disabled and grayed out
   - Verify clicking disabled buttons does nothing

3. **Test with mixed images:**
   - Navigate to validation page where some images exist
   - Verify enabled buttons work
   - Verify disabled buttons are clearly indicated

## Files Changed

1. `app/templates/queue_validation_comparison.html`
   - Updated button section (lines ~1039-1064)
   - Added handleImageButtonClick function (lines ~1155-1165)
   - Enhanced disabled CSS (lines ~413-418)

2. `app/templates/queue_validation_manual.html`
   - Updated button section (lines ~849-875)
   - Added handleImageButtonClick function
   - Enhanced disabled CSS (lines ~413-418)

## Notes

- The `disabled` attribute prevents both clicking and keyboard interaction
- The JavaScript function provides an extra layer of protection
- Jinja2 `|lower` filter converts boolean to lowercase string for JavaScript
- CSS `!important` ensures disabled styling takes precedence
