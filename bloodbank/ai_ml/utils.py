"""
AI/ML Utility Functions for Blood Management System

Provides helper functions for:
- Data validation
- Scoring calculations
- Format conversions
- Logging
"""

from datetime import datetime, timedelta
import math


def calculate_urgency_score(request_data: dict) -> float:
    """
    Calculate AI urgency score based on multiple factors.
    
    Factors:
    - Request age (newer = higher urgency)
    - Blood group rarity
    - Quantity requested
    - Explicit urgency level
    
    Returns:
        float: Score between 0 and 100
    """
    score = 0.0
    
    # 1. Request age factor (0-30 points)
    if 'created_at' in request_data:
        age_hours = (datetime.utcnow() - request_data['created_at']).total_seconds() / 3600
        age_score = max(0, 30 - age_hours)  # Decreases over time
        score += age_score
    
    # 2. Blood group rarity factor (0-25 points)
    rare_groups = ['O-', 'B-', 'AB-', 'AB+']  # Rarer groups
    if request_data.get('blood_group') in rare_groups:
        score += 25
    else:
        score += 10
    
    # 3. Quantity factor (0-25 points)
    quantity = request_data.get('quantity', 1)
    score += min(25, quantity * 5)  # More units = higher urgency
    
    # 4. Explicit urgency level (0-20 points)
    urgency_levels = {
        'critical': 20,
        'high': 15,
        'normal': 5,
        'low': 0
    }
    explicit_urgency = request_data.get('urgency', 'normal').lower()
    score += urgency_levels.get(explicit_urgency, 5)
    
    return min(100, score)  # Cap at 100


def detect_emergency_keywords(text: str) -> list:
    """
    Detect emergency-related keywords in request reason.
    
    Returns:
        list: Detected keywords
    """
    emergency_keywords = [
        'emergency', 'urgent', 'critical', 'icu', 'surgery', 'accident',
        'trauma', 'bleeding', 'serious', 'life-threatening', 'immediately',
        'asap', 'emergency room', 'er', 'operating room', 'or'
    ]
    
    text_lower = text.lower()
    detected = [kw for kw in emergency_keywords if kw in text_lower]
    return detected


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two geographic points using Haversine formula.
    
    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates
    
    Returns:
        float: Distance in kilometers
    """
    # Earth's radius in kilometers
    R = 6371.0
    
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Differences
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    # Haversine formula
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    distance = R * c
    
    return distance


def calculate_donor_score(donor: dict, request: dict, distance_km: float = None) -> float:
    """
    Calculate recommendation score for a donor based on multiple factors.
    
    Factors:
    - Blood group match: 40 points
    - Availability: 30 points
    - Location proximity: 20 points
    - Donation activity: 10 points
    
    Args:
        donor: Donor data dict
        request: Blood request data dict
        distance_km: Distance in kilometers (optional)
    
    Returns:
        float: Score between 0 and 100
    """
    score = 0.0
    
    # 1. Blood group match (40 points)
    if donor.get('blood_group') == request.get('blood_group'):
        score += 40
    
    # 2. Availability (30 points)
    if donor.get('availability'):
        score += 30
    else:
        return 0  # Not available donors get 0 score
    
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
        if donor.get('city') == request.get('city'):
            score += 20
        else:
            score += 5
    
    # 4. Donation activity (10 points)
    units_donated = donor.get('units_donated', 0)
    donation_frequency = donor.get('donation_frequency', 0)
    
    if units_donated > 0 or donation_frequency > 0:
        activity_score = min(10, units_donated / 10)  # More donations = higher score
        score += activity_score
    
    return min(100, score)


def format_recommendation_response(donors: list, scores: list) -> list:
    """
    Format recommendation data for API response.
    
    Returns:
        list: List of donor recommendations with scores and ranking
    """
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
    """
    Predict time to fulfill blood request in hours.
    
    Uses simple heuristics:
    - More matching donors = faster fulfillment
    - Rare blood groups = slower fulfillment
    
    Args:
        matching_donors_count: Number of available donors
        blood_group: Requested blood group
    
    Returns:
        int: Predicted hours to fulfill
    """
    base_time = 24  # Base: 24 hours
    
    # Reduce time based on donor availability
    if matching_donors_count >= 5:
        base_time = 4
    elif matching_donors_count >= 3:
        base_time = 8
    elif matching_donors_count >= 1:
        base_time = 12
    
    # Increase time for rare blood groups
    rare_groups = ['O-', 'B-', 'AB-', 'AB+']
    if blood_group in rare_groups:
        base_time += 12
    
    return base_time


def log_recommendation(blood_request_id: int, donor_id: int, score: float, ranking: int):
    """
    Log recommendation for analytics (to be implemented with database logging).
    
    Args:
        blood_request_id: ID of blood request
        donor_id: ID of recommended donor
        score: Recommendation score
        ranking: Position in recommendations (1st, 2nd, etc.)
    """
    # This will be implemented using DonorRecommendation model
    pass
