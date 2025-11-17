#!/usr/bin/env python3
"""
Location mapping for Exer Urgent Care locations.
Maps location names to their corresponding location IDs.
"""

# Mapping of location names to location IDs
LOCATION_MAP = {
    "Exer Urgent Care - Anaheim - Euclid St": "AWRBj6",
    "Exer Urgent Care - Anaheim - State College Blvd": "ABr1Nd",
    "Exer Urgent Care - Beaumont": "g5rawn",
    "Exer Urgent Care - Beverly Hills": "gKe2Nj",
    "Exer Urgent Care - Calabasas - Agoura Rd": "v0mYy0",
    "Exer Urgent Care - Calabasas - Mulholland Dr": "gdeYvE",
    "Exer Urgent Care - Camarillo": "0V37aA",
    "Exer Urgent Care - Canyon Country": "ABOklp",
    "Exer Urgent Care - Costa Mesa": "A4NEvv",
    "Exer Urgent Care - Covina": "gw8Ky1",
    "Exer Urgent Care - Culver City - 8985 Venice Blvd": "p3Xkkg",
    "Exer Urgent Care - Culver City - 9726 Venice Blvd": "A6JY29",
    "Exer Urgent Care - Demo": "AXjwbE",
    "Exer Urgent Care - Downtown": "gbx2w3",
    "Exer Urgent Care - Eagle Rock": "AGGzMe",
    "Exer Urgent Care - Glendale": "goBwnJ",
    "Exer Urgent Care - Glendora": "0r7Kd2",
    "Exer Urgent Care - Highland": "gLXaG2",
    "Exer Urgent Care - Hollywood - Melrose Ave": "0md8a5",
    "Exer Urgent Care - Hollywood - Willoughby Ave": "gqo6xN",
    "Exer Urgent Care - Huntington Park": "gZ86G6",
    "Exer Urgent Care - Irvine": "0edRx4",
    "Exer Urgent Care - La Canada Flintridge": "gwdX30",
    "Exer Urgent Care - Lakewood": "gZ89yL",
    "Exer Urgent Care - Lawndale": "AzxK8o",
    "Exer Urgent Care - Long Beach - Long Beach Blvd": "A9OjD6",
    "Exer Urgent Care - Long Beach - PCH": "gbx2LQ",
    "Exer Urgent Care - Long Beach - Willow St": "A2BbY8",
    "Exer Urgent Care - Manhattan Beach": "AGeveg",
    "Exer Urgent Care - Marina Del Rey": "gd8Pav",
    "Exer Urgent Care - Moorpark": "gNLDRo",
    "Exer Urgent Care - Newbury Park": "PgoEoA",
    "Exer Urgent Care - North Hollywood": "py6Ko8",
    "Exer Urgent Care - Northridge": "gonMGp",
    "Exer Urgent Care - Pasadena - Allen Ave": "A4N23m",
    "Exer Urgent Care - Pasadena - East Del Mar Blvd": "xAzoMp",
    "Exer Urgent Care - Pasadena - Lake Ave": "p8dEeq",
    "Exer Urgent Care - Pasadena - South Fair Oaks Ave": "0EBZmJ",
    "Exer Urgent Care - Physical Therapy": "0x1KEk",
    "Exer Urgent Care - Playa Vista": "0edXQB",
    "Exer Urgent Care - Porter Ranch": "0x1Kdb",
    "Exer Urgent Care - Rancho Palos Verdes": "pDJxXl",
    "Exer Urgent Care - Redlands": "07wDB3",
    "Exer Urgent Care - Redondo Beach": "0m8YDg",
    "Exer Urgent Care - Rolling Hills Estates": "0mOPvp",
    "Exer Urgent Care - Santa Monica - Colorado Blvd": "gQKXVv",
    "Exer Urgent Care - Santa Monica - Wilshire Blvd": "0O3mL1",
    "Exer Urgent Care - Sherman Oaks - Riverside": "ABG1Np",
    "Exer Urgent Care - Sherman Oaks - Ventura Blvd": "gbx2W1",
    "Exer Urgent Care - Silver Lake": "pyX2a6",
    "Exer Urgent Care - Stevenson Ranch": "gKEwQA",
    "Exer Urgent Care - Tarzana": "gJMwx7",
    "Exer Urgent Care - Thousand Oaks": "g1B9aR",
    "Exer Urgent Care - Torrance - PCH": "AGL7qR",
    "Exer Urgent Care - Torrance - Sepulveda Blvd": "pjOLzD",
    "Exer Urgent Care - Venice - Lincoln Blvd": "AvXK8d",
    "Exer Urgent Care - Virtual Care": "gZ867B",
    "Exer Urgent Care - West Hills": "0OMDWp",
    "Exer Urgent Care - West Hollywood - La Brea Ave": "AvXZa3",
    "Exer Urgent Care - West Hollywood - Sunset Blvd": "p8P9bp",
    "Exer Urgent Care - West Los Angeles": "gJBEQl",
    "Exer Urgent Care - Westlake Village": "plvWN0",
    "Exer Urgent Care - Westwood": "07okv0",
    "Exer Urgent Care - Whittier": "0VGVeM",
}

# Reverse mapping: location ID to location name
LOCATION_ID_TO_NAME = {v: k for k, v in LOCATION_MAP.items()}


def get_location_id(location_name):
    """
    Get location ID by location name.
    
    Args:
        location_name: Full location name (e.g., "Exer Urgent Care - Demo")
    
    Returns:
        Location ID string, or None if not found
    """
    return LOCATION_MAP.get(location_name)


def get_location_name(location_id):
    """
    Get location name by location ID.
    
    Args:
        location_id: Location ID string (e.g., "AXjwbE")
    
    Returns:
        Location name string, or None if not found
    """
    return LOCATION_ID_TO_NAME.get(location_id)


def get_queue_url(location_id=None, location_name=None):
    """
    Get queue URL for a location.
    
    Args:
        location_id: Location ID string (required if location_name not provided)
        location_name: Location name string (required if location_id not provided)
    
    Returns:
        Queue URL string, or None if neither location_id nor location_name is provided
    
    Examples:
        >>> get_queue_url(location_id="AXjwbE")
        'https://manage.solvhealth.com/queue?location_ids=AXjwbE'
        
        >>> get_queue_url(location_name="Exer Urgent Care - Demo")
        'https://manage.solvhealth.com/queue?location_ids=AXjwbE'
    """
    if location_id:
        return f"https://manage.solvhealth.com/queue?location_ids={location_id}"
    elif location_name:
        loc_id = get_location_id(location_name)
        if loc_id:
            return f"https://manage.solvhealth.com/queue?location_ids={loc_id}"
    
    # No default - return None if no location provided
    return None


def list_all_locations():
    """
    Get a list of all location names.
    
    Returns:
        List of location name strings
    """
    return sorted(LOCATION_MAP.keys())


def list_all_location_ids():
    """
    Get a list of all location IDs.
    
    Returns:
        List of location ID strings
    """
    return sorted(LOCATION_MAP.values())


if __name__ == "__main__":
    # Example usage
    print("Location Mapping Examples:")
    print("=" * 60)
    
    # Get location ID by name
    demo_id = get_location_id("Exer Urgent Care - Demo")
    print(f"Demo Location ID: {demo_id}")
    
    # Get location name by ID
    demo_name = get_location_name("AXjwbE")
    print(f"Location name for 'AXjwbE': {demo_name}")
    
    # Get queue URL
    url = get_queue_url(location_name="Exer Urgent Care - Demo")
    print(f"Queue URL: {url}")
    
    # List all locations
    print(f"\nTotal locations: {len(LOCATION_MAP)}")
    print("\nAll locations:")
    for name in list_all_locations()[:10]:  # Show first 10
        print(f"  - {name}")
    print("  ...")

