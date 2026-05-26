"""
AI/ML API Routes for Blood Management System

Integrates all AI features into Flask REST API endpoints.

Endpoints:
- POST /api/ai/recommend-donors - Get recommended donors
- GET  /api/ai/nearest-donors - Find nearest donors
- GET  /api/ai/demand-prediction - Blood demand forecast
- POST /api/ai/chatbot - Chat with AI
- GET  /api/ai/emergency-priority - Prioritized requests
- POST /api/ai/train-model - Train ML model (admin only)
"""

from flask import Blueprint, request, jsonify, session, current_app
from functools import wraps
from bloodbank.models import BloodRequest, User
from bloodbank.extensions import db
from bloodbank.ai_ml.donor_recommendation import recommendation_engine
from bloodbank.ai_ml.location_matching import location_matcher
from bloodbank.ai_ml.demand_prediction import demand_predictor
from bloodbank.ai_ml.chatbot_assistant import chatbot_assistant
from bloodbank.ai_ml.emergency_priority import emergency_prioritizer

# Create Blueprint
ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')


# Decorator for authentication
def require_login(f):
    """Require user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def require_admin(f):
    """Require admin privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function


# ==================== Feature 1: Donor Recommendation ====================

@ai_bp.route('/recommend-donors', methods=['POST'])
@require_login
def recommend_donors():
    """
    Get AI-recommended donors for a blood request.
    
    Request body:
    {
        'blood_request_id': int,
        'top_n': int (optional, default: 5)
    }
    """
    try:
        data = request.get_json()
        blood_request_id = data.get('blood_request_id')
        top_n = data.get('top_n', 5)
        
        if not blood_request_id:
            return jsonify({
                'success': False,
                'message': 'blood_request_id required'
            }), 400
        
        # Get recommendations
        result = recommendation_engine.get_recommended_donors(blood_request_id, top_n)
        
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in recommend_donors: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_bp.route('/emergency-donors', methods=['POST'])
@require_login
def get_emergency_donors():
    """Get fastest available donors for emergency requests."""
    try:
        data = request.get_json()
        blood_request_id = data.get('blood_request_id')
        
        if not blood_request_id:
            return jsonify({'success': False, 'message': 'blood_request_id required'}), 400
        
        result = recommendation_engine.get_emergency_donors(blood_request_id)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in get_emergency_donors: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== Feature 2: Location Matching ====================

@ai_bp.route('/nearest-donors', methods=['POST'])
@require_login
def find_nearest_donors():
    """
    Find nearest donors using location-based matching.
    
    Request body:
    {
        'blood_request_id': int,
        'limit': int (optional, default: 5)
    }
    """
    try:
        data = request.get_json()
        blood_request_id = data.get('blood_request_id')
        limit = data.get('limit', 5)
        
        if not blood_request_id:
            return jsonify({'success': False, 'message': 'blood_request_id required'}), 400
        
        result = location_matcher.find_nearest_donors(blood_request_id, limit)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in find_nearest_donors: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_bp.route('/emergency-location-donors', methods=['POST'])
@require_login
def get_emergency_location_donors():
    """Find nearest donors for emergency with expanded radius."""
    try:
        data = request.get_json()
        blood_request_id = data.get('blood_request_id')
        
        if not blood_request_id:
            return jsonify({'success': False, 'message': 'blood_request_id required'}), 400
        
        result = location_matcher.find_emergency_donors(blood_request_id)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in get_emergency_location_donors: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== Feature 3: Demand Prediction ====================

@ai_bp.route('/demand-prediction', methods=['GET'])
@require_login
def get_demand_prediction():
    """Get blood demand prediction for all blood groups."""
    try:
        days_ahead = request.args.get('days_ahead', 7, type=int)
        
        result = demand_predictor.get_all_predictions(days_ahead)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in get_demand_prediction: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_bp.route('/demand-prediction/<blood_group>', methods=['GET'])
@require_login
def predict_blood_group_demand(blood_group):
    """Get demand prediction for specific blood group."""
    try:
        days_ahead = request.args.get('days_ahead', 7, type=int)
        
        result = demand_predictor.predict_demand(blood_group, days_ahead)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in predict_blood_group_demand: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_bp.route('/train-demand-model', methods=['POST'])
@require_admin
def train_demand_model():
    """Train ML model on historical data (admin only)."""
    try:
        days_history = request.json.get('days_history', 30)
        
        result = demand_predictor.train_demand_model(days_history)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in train_demand_model: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== Feature 4: Chatbot ====================

@ai_bp.route('/chatbot', methods=['POST'])
def chat():
    """Chat with AI assistant."""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({'success': False, 'message': 'Message required'}), 400
        
        user_id = session.get('user_id')
        result = chatbot_assistant.process_message(user_message, user_id)
        
        return jsonify(result), 200
    
    except Exception as e:
        current_app.logger.error(f"Error in chat: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_bp.route('/chat-history', methods=['GET'])
@require_login
def get_chat_history():
    """Get chat conversation history."""
    try:
        user_id = session['user_id']
        limit = request.args.get('limit', 10, type=int)
        
        result = chatbot_assistant.get_conversation_history(user_id, limit)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in get_chat_history: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_bp.route('/chat-stats', methods=['GET'])
@require_admin
def get_chat_stats():
    """Get chatbot usage statistics."""
    try:
        result = chatbot_assistant.get_chat_stats()
        return jsonify(result), 200
    
    except Exception as e:
        current_app.logger.error(f"Error in get_chat_stats: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== Feature 5: Emergency Priority ====================

@ai_bp.route('/emergency-priority/<int:request_id>', methods=['POST'])
@require_login
def prioritize_request(request_id):
    """Calculate priority score for blood request."""
    try:
        result = emergency_prioritizer.prioritize_request(request_id)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in prioritize_request: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_bp.route('/priority-queue', methods=['GET'])
@require_login
def get_priority_queue():
    """Get pending requests sorted by priority."""
    try:
        limit = request.args.get('limit', 10, type=int)
        
        result = emergency_prioritizer.get_priority_queue(limit)
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in get_priority_queue: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ai_bp.route('/critical-alerts', methods=['GET'])
@require_admin
def get_critical_alerts():
    """Get critical emergency alerts (admin only)."""
    try:
        result = emergency_prioritizer.get_critical_alerts()
        return jsonify(result), 200 if result['success'] else 400
    
    except Exception as e:
        current_app.logger.error(f"Error in get_critical_alerts: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== Health Check ====================

@ai_bp.route('/health', methods=['GET'])
def health_check():
    """Check if AI module is healthy."""
    return jsonify({
        'success': True,
        'message': 'AI/ML module is running',
        'features': [
            'Donor Recommendation',
            'Location Matching',
            'Demand Prediction',
            'Chatbot Assistant',
            'Emergency Priority'
        ]
    }), 200
