import os
from flask import Blueprint, request, jsonify, current_app
from groq import Groq
from bloodbank.models import BloodInventory

# Renamed to avoid clashing with your existing ML ai_routes.py
chatbot_bp = Blueprint('chatbot_api', __name__, url_prefix='/api/smart_chat')

@chatbot_bp.route('/ask', methods=['POST'])
# @login_required (Uncomment if you only want logged-in users to use the bot)
def chatbot():
    data = request.get_json()
    user_message = data.get('message')

    if not user_message:
        return jsonify({'success': False, 'error': 'No message provided'}), 400

    try:
        # 1. Fetch live context from the database
        # This makes the AI "aware" of the current hospital stock
        inventory = BloodInventory.query.all()
        if inventory:
            inventory_status = "\n".join([f"- {item.blood_group}: {item.units} units" for item in inventory])
        else:
            inventory_status = "Inventory data is currently unavailable."

        # 2. Construct the System Prompt (The AI's Brain/Rules & App Knowledge)
        system_prompt = f"""
        You are the official AI assistant for BloodBank Pro. You are helpful, empathetic, and professional.
        Your primary job is to answer questions about blood donation, our platform's features, and blood availability.

        CURRENT LIVE INVENTORY:
        {inventory_status}

        BLOODBANK PRO APP KNOWLEDGE BASE (How to use this site):
        - To Request Blood: Users must navigate to their Dashboard, click "Request Blood", fill out the urgency form, and upload a valid doctor's requisition document.
        - To Become a Donor: Users must go to their Profile, select the "Donor" tab, enter their blood group and city, and toggle their availability to 'Yes'.
        - Approval Process: Once a blood request is submitted, it goes to "Pending Review". An Admin must securely view the uploaded medical document, Verify it, and then Approve the release of inventory.
        - Updating Passwords or Details: Users can update their name, email, or password by clicking "Profile" in the navigation bar.

        Strict Guidelines:
        1. If a user asks how to do something on the site, use the exact App Knowledge Base above to guide them step-by-step.
        2. If a user asks about blood availability, use the exact live inventory data provided above.
        3. If inventory for a specific blood group is below 10 units, warn the user that it is "critically low".
        4. Format your responses cleanly using HTML tags like <strong> for bolding, <ul>/<li> for lists, and <br> for line breaks. Do NOT use markdown (**).
        5. Keep responses concise, friendly, and directly related to BloodBank Pro.
        """

        # 3. Initialize Groq Client and Call the LLM
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # <-- Update this line right here
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3, 
            max_tokens=300
        )

        bot_response = completion.choices[0].message.content

        return jsonify({
            'success': True,
            'message': bot_response
        })

    except Exception as e:
        print(f"AI Chatbot Error: {e}")
        return jsonify({
            'success': False,
            'message': 'I am currently undergoing maintenance or experiencing heavy traffic. Please try again in a moment.'
        }), 500