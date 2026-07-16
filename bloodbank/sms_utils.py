from twilio.rest import Client
from flask import current_app

def send_sms_otp(phone_number: str, otp_code: str) -> bool:
    """Sends a 6-digit OTP using the Twilio API."""
    account_sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    auth_token = current_app.config.get("TWILIO_AUTH_TOKEN")
    twilio_number = current_app.config.get("TWILIO_PHONE_NUMBER")
    
    if not all([account_sid, auth_token, twilio_number]):
        current_app.logger.error("Twilio credentials missing from config.")
        return False

    try:
        client = Client(account_sid, auth_token)
        
        # Twilio strictly requires the E.164 format with the country code
        # This safely adds +91 if the user only entered their 10-digit number
        formatted_number = str(phone_number).strip()
        if not formatted_number.startswith("+"):
            formatted_number = f"+91{formatted_number.lstrip('0')}"
            
        message = client.messages.create(
            body=f"Your BloodBank Pro login OTP is {otp_code}. Do not share this code.",
            from_=twilio_number,
            to=formatted_number
        )
        
        current_app.logger.info(f"Twilio SMS sent successfully to {formatted_number}. SID: {message.sid}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"Twilio SMS failed: {e}")
        return False