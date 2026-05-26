"""
AI/ML Module for Blood Management System

This package contains all AI and Machine Learning features:
1. Intelligent Donor Recommendation System
2. Location-Based Smart Matching
3. ML Blood Demand Prediction
4. AI Chatbot Assistant
5. Emergency Priority AI

Import individual modules as needed for specific features.
"""

from bloodbank.ai_ml.donor_recommendation import RecommendationEngine
from bloodbank.ai_ml.location_matching import LocationMatcher
from bloodbank.ai_ml.demand_prediction import DemandPredictor
from bloodbank.ai_ml.emergency_priority import EmergencyPrioritizer

__all__ = [
    'RecommendationEngine',
    'LocationMatcher',
    'DemandPredictor',
    'EmergencyPrioritizer'
]
