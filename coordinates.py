# Centralized coordinate mappings and lookup function

DISTRICT_COORDS = {
    'Central and Western': (22.286, 114.155),
    'Wan Chai': (22.278, 114.173),
    'Eastern': (22.286, 114.225),
    'Southern': (22.247, 114.159),
    'Yau Tsim Mong': (22.320, 114.170),
    'Sham Shui Po': (22.331, 114.162),
    'Kowloon City': (22.330, 114.189),
    'Wong Tai Sin': (22.343, 114.197),
    'Kwun Tong': (22.313, 114.226),
    'Tsuen Wan': (22.373, 114.113),
    'Tuen Mun': (22.393, 113.972),
    'Yuen Long': (22.446, 114.035),
    'North': (22.495, 114.138),
    'Tai Po': (22.451, 114.169),
    'Sha Tin': (22.383, 114.194),
    'Sai Kung': (22.383, 114.271),
    'Islands': (22.278, 113.945),
    'Kwai Tsing': (22.355, 114.128),
}

BUILDING_COORDS = {
    'Mid-Levels Garden': (22.283, 114.150),
    'The Avenue': (22.279, 114.170),
    'Kornhill Garden': (22.286, 114.230),
    'South Horizons': (22.240, 114.150),
    'The Masterpiece': (22.320, 114.180),
    'Beacon Heights': (22.331, 114.160),
    'Kadoorie Hill': (22.330, 114.190),
    'Fung Tak Estate': (22.343, 114.197),
    'Laguna City': (22.313, 114.226),
    'Discovery Park': (22.373, 114.113),
    'Melody Garden': (22.393, 113.972),
    'YOHO Town': (22.446, 114.035),
    'Avon Park': (22.495, 114.138),
    'Tai Po Centre': (22.451, 114.169),
    'City One Shatin': (22.383, 114.194),
    'Marina Cove': (22.383, 114.271),
    'Caribbean Coast': (22.278, 113.945),
    'Kwai Fong Estate': (22.355, 114.128),
}

def get_coordinates(district, estate_building=None):
    """
    Return (latitude, longitude).
    Prefer building-level precision; fallback to district center.
    """
    if estate_building and estate_building in BUILDING_COORDS:
        return BUILDING_COORDS[estate_building]
    return DISTRICT_COORDS.get(district, (None, None))