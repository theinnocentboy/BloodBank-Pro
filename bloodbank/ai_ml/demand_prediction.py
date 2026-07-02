"""
Feature 3: Machine Learning Blood Demand Prediction

Uses Linear Regression to predict future blood demand.

Features:
- Predict demand for each blood group
- Identify shortage risks
- Generate time-series forecasts
- Provide insights for inventory management

Uses:
- scikit-learn for ML
- pandas for data processing
- numpy for computations
"""

from flask import current_app
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import pickle
import os
from bloodbank.models import BloodRequest, BloodInventory
from bloodbank.extensions import db


class DemandPredictor:
    """ML-based blood demand prediction engine."""
    
    def __init__(self):
        self.model_path = os.path.join(os.path.dirname(__file__), 'models')
        os.makedirs(self.model_path, exist_ok=True)
        self.blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        self.models = {}  # Cache models
        self.scalers = {}  # Cache scalers
    
    def train_demand_model(self, days_history: int = 30) -> dict:
        """
        Train ML model on historical blood request data.
        
        Args:
            days_history: Number of past days to use for training
        
        Returns:
            dict: Training results
        """
        try:
            results = {'success': True, 'trained_groups': []}
            
            # Get historical data
            start_date = datetime.utcnow() - timedelta(days=days_history)
            historical_requests = BloodRequest.query.filter(
                BloodRequest.created_at >= start_date
            ).all()
            
            if not historical_requests:
                return {
                    'success': False,
                    'message': f'Insufficient data: {len(historical_requests)} requests found',
                    'trained_groups': []
                }
            
            # Train model for each blood group
            for blood_group in self.blood_groups:
                try:
                    # Filter requests for this blood group
                    group_requests = [r for r in historical_requests if r.blood_group == blood_group]
                    
                    if len(group_requests) < 3:
                        continue  # Skip groups with too little data
                    
                    # Prepare training data
                    X, y = self._prepare_training_data(group_requests, days_history)
                    
                    if X is None or len(X) < 3:
                        continue
                    
                    # Train model
                    model, scaler = self._train_linear_model(X, y)
                    
                    # Save model
                    self._save_model(blood_group, model, scaler)
                    
                    results['trained_groups'].append({
                        'blood_group': blood_group,
                        'samples': len(X),
                        'status': 'trained'
                    })
                
                except Exception as e:
                    current_app.logger.warning(f"Failed to train model for {blood_group}: {e}")
                    continue
            
            results['message'] = f"Trained models for {len(results['trained_groups'])} blood groups"
            return results
        
        except Exception as e:
            current_app.logger.error(f"Error in demand model training: {e}")
            return {'success': False, 'message': str(e), 'trained_groups': []}
    
    def predict_demand(self, blood_group: str, days_ahead: int = 7) -> dict:
        """
        Predict blood demand for next N days.
        
        Args:
            blood_group: Blood group to predict for
            days_ahead: Number of days to forecast
        
        Returns:
            dict: Prediction results
        """
        try:
            if blood_group not in self.blood_groups:
                return {'success': False, 'message': f'Invalid blood group: {blood_group}'}
            
            # Load or train model
            model, scaler = self._get_or_train_model(blood_group)
            
            if model is None:
                return {
                    'success': False,
                    'message': f'Cannot predict for {blood_group}: insufficient data'
                }
            
            # Prepare prediction data
            current_date = datetime.utcnow().date()
            predictions = []
            
            for day in range(1, days_ahead + 1):
                pred_date = current_date + timedelta(days=day)
                
                # Create feature vector
                day_of_week = pred_date.weekday()
                day_of_month = pred_date.day
                month = pred_date.month
                
                X_pred = np.array([[day_of_week, day_of_month, month]])
                X_pred_scaled = scaler.transform(X_pred)
                
                # Predict
                demand = model.predict(X_pred_scaled)[0]
                demand = max(0, int(demand))  # Ensure non-negative
                
                predictions.append({
                    'date': pred_date.isoformat(),
                    'predicted_units': demand,
                    'confidence': 'medium'
                })
            
            # Check shortage risk
            total_predicted = sum(p['predicted_units'] for p in predictions)
            current_inventory = self._get_current_inventory(blood_group)
            shortage_risk = current_inventory < total_predicted / days_ahead
            
            return {
                'success': True,
                'blood_group': blood_group,
                'forecast_days': days_ahead,
                'predictions': predictions,
                'total_predicted_demand': total_predicted,
                'current_inventory': current_inventory,
                'shortage_risk': shortage_risk,
                'average_daily_demand': round(total_predicted / days_ahead, 2)
            }
        
        except Exception as e:
            current_app.logger.error(f"Error in demand prediction: {e}")
            return {'success': False, 'message': str(e)}
    
    def get_all_predictions(self, days_ahead: int = 7) -> dict:
        """
        Get predictions for all blood groups.
        
        Args:
            days_ahead: Number of days to forecast
        
        Returns:
            dict: Predictions for all blood groups
        """
        predictions = {}
        shortage_alerts = []
        
        for blood_group in self.blood_groups:
            result = self.predict_demand(blood_group, days_ahead)
            if result['success']:
                predictions[blood_group] = result
                
                if result.get('shortage_risk'):
                    shortage_alerts.append({
                        'blood_group': blood_group,
                        'predicted_demand': result['total_predicted_demand'],
                        'current_inventory': result['current_inventory'],
                        'action': 'Urgent: Contact donors immediately'
                    })
        
        return {
            'success': True,
            'total_groups_predicted': len(predictions),
            'shortage_alerts': shortage_alerts,
            'all_predictions': predictions
        }
    
    def _prepare_training_data(self, requests: list, days_history: int):
        """Prepare training data from blood requests."""
        try:
            dates = [r.created_at.date() for r in requests]
            daily_demand = pd.Series(dates).value_counts().sort_index()
            
            if len(daily_demand) < 3:
                return None, None
            
            # Create feature matrix
            X = []
            y = []
            
            for date, count in daily_demand.items():
                X.append([
                    date.weekday(),      # 0-6 (Monday-Sunday)
                    date.day,            # 1-31
                    date.month           # 1-12
                ])
                y.append(count)
            
            return np.array(X), np.array(y)
        
        except Exception as e:
            current_app.logger.error(f"Error preparing training data: {e}")
            return None, None
    
    def _train_linear_model(self, X, y):
        """Train linear regression model."""
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        model = LinearRegression()
        model.fit(X_scaled, y)
        
        return model, scaler
    
    def _save_model(self, blood_group: str, model, scaler):
        """Save trained model and scaler."""
        try:
            model_file = os.path.join(self.model_path, f'{blood_group}_model.pkl')
            scaler_file = os.path.join(self.model_path, f'{blood_group}_scaler.pkl')
            
            with open(model_file, 'wb') as f:
                pickle.dump(model, f)
            with open(scaler_file, 'wb') as f:
                pickle.dump(scaler, f)
        
        except Exception as e:
            current_app.logger.error(f"Error saving model: {e}")
    
    def _get_or_train_model(self, blood_group: str):
        """Load saved model or train new one."""
        # Try to load from cache
        if blood_group in self.models:
            return self.models[blood_group], self.scalers[blood_group]
        
        # Try to load from file
        model_file = os.path.join(self.model_path, f'{blood_group}_model.pkl')
        scaler_file = os.path.join(self.model_path, f'{blood_group}_scaler.pkl')
        
        if os.path.exists(model_file) and os.path.exists(scaler_file):
            try:
                with open(model_file, 'rb') as f:
                    model = pickle.load(f)
                with open(scaler_file, 'rb') as f:
                    scaler = pickle.load(f)
                
                self.models[blood_group] = model
                self.scalers[blood_group] = scaler
                return model, scaler
            
            except Exception as e:
                current_app.logger.error(f"Error loading model: {e}")
        
        return None, None
    
    def _get_current_inventory(self, blood_group: str) -> int:
        """Get current blood inventory for a group."""
        try:
            inventory = BloodInventory.query.filter_by(blood_group=blood_group).first()
            return inventory.units if inventory else 0
        except:
            return 0


# Initialize predictor
demand_predictor = DemandPredictor()
