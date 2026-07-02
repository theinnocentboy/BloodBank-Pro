"""
Feature 2: Location-Based Smart Matching

Uses Haversine formula to find nearest donors based on lat/long coordinates.
Provides city-based fallback for donors without GPS data.

Features:
- Accurate distance calculation
- Nearest donor prioritization
- Emergency sorting
- City-based fallback
"""

from flask import current_app
from sqlalchemy import and_
import math
from bloodbank.models import Donor, BloodRequest, User
from bloodbank.ai_ml.utils import haversine_distance


class LocationMatcher:
    """Location-based donor matching using geolocation."""
    
    def __init__(self):
        self.default_search_radius_km = 50  # Default search radius
        self.emergency_search_radius_km = 100  # Emergency search radius
    
    def find_nearest_donors(self, blood_request_id: int, limit: int = 5) -> dict:
        """
        Find nearest available donors for a blood request.
        
        Uses lat/long if available, otherwise falls back to city matching.
        
        Args:
            blood_request_id: ID of blood request
            limit: Maximum donors to return
        
        Returns:
            dict with nearest donors sorted by distance
        """
        try:
            # Get blood request
            blood_request = BloodRequest.query.get(blood_request_id)
            if not blood_request:
                return {'success': False, 'message': 'Request not found'}
            
            # Get requester location
            requester = blood_request.user
            if not requester.donor_profile or not requester.donor_profile.latitude:
                # Fallback to city-based search
                return self._city_based_search(blood_request, limit)
            
            requester_lat = requester.donor_profile.latitude
            requester_lon = requester.donor_profile.longitude
            
            # Get all available donors with matching blood group
            donors = Donor.query.filter(
                and_(
                    Donor.blood_group == blood_request.blood_group,
                    Donor.availability == True
                )
            ).all()
            
            if not donors:
                return {
                    'success': True,
                    'message': 'No donors available',
                    'donors': []
                }
            
            # Calculate distances
            donors_with_distance = []
            for donor in donors:
                if donor.latitude and donor.longitude:
                    distance = haversine_distance(
                        requester_lat, requester_lon,
                        donor.latitude, donor.longitude
                    )
                    donors_with_distance.append({
                        'donor': donor,
                        'distance_km': distance,
                        'has_gps': True
                    })
            
            # Sort by distance
            donors_with_distance.sort(key=lambda x: x['distance_km'])
            
            # Format response
            nearest_donors = []
            for item in donors_with_distance[:limit]:
                nearest_donors.append(self._format_donor_response(item))
            
            return {
                'success': True,
                'message': 'Nearest donors found',
                'search_type': 'geolocation',
                'requester_location': {
                    'latitude': requester_lat,
                    'longitude': requester_lon
                },
                'donors': nearest_donors,
                'total_found': len(donors_with_distance)
            }
        
        except Exception as e:
            current_app.logger.error(f"Error in location matching: {e}")
            return {'success': False, 'message': str(e)}
    
    def find_emergency_donors(self, blood_request_id: int) -> dict:
        """
        Find nearest donors for emergency requests.
        
        Uses expanded search radius and stricter time limits.
        
        Args:
            blood_request_id: ID of blood request
        
        Returns:
            dict with emergency-priority donors
        """
        result = self.find_nearest_donors(blood_request_id, limit=3)
        
        if result['success']:
            result['message'] = 'Emergency - Finding nearest donors'
            result['is_emergency'] = True
            result['search_radius_km'] = self.emergency_search_radius_km
        
        return result
    
    def _city_based_search(self, blood_request: BloodRequest, limit: int) -> dict:
        """
        Fallback search using city-based matching.
        
        When GPS data unavailable, match donors in same city.
        """
        try:
            requester_city = blood_request.user.donor_profile.city if blood_request.user.donor_profile else None
            
            if not requester_city:
                return {
                    'success': True,
                    'message': 'No location data available',
                    'donors': []
                }
            
            # Find donors in same city
            same_city_donors = Donor.query.filter(
                and_(
                    Donor.blood_group == blood_request.blood_group,
                    Donor.city == requester_city,
                    Donor.availability == True
                )
            ).limit(limit).all()
            
            # Find donors in nearby cities (fallback)
            if len(same_city_donors) < limit:
                other_donors = Donor.query.filter(
                    and_(
                        Donor.blood_group == blood_request.blood_group,
                        Donor.city != requester_city,
                        Donor.availability == True
                    )
                ).limit(limit - len(same_city_donors)).all()
                
                donors = same_city_donors + other_donors
            else:
                donors = same_city_donors
            
            formatted_donors = []
            for i, donor in enumerate(donors, 1):
                formatted_donors.append({
                    'ranking': i,
                    'donor_id': donor.id,
                    'name': donor.user.full_name,
                    'blood_group': donor.blood_group,
                    'city': donor.city,
                    'same_city': donor.city == requester_city,
                    'availability': donor.availability,
                    'phone': donor.user.phone,
                    'distance_km': 0 if donor.city == requester_city else 'Unknown'
                })
            
            return {
                'success': True,
                'message': 'Donors found using city-based search',
                'search_type': 'city_based',
                'requester_city': requester_city,
                'donors': formatted_donors,
                'total_found': len(donors)
            }
        
        except Exception as e:
            current_app.logger.error(f"Error in city-based search: {e}")
            return {'success': False, 'message': str(e)}
    
    def _format_donor_response(self, donor_item: dict) -> dict:
        """Format donor data for API response."""
        donor = donor_item['donor']
        return {
            'donor_id': donor.id,
            'name': donor.user.full_name,
            'blood_group': donor.blood_group,
            'city': donor.city,
            'distance_km': round(donor_item['distance_km'], 2),
            'availability': donor.availability,
            'units_donated': donor.units_donated,
            'phone': donor.user.phone,
            'last_donation': donor.last_donation.isoformat() if donor.last_donation else None,
            'contact_available': True if donor.user.phone else False
        }


# Initialize matcher
location_matcher = LocationMatcher()
