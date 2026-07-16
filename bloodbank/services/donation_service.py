"""
Core business logic for physical blood donation processing.
Enforces medical rules, logs vitals, and generates inventory records.
"""

from datetime import datetime, timedelta
import uuid
from flask import current_app
from bloodbank.extensions import db
from bloodbank.models import Donor, DonationAppointment, MedicalScreening, DonationRecord

class DonationService:
    
    @staticmethod
    def process_walk_in(appointment_id: int, admin_id: int, vitals: dict) -> dict:
        """
        Process a donor's physical appointment, log vitals, and generate blood record if approved.
        
        vitals dict format: {
            'weight_kg': float,
            'blood_pressure': str,
            'hemoglobin_level': float,
            'temperature_c': float
        }
        """
        try:
            appointment = db.session.get(DonationAppointment, appointment_id)
            if not appointment:
                return {'success': False, 'message': 'Appointment not found.'}
            
            donor = appointment.donor
            
            # 1. ENFORCE THE 56-DAY RULE
            if donor.last_donation:
                days_since_last = (datetime.utcnow().date() - donor.last_donation.date()).days
                if days_since_last < 56:
                    return {
                        'success': False, 
                        'message': f'MEDICAL LOCK: Donor must wait {56 - days_since_last} more days to donate.'
                    }

            # 2. AUTO-EVALUATE VITALS
            # Basic medical thresholds: weight >= 50kg, Hemoglobin >= 12.5, Temp <= 37.5C
            is_approved = True
            disqualify_reason = None
            
            if vitals.get('weight_kg', 0) < 50:
                is_approved = False
                disqualify_reason = "Underweight (Under 50kg)"
            elif vitals.get('hemoglobin_level', 0) < 12.5:
                is_approved = False
                disqualify_reason = "Low Hemoglobin"
            elif vitals.get('temperature_c', 0) > 37.5:
                is_approved = False
                disqualify_reason = "Elevated Temperature"

            # 3. CREATE SCREENING RECORD
            screening = MedicalScreening(
                appointment_id=appointment.id,
                admin_id=admin_id,
                weight_kg=vitals.get('weight_kg'),
                blood_pressure=vitals.get('blood_pressure'),
                hemoglobin_level=vitals.get('hemoglobin_level'),
                temperature_c=vitals.get('temperature_c'),
                is_approved=is_approved,
                disqualification_reason=disqualify_reason
            )
            db.session.add(screening)

            # 4. HANDLE REJECTION OR SUCCESS
            if not is_approved:
                appointment.status = 'disqualified'
                # Temporarily lock donor profile
                donor.availability = False
                db.session.commit()
                return {
                    'success': False,
                    'message': f'Donor disqualified: {disqualify_reason}',
                    'status': 'disqualified'
                }

            # If approved, generate the physical blood bag record
            appointment.status = 'completed'
            
            # Generate unique Bag Serial Number (e.g., BLD-20260712-A1B2)
            date_prefix = datetime.utcnow().strftime("%Y%m%d")
            unique_hash = uuid.uuid4().hex[:4].upper()
            serial_number = f"BLD-{date_prefix}-{unique_hash}"
            
            # Standard Whole Blood expires in 42 days
            expiry_date = datetime.utcnow() + timedelta(days=42)

            record = DonationRecord(
                donor_id=donor.id,
                appointment_id=appointment.id,
                admin_id=admin_id,
                unit_serial_number=serial_number,
                blood_component='Whole Blood',
                quantity_ml=450,
                expiry_date=expiry_date
            )
            db.session.add(record)

            # 5. UPDATE DONOR PROFILE STATS
            donor.units_donated = (donor.units_donated or 0) + 1
            donor.last_donation = datetime.utcnow()
            donor.donation_frequency = (donor.donation_frequency or 0) + 1
            
            # Execute all database writes in one secure transaction
            db.session.commit()

            return {
                'success': True,
                'message': 'Donation successful. Bag logged into inventory.',
                'serial_number': serial_number,
                'expiry_date': expiry_date.strftime("%Y-%m-%d")
            }

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error processing donation: {e}")
            return {'success': False, 'message': 'Internal database error.'}

# Initialize service
donation_service = DonationService()

class ScreeningService:
    @staticmethod
    def validate_vitals(vitals):
        """
        Validates vitals based on standard Indian screening guidelines.
        Returns (is_passed, message, status)
        """
        weight = vitals.get('weight_kg', 0)
        hb = vitals.get('hemoglobin_level', 0)
        bp = vitals.get('blood_pressure', '') # Expected format "120/80"
        
        # 1. Weight Check
        if weight < 45:
            return False, "Deferred: Underweight (< 45kg).", "deferred"
            
        # 2. Hemoglobin Check
        if hb < 12.5:
            return False, "Deferred: Low Hemoglobin (Anemia Risk).", "deferred"
        if hb > 18.0:
            return False, "Flagged: High Hemoglobin. Requires Medical Officer review.", "flagged"
            
        # 3. Blood Pressure Check (Simple parse)
        try:
            systolic, diastolic = map(int, bp.split('/'))
            if not (100 <= systolic <= 140) or not (60 <= diastolic <= 90):
                return False, "Deferred: Blood Pressure out of normal range.", "deferred"
        except:
            return False, "Invalid Blood Pressure format (Use 120/80).", "deferred"

        return True, "Passed: Donor is fit for donation.", "cleared"