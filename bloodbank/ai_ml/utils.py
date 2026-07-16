"""
AI/ML Utility Functions for Blood Management System

Provides helper functions for:
- Data validation
- Scoring calculations
- Format conversions
- Medical blood compatibility mapping
- Logging
"""

from datetime import datetime
import math


# Universal Medical Compatibility Matrix
# Maps Patient Blood Group -> List of Safe Donor Blood Groups
COMPATIBILITY_MATRIX = {
    'A+': ['A+', 'A-', 'O+', 'O-'],
    'A-': ['A-', 'O-'],
    'B+': ['B+', 'B-', 'O+', 'O-'],
    'B-': ['B-', 'O-'],
    'AB+': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
    'AB-': ['AB-', 'A-', 'B-', 'O-'],
    'O+': ['O+', 'O-'],
    'O-': ['O-']
}

def calculate_urgency_score(request_data: dict) -> float:
    """
    Calculate AI urgency score based on multiple factors.
    
    Factors:
    - Request age (older = escalating urgency)
    - Blood group rarity
    - Quantity requested
    - Explicit urgency level
    
    Returns:
        float: Score between 0 and 100
    """
    score = 0.0
    
    # 1. Request age factor (0-30 points) - FIXED: Escalates over time
    if 'created_at' in request_data:
        age_hours = (datetime.utcnow() - request_data['created_at']).total_seconds() / 3600
        # Gains 4 points per hour waiting, maxing out at 30 points after ~7.5 hours
        age_score = min(30, age_hours * 4.0)
        score += age_score
    
    # 2. Blood group rarity factor (0-25 points)
    rare_groups = ['O-', 'B-', 'AB-', 'AB+']
    if request_data.get('blood_group') in rare_groups:
        score += 25
    else:
        score += 10
    
    # 3. Quantity factor (0-25 points)
    quantity = request_data.get('quantity', 1)
    score += min(25, quantity * 5)  # Maxes out at 5 units
    
    # 4. Explicit urgency level (0-20 points)
    urgency_levels = {
        'critical': 20,
        'high': 15,
        'normal': 5,
        'low': 0
    }
    explicit_urgency = request_data.get('urgency', 'normal').lower()
    score += urgency_levels.get(explicit_urgency, 5)
    
    return min(100.0, score)


def detect_emergency_keywords(text: str) -> list:
    """Detect emergency-related keywords in request reason."""
    if not text:
        return []
        
    emergency_keywords = [
        'emergency', 'urgent', 'critical', 'icu', 'surgery', 'accident',
        'trauma', 'bleeding', 'serious', 'life-threatening', 'immediately',
        'asap', 'emergency room', 'er', 'operating room', 'or'
    ]
    
    text_lower = text.lower()
    return [kw for kw in emergency_keywords if kw in text_lower]


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two geographic points using Haversine formula."""
    R = 6371.0 # Earth's radius in km
    
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def calculate_donor_score(donor: dict, request: dict, distance_km: float = None) -> float:
    """
    Calculate recommendation score for a donor.
    Includes Universal Compatibility Matrix.
    """
    score = 0.0
    
    # 1. Availability (Must pass first)
    if not donor.get('availability'):
        return 0.0  # Donor is unavailable, instant disqualification
    
    score += 30
    
    # 2. Medical Blood Compatibility (40 points)
    patient_bg = request.get('blood_group')
    donor_bg = donor.get('blood_group')
    
    if donor_bg == patient_bg:
        score += 40  # Exact match is highly preferred
    elif patient_bg in COMPATIBILITY_MATRIX and donor_bg in COMPATIBILITY_MATRIX[patient_bg]:
        score += 30  # Safe universal cross-match (e.g., O- giving to A+)
    else:
        return 0.0  # CRITICAL: Medically incompatible blood. Instant disqualification.
    
    # 3. Location proximity (20 points)
    if distance_km is not None:
        if distance_km <= 5:
            score += 20
        elif distance_km <= 15:
            score += 15
        elif distance_km <= 50:
            score += 10
        else:
            score += 5
    else:
        # City-based fallback
        score += 20 if donor.get('city') == request.get('city') else 5
    
    # 4. Donation activity (10 points) - FIXED: Better scaling
    units_donated = donor.get('units_donated', 0)
    donation_frequency = donor.get('donation_frequency', 0)
    
    if units_donated > 0 or donation_frequency > 0:
        # Gives 2 points per past donation, maxing out the 10 points at 5 donations
        activity_score = min(10.0, units_donated * 2.0)
        score += activity_score
    
    return min(100.0, score)


def format_recommendation_response(donors: list, scores: list) -> list:
    """Format recommendation data for API response."""
    recommendations = []
    
    for ranking, (donor, score) in enumerate(zip(donors, scores), 1):
        recommendations.append({
            'ranking': ranking,
            'donor_id': donor.get('id'),
            'donor_name': donor.get('donor_name'),
            'blood_group': donor.get('blood_group'),
            'city': donor.get('city'),
            'score': round(score, 2),
            'availability': donor.get('availability'),
            'units_donated': donor.get('units_donated'),
            'contact_info': donor.get('phone', 'Not available')
        })
    
    return recommendations


def predict_fulfillment_time(matching_donors_count: int, blood_group: str) -> int:
    """Predict time to fulfill blood request in hours."""
    base_time = 24
    
    if matching_donors_count >= 5:
        base_time = 4
    elif matching_donors_count >= 3:
        base_time = 8
    elif matching_donors_count >= 1:
        base_time = 12
    
    rare_groups = ['O-', 'B-', 'AB-', 'AB+']
    if blood_group in rare_groups:
        base_time += 12
        
    return base_time