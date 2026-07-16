"""
Feature 5: Emergency Priority AI

Automatically detects and prioritizes urgent blood requests.

Features:
- Detect emergency keywords in request reason
- Compute urgency score based on:
  * Request age
  * Blood group rarity
  * Quantity needed
  * Explicit urgency level
- Rank requests by priority
- Highlight critical cases on admin dashboard

The system automatically flags high-priority requests.
"""

from flask import current_app
from datetime import datetime
from bloodbank.models import BloodRequest
from bloodbank.extensions import db
from bloodbank.ai_ml.utils import (
    calculate_urgency_score,
    detect_emergency_keywords
)


class EmergencyPrioritizer:
    """AI-based emergency request prioritization."""
    
    def __init__(self):
        self.critical_threshold = 75  # Score >= 75 is critical
        self.high_threshold = 50       # Score >= 50 is high priority
        self.emergency_keywords_weight = 15  # Additional points for keywords
    
    def prioritize_request(self, blood_request_id: int) -> dict:
        """
        Calculate and set priority score for a blood request.
        """
        try:
            blood_request = db.session.get(BloodRequest, blood_request_id)
            if not blood_request:
                return {'success': False, 'message': 'Request not found'}
            
            # Calculate urgency score
            request_data = {
                'created_at': blood_request.created_at,
                'blood_group': blood_request.blood_group,
                'quantity': blood_request.quantity,
                'urgency': blood_request.urgency,
                'reason': blood_request.reason
            }
            
            base_score = calculate_urgency_score(request_data)
            
            # Detect emergency keywords
            keywords = detect_emergency_keywords(blood_request.reason)
            keyword_bonus = len(keywords) * self.emergency_keywords_weight
            
            final_score = min(100, base_score + keyword_bonus)
            
            # Determine priority level
            if final_score >= self.critical_threshold:
                priority_level = 'critical'
                is_emergency = True
            elif final_score >= self.high_threshold:
                priority_level = 'high'
                is_emergency = True
            else:
                priority_level = 'normal'
                is_emergency = False
            
            # Update database
            blood_request.priority_score = final_score
            blood_request.emergency_keywords = ','.join(keywords) if keywords else None
            blood_request.is_emergency = is_emergency
            
            db.session.commit()
            
            return {
                'success': True,
                'request_id': blood_request_id,
                'priority_score': round(final_score, 2),
                'priority_level': priority_level,
                'is_emergency': is_emergency,
                'base_score': round(base_score, 2),
                'keyword_bonus': keyword_bonus,
                'detected_keywords': keywords,
                'message': f'Request marked as {priority_level} priority'
            }
        
        except Exception as e:
            current_app.logger.error(f"Error prioritizing request: {e}")
            return {'success': False, 'message': str(e)}
    
    def get_priority_queue(self, limit: int = 10) -> dict:
        """
        Get all pending blood requests ranked by priority utilizing DB-level sorting.
        """
        try:
            # Optimized: Offload sorting and limiting entirely to the database
            pending_requests = BloodRequest.query.filter(
                BloodRequest.status.in_(['pending', 'in_progress'])
            ).order_by(
                db.func.coalesce(BloodRequest.priority_score, 0).desc(),
                BloodRequest.created_at.asc()
            ).limit(limit).all()
            
            # For total count (still fast as it's just a COUNT() query, not loading objects)
            total_pending = BloodRequest.query.filter(
                BloodRequest.status.in_(['pending', 'in_progress'])
            ).count()
            
            # Format queue
            priority_queue = []
            critical_count = 0
            high_count = 0
            
            for ranking, request in enumerate(pending_requests, 1):
                priority_level = self._get_priority_level(request.priority_score or 0)
                
                if priority_level == 'critical':
                    critical_count += 1
                elif priority_level == 'high':
                    high_count += 1
                
                # Fix: Properly handle empty keyword strings
                keywords_list = request.emergency_keywords.split(',') if request.emergency_keywords else []
                
                priority_queue.append({
                    'ranking': ranking,
                    'request_id': request.id,
                    'blood_group': request.blood_group,
                    'quantity': request.quantity,
                    'priority_score': round(request.priority_score or 0, 2),
                    'priority_level': priority_level,
                    'is_emergency': request.is_emergency,
                    'age_hours': round((datetime.utcnow() - request.created_at).total_seconds() / 3600, 1),
                    'reason': request.reason[:100],
                    'keywords': keywords_list,
                    'status': request.status,
                    'urgency': request.urgency,
                    'requested_by': request.user.full_name
                })
            
            return {
                'success': True,
                'total_pending': total_pending,
                'critical_requests': critical_count,
                'high_priority_requests': high_count,
                'queue': priority_queue,
                'message': f'Retrieved {len(priority_queue)} prioritized requests'
            }
        
        except Exception as e:
            current_app.logger.error(f"Error getting priority queue: {e}")
            return {'success': False, 'message': str(e)}
    
    def get_critical_alerts(self) -> dict:
        """
        Get all critical/emergency requests requiring immediate attention.
        """
        try:
            critical_requests = BloodRequest.query.filter(
                BloodRequest.is_emergency == True,
                BloodRequest.status.in_(['pending', 'in_progress'])
            ).order_by(
                BloodRequest.priority_score.desc()
            ).limit(5).all()  # Added limit(5) to DB query instead of list slicing
            
            alerts = []
            for request in critical_requests:
                age_minutes = round((datetime.utcnow() - request.created_at).total_seconds() / 60, 0)
                
                # Fix: Properly handle empty keyword strings
                keywords_list = request.emergency_keywords.split(',') if request.emergency_keywords else []
                
                alerts.append({
                    'request_id': request.id,
                    'alert_level': 'CRITICAL' if (request.priority_score or 0) >= 80 else 'HIGH',
                    'blood_group': request.blood_group,
                    'quantity_units': request.quantity,
                    'age_minutes': int(age_minutes),
                    'requester': request.user.full_name,
                    'reason': request.reason,
                    'keywords': keywords_list,
                    'score': round(request.priority_score or 0, 2),
                    'recommended_action': self._get_action_recommendation(request),
                    'contact': request.user.phone or 'No phone on file'
                })
            
            return {
                'success': True,
                'critical_count': len(critical_requests),
                'alerts_shown': len(alerts),
                'alerts': alerts,
                'timestamp': datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            current_app.logger.error(f"Error getting critical alerts: {e}")
            return {'success': False, 'message': str(e)}
    
    def _get_priority_level(self, score: float) -> str:
        """Convert score to priority level."""
        if score >= self.critical_threshold:
            return 'critical'
        elif score >= self.high_threshold:
            return 'high'
        else:
            return 'normal'
    
    def _get_action_recommendation(self, request: BloodRequest) -> str:
        """Get recommended action for a request."""
        age_hours = (datetime.utcnow() - request.created_at).total_seconds() / 3600
        
        if age_hours > 4:
            return 'URGENT: Contact donors immediately. Request is older than 4 hours.'
        elif request.quantity >= 3:
            return 'HIGH PRIORITY: Large quantity requested. Activate emergency contact list.'
        elif request.blood_group in ['O-', 'B-', 'AB-', 'AB+']:
            return 'RARE BLOOD: Contact rare blood donor network.'
        else:
            return 'Contact available donors in order of recommendation score.'


# Initialize prioritizer
emergency_prioritizer = EmergencyPrioritizer()