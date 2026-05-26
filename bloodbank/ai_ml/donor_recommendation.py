"""
Feature 1: Intelligent Donor Recommendation System

Matches blood requests with optimal donors using AI scoring algorithm.

Factors considered:
- Blood group match (critical)
- Geographic proximity
- Donor availability
- Previous donation activity
- Request urgency

Returns top N recommended donors ranked by score.
"""

from flask import current_app
from sqlalchemy import and_, or_
from bloodbank.models import Donor, BloodRequest, User, DonorRecommendation
from bloodbank.extensions import db
from bloodbank.ai_ml.utils import calculate_donor_score, format_recommendation_response
from datetime import datetime


class RecommendationEngine:
    """AI-powered donor recommendation engine."""
    
    def __init__(self):
        self.max_recommendations = 5
        self.min_score_threshold = 30  # Minimum score to recommend
    
    def get_recommended_donors(self, blood_request_id: int, top_n: int = 5) -> dict:
        """
        Get top N recommended donors for a blood request.
        
        Args:
            blood_request_id: ID of blood request
            top_n: Number of recommendations to return
        
        Returns:
            dict: {
                'success': bool,
                'message': str,
                'request_id': int,
                'blood_group': str,
                'recommendations': list,
                'fulfillment_time': int (hours),
                'total_donors_found': int
            }
        """
        try:
            # Get blood request
            blood_request = BloodRequest.query.get(blood_request_id)
            if not blood_request:
                return {
                    'success': False,
                    'message': 'Blood request not found',
                    'request_id': blood_request_id
                }
            
            # Get all available donors with matching blood group
            matching_donors = Donor.query.filter(
                and_(
                    Donor.blood_group == blood_request.blood_group,
                    Donor.availability == True
                )
            ).join(User).all()
            
            if not matching_donors:
                return {
                    'success': True,
                    'message': 'No donors available for this blood group',
                    'request_id': blood_request_id,
                    'blood_group': blood_request.blood_group,
                    'recommendations': [],
                    'total_donors_found': 0
                }
            
            # Score and rank donors
            scored_donors = []
            for donor in matching_donors:
                donor_dict = self._donor_to_dict(donor)
                score = calculate_donor_score(
                    donor_dict,
                    {'blood_group': blood_request.blood_group}
                )
                
                if score >= self.min_score_threshold:
                    scored_donors.append((donor, score))
            
            # Sort by score (descending)
            scored_donors.sort(key=lambda x: x[1], reverse=True)
            
            # Prepare response
            top_donors = scored_donors[:top_n]
            recommendations_data = []
            
            for ranking, (donor, score) in enumerate(top_donors, 1):
                donor_dict = self._donor_to_dict(donor)
                donor_dict['score'] = round(score, 2)
                recommendations_data.append(donor_dict)
                
                # Log recommendation
                self._log_recommendation(blood_request_id, donor.id, score, ranking)
            
            # Estimate fulfillment time
            fulfillment_time = self._estimate_fulfillment_time(
                len(top_donors),
                blood_request.blood_group
            )
            
            return {
                'success': True,
                'message': 'Donors found successfully',
                'request_id': blood_request_id,
                'blood_group': blood_request.blood_group,
                'recommendations': recommendations_data,
                'fulfillment_time_hours': fulfillment_time,
                'total_donors_found': len(matching_donors),
                'available_for_request': len(top_donors)
            }
            
        except Exception as e:
            current_app.logger.error(f"Error in recommendation engine: {e}")
            return {
                'success': False,
                'message': f'Error: {str(e)}',
                'request_id': blood_request_id
            }
    
    def get_emergency_donors(self, blood_request_id: int) -> dict:
        """
        Get fastest available donors for emergency requests.
        
        Prioritizes:
        1. Nearby donors
        2. Active donors
        3. High availability
        
        Args:
            blood_request_id: ID of blood request
        
        Returns:
            dict: Emergency donor recommendations
        """
        # Get regular recommendations
        result = self.get_recommended_donors(blood_request_id, top_n=3)
        
        if result['success'] and result['recommendations']:
            # For emergency, only return top 3 fastest
            result['recommendations'] = result['recommendations'][:3]
            result['message'] = 'Emergency donors - Top 3 fastest matches'
        
        return result
    
    def _donor_to_dict(self, donor: Donor) -> dict:
        """Convert Donor model to dictionary for scoring."""
        return {
            'id': donor.id,
            'donor_name': donor.user.full_name,
            'blood_group': donor.blood_group,
            'city': donor.city,
            'availability': donor.availability,
            'units_donated': donor.units_donated,
            'phone': donor.user.phone,
            'last_donation': donor.last_donation,
            'latitude': donor.latitude,
            'longitude': donor.longitude,
            'donation_frequency': donor.donation_frequency
        }
    
    def _estimate_fulfillment_time(self, donors_count: int, blood_group: str) -> int:
        """Estimate time to fulfill request in hours."""
        base_time = 24
        
        if donors_count >= 5:
            base_time = 4
        elif donors_count >= 3:
            base_time = 8
        elif donors_count >= 1:
            base_time = 12
        
        # Increase for rare groups
        if blood_group in ['O-', 'B-', 'AB-', 'AB+']:
            base_time += 12
        
        return base_time
    
    def _log_recommendation(self, request_id: int, donor_id: int, score: float, ranking: int):
        """Log recommendation for analytics."""
        try:
            recommendation_log = DonorRecommendation(
                blood_request_id=request_id,
                recommended_donor_id=donor_id,
                recommendation_score=score,
                ranking=ranking
            )
            db.session.add(recommendation_log)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to log recommendation: {e}")


# Initialize engine
recommendation_engine = RecommendationEngine()
