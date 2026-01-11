#!/usr/bin/env python3
"""
Script to create and upload test ICD and Historian images for local testing.

This script creates simple test PNG images and uploads them to Azure Blob Storage
for testing the ICD and Historian screenshot viewing feature.

Usage:
    python scripts/create_test_encounter_images.py <encounter_id>

Example:
    python scripts/create_test_encounter_images.py 8b9f6493-57cf-41cb-b1e9-b4cd255645bc
"""

import os
import sys
from io import BytesIO
from typing import Optional

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    AZURE_BLOB_AVAILABLE = True
except ImportError:
    print("Error: azure-storage-blob package not installed. Please install it with: pip install azure-storage-blob")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL/Pillow not available. Will create minimal PNG files instead.")


def init_azure_blob():
    """Initialize Azure Blob Storage client."""
    connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    container_name = os.getenv('AZURE_STORAGE_CONTAINER_NAME', 'images')
    
    if not connection_string:
        print("Error: AZURE_STORAGE_CONNECTION_STRING environment variable not set")
        return None
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(container_name)
        return container_client
    except Exception as e:
        print(f"Error: Failed to initialize Azure Blob Storage: {e}")
        return None


def create_test_image_pil(width: int = 800, height: int = 600, text: str = "Test Image") -> bytes:
    """Create a test image using PIL/Pillow."""
    # Create image with light background
    img = Image.new('RGB', (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    
    # Draw a border
    draw.rectangle([10, 10, width - 10, height - 10], outline=(100, 100, 100), width=3)
    
    # Try to use a default font, fallback to basic if not available
    try:
        # Try to use a system font
        font_size = 40
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            except:
                font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # Calculate text position (centered)
    try:
        # Try newer PIL method first (Pillow 9.0.0+)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
        # Fallback for older PIL versions
        text_width, text_height = draw.textsize(text, font=font)
    
    text_x = (width - text_width) // 2
    text_y = (height - text_height) // 2
    
    # Draw text
    draw.text((text_x, text_y), text, fill=(50, 50, 50), font=font)
    
    # Draw a simple shape
    center_x, center_y = width // 2, height // 2
    draw.ellipse([center_x - 50, center_y + 80, center_x + 50, center_y + 180], 
                 fill=(70, 130, 180), outline=(50, 100, 150), width=2)
    
    # Save to bytes
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def create_minimal_png(text: str = "Test Image") -> bytes:
    """Create a minimal valid PNG file (fallback when PIL is not available)."""
    # This is a minimal 1x1 red PNG file
    # In practice, you'd want to use PIL, but this works as a fallback
    minimal_png = (
        b'\x89PNG\r\n\x1a\n'
        b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
        b'\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00'
        b'\x00\x00\nIDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    
    # If PIL is available, use it instead
    if PIL_AVAILABLE:
        return create_test_image_pil(text=text)
    
    return minimal_png


def upload_test_images(encounter_id: str, container_client) -> bool:
    """Upload test ICD and Historian images for the given encounter_id."""
    if not container_client:
        print("Error: Container client not initialized")
        return False
    
    # Create test images
    print(f"Creating test images for encounter_id: {encounter_id}")
    
    icd_image_data = create_minimal_png(f"ICD Screenshot - {encounter_id}")
    historian_image_data = create_minimal_png(f"Historian Screenshot - {encounter_id}")
    
    # Define blob names (following the naming format: {encounter_id}_{image_type}.png)
    icd_blob_name = f"encounters/{encounter_id}/{encounter_id}_icd.png"
    historian_blob_name = f"encounters/{encounter_id}/{encounter_id}_historian.png"
    
    success = True
    
    # Upload ICD image
    try:
        print(f"Uploading ICD image to: {icd_blob_name}")
        blob_client = container_client.get_blob_client(icd_blob_name)
        content_settings = ContentSettings(content_type='image/png')
        blob_client.upload_blob(icd_image_data, content_settings=content_settings, overwrite=True)
        print(f"✓ Successfully uploaded ICD image")
    except Exception as e:
        print(f"✗ Error uploading ICD image: {e}")
        success = False
    
    # Upload Historian image
    try:
        print(f"Uploading Historian image to: {historian_blob_name}")
        blob_client = container_client.get_blob_client(historian_blob_name)
        content_settings = ContentSettings(content_type='image/png')
        blob_client.upload_blob(historian_image_data, content_settings=content_settings, overwrite=True)
        print(f"✓ Successfully uploaded Historian image")
    except Exception as e:
        print(f"✗ Error uploading Historian image: {e}")
        success = False
    
    return success


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_test_encounter_images.py <encounter_id>")
        print("\nExample:")
        print("  python scripts/create_test_encounter_images.py 8b9f6493-57cf-41cb-b1e9-b4cd255645bc")
        sys.exit(1)
    
    encounter_id = sys.argv[1].strip()
    
    if not encounter_id:
        print("Error: encounter_id cannot be empty")
        sys.exit(1)
    
    # Initialize Azure Blob Storage
    print("Initializing Azure Blob Storage...")
    container_client = init_azure_blob()
    
    if not container_client:
        print("\nError: Could not initialize Azure Blob Storage client.")
        print("Please make sure AZURE_STORAGE_CONNECTION_STRING is set in your environment.")
        sys.exit(1)
    
    print("✓ Azure Blob Storage initialized\n")
    
    # Upload test images
    success = upload_test_images(encounter_id, container_client)
    
    if success:
        print("\n✓ All test images uploaded successfully!")
        print(f"\nYou can now test the feature by visiting:")
        print(f"  /queue/validation/{encounter_id}")
        print(f"\nThe ICD and Historian screenshot buttons should now work.")
    else:
        print("\n✗ Some errors occurred during upload. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

