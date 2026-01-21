#!/usr/bin/env python3
"""
Test script to verify complaint image switching functionality on validation page.
This script checks:
1. That images are properly scoped to their complaint-content divs
2. That the switchComplaint function correctly shows/hides images
3. That CSS rules are properly applied
"""

import re
import sys
from pathlib import Path

def check_template_file(file_path: str, template_name: str) -> dict:
    """Check a template file for proper image switching implementation."""
    results = {
        'file': template_name,
        'has_switch_function': False,
        'has_image_hiding': False,
        'has_image_showing': False,
        'has_css_rules': False,
        'images_in_complaint_content': True,
        'errors': []
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if switchComplaint function exists
        if 'function switchComplaint' in content:
            results['has_switch_function'] = True
            
            # Check if function hides all images
            if 'querySelectorAll(\'.screenshot-container img\')' in content:
                if 'style.display = \'none\'' in content or 'display = "none"' in content:
                    results['has_image_hiding'] = True
            
            # Check if function shows active image
            if 'selectedContent.querySelector(\'.screenshot-container img\')' in content:
                if 'style.display = \'block\'' in content or 'display = "block"' in content:
                    results['has_image_showing'] = True
        
        # Check for CSS rules
        if '.complaint-content:not(.active) .screenshot-container img' in content:
            results['has_css_rules'] = True
        
        # Check that images are inside complaint-content divs
        # Find all complaint-content divs
        complaint_content_pattern = r'<div class="complaint-content[^"]*"'
        complaint_contents = re.findall(complaint_content_pattern, content)
        
        # Find all screenshot sections
        screenshot_pattern = r'<div class="screenshot-section"[^>]*>.*?</div>\s*</div>'
        screenshot_sections = re.findall(screenshot_pattern, content, re.DOTALL)
        
        # Check that each complaint-content has a screenshot-section
        if len(complaint_contents) > 0:
            # Count how many complaint-content blocks have screenshot-section inside them
            # This is a simplified check - in reality we'd need to parse HTML properly
            complaint_blocks = content.split('<div class="complaint-content')
            for i, block in enumerate(complaint_blocks[1:], 1):  # Skip first empty split
                if 'screenshot-section' not in block[:2000]:  # Check first 2000 chars of block
                    results['errors'].append(f"Complaint block {i} may not have screenshot-section")
        
        return results
        
    except Exception as e:
        results['errors'].append(f"Error reading file: {str(e)}")
        return results

def main():
    """Main test function."""
    print("=" * 80)
    print("Testing Complaint Image Switching Implementation")
    print("=" * 80)
    print()
    
    base_path = Path(__file__).parent
    templates_path = base_path / 'app' / 'templates'
    
    templates_to_check = [
        ('queue_validation_comparison.html', 'Comparison Template'),
        ('queue_validation_manual.html', 'Manual Template')
    ]
    
    all_passed = True
    
    for template_file, template_name in templates_to_check:
        file_path = templates_path / template_file
        
        if not file_path.exists():
            print(f"❌ ERROR: Template file not found: {file_path}")
            all_passed = False
            continue
        
        print(f"Testing: {template_name} ({template_file})")
        print("-" * 80)
        
        results = check_template_file(str(file_path), template_name)
        
        # Check results
        checks = [
            ('Has switchComplaint function', results['has_switch_function']),
            ('Hides all images on switch', results['has_image_hiding']),
            ('Shows active complaint image', results['has_image_showing']),
            ('Has CSS backup rules', results['has_css_rules']),
        ]
        
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            print(f"  {status} {check_name}")
            if not check_result:
                all_passed = False
        
        if results['errors']:
            print(f"  ⚠️  Warnings:")
            for error in results['errors']:
                print(f"     - {error}")
        
        print()
    
    print("=" * 80)
    if all_passed:
        print("✅ ALL CHECKS PASSED")
        print()
        print("Next steps:")
        print("1. Start the server: uvicorn app.api.routes:app --host 0.0.0.0 --port 8000 --reload")
        print("2. Navigate to a validation page with multiple complaints")
        print("3. Test switching between complaint tabs")
        print("4. Verify only the active complaint's image is visible")
        return 0
    else:
        print("❌ SOME CHECKS FAILED")
        print("Please review the implementation and fix any issues.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
