"""
Feature 2: Location-Based Smart Matching

Uses Haversine formula to find nearest donors based on lat/long coordinates.
Provides city-based fallback for donors without GPS data.

Features:
- Bounding Box SQL optimization (High Performance)
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
        self.earth_radius_km = 6371.0 # Standard Earth radius
    
    def _get_bounding_box(self, lat: float, lon: float, radius_km: float) -> tuple:
        """
        Calculate min/max lat and long for a given radius.
        Creates a fast SQL-queryable geographic square.
        """
        # Coordinate offsets in radians
        dlat = radius_km / self.earth_radius_km
        dlon = radius_km / (self.earth_radius_km * math.cos(math.radians(lat)))
        
        # Calculate min/max coordinates
        min_lat = lat - math.degrees(dlat)
        max_lat = lat + math.degrees(dlat)
        min_lon = lon - math.degrees(dlon)
        max_lon = lon + math.degrees(dlon)
        
        return min_lat, max_lat, min_lon, max_lon

    def find_nearest_donors(self, blood_request_id: int, limit: int = 5, radius_km: float = None) -> dict:
        """
        Find nearest available donors for a blood request within a specific radius.
        """
        try:
            # Set dynamic search radius
            search_radius = radius_km if radius_km else self.default_search_radius_km
            
            # Get blood request
            blood_request = BloodRequest.query.get(blood_request_id)
            if not blood_request:
                return {'success': False, 'message': 'Request not found'}
            
            # Get requester location
            requester = blood_request.user
            if not requester.donor_profile or not requester.donor_profile.latitude:
                # Fallback to city-based search if no GPS data
                return self._city_based_search(blood_request, limit)
            
            requester_lat = requester.donor_profile.latitude
            requester_lon = requester.donor_profile.longitude
            
            # 1. Calculate Bounding Box to prevent memory overload
            min_lat, max_lat, min_lon, max_lon = self._get_bounding_box(
                requester_lat, requester_lon, search_radius
            )
            
            # 2. Optimized SQL Query: Only fetch donors inside the geographical square
            donors = Donor.query.filter(
                and_(
                    Donor.blood_group == blood_request.blood_group,
                    Donor.availability == True,
                    Donor.latitude.isnot(None),
                    Donor.longitude.isnot(None),
                    Donor.latitude.between(min_lat, max_lat),
                    Donor.longitude.between(min_lon, max_lon)
                )
            ).all()
            
            if not donors:
                return {
                    'success': True,
                    'message': f'No donors available within {search_radius}km',
                    'donors': []
                }
            
            # 3. Calculate exact distances and filter out corners of the bounding box
            donors_with_distance = []
            for donor in donors:
                distance = haversine_distance(
                    requester_lat, requester_lon,
                    donor.latitude, donor.longitude
                )
                
                # Strict radius enforcement (Bounding box is a square, radius is a circle)
                if distance <= search_radius:
                    donors_with_distance.append({
                        'donor': donor,
                        'distance_km': distance,
                        'has_gps': True
                    })
            
            # Sort by exact distance
            donors_with_distance.sort(key=lambda x: x['distance_km'])
            
            # Format response
            nearest_donors = []
            for item in donors_with_distance[:limit]:
                nearest_donors.append(self._format_donor_response(item))
            
            return {
                'success': True,
                'message': f'Nearest donors found within {search_radius}km',
                'search_type': 'geolocation',
                'search_radius_km': search_radius,
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
        Find nearest donors for emergency requests using expanded search radius.
        """
        # Fix: Now successfully passing the expanded 100km radius to the core function
        result = self.find_nearest_donors(
            blood_request_id, 
            limit=3, 
            radius_km=self.emergency_search_radius_km
        )
        
        if result['success']:
            result['message'] = 'Emergency - Finding nearest donors'
            result['is_emergency'] = True
        
        return result
    
    def _city_based_search(self, blood_request: BloodRequest, limit: int) -> dict:
        """
        Fallback search using city-based matching.
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