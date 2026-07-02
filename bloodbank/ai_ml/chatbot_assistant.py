"""
Feature 4: AI Chatbot Assistant

Provides intelligent assistance to users through conversational AI.

Features:
- Answers donation FAQ
- Guides emergency users
- Explains donation process
- Helps navigation
- Maintains conversation history
- Session-based memory

Uses rule-based responses (can be upgraded to OpenAI/Dialogflow).
"""

from flask import current_app, session
from datetime import datetime
from bloodbank.models import ChatConversation, User
from bloodbank.extensions import db


class ChatbotAssistant:
    """AI Chatbot for blood donation assistance."""
    
    def __init__(self):
        self.name = "BloodBot"
        self.version = "1.0"
        
        # Knowledge base for FAQ
        self.knowledge_base = {
            'donation': {
                'keywords': ['donate', 'donation', 'how to donate', 'become a donor'],
                'response': 'To become a blood donor: 1) Register as a donor 2) Complete health screening 3) Schedule donation appointment 4) Donate at our center. Blood donation takes about 45 minutes and is completely safe!'
            },
            'eligibility': {
                'keywords': ['eligible', 'can i donate', 'requirements', 'age', 'weight'],
                'response': 'Donor eligibility: Must be 18-65 years old, weigh at least 50kg, be in good health, and not have certain medical conditions. Please take our eligibility test to confirm.'
            },
            'process': {
                'keywords': ['process', 'what happens', 'donation process', 'steps'],
                'response': 'Donation process: 1) Registration & health check (5 min) 2) Refreshment (5 min) 3) Blood draw (5-10 min) 4) Recovery area (15 min). Total time: 45-60 minutes.'
            },
            'emergency': {
                'keywords': ['emergency', 'urgent', 'critical', 'asap', 'immediate'],
                'response': 'For emergency blood requests: Click "Request Blood" and select "Emergency". Our AI will prioritize your request and notify nearby donors immediately.'
            },
            'blood_groups': {
                'keywords': ['blood group', 'blood type', 'o+', 'a+', 'b+', 'ab+', 'o-', 'a-', 'b-', 'ab-'],
                'response': 'Blood groups: O+ (universal donor), O- (emergency donor), AB+ (universal recipient), AB- (rare). Different groups are needed for different patients. Check your type with our search tool!'
            },
            'search': {
                'keywords': ['search', 'find donor', 'find blood', 'locate', 'nearest'],
                'response': 'Use our Smart Donor Search tool: 1) Select blood group 2) Choose location/city 3) AI finds nearest donors 4) View contact info and make request. Easy and fast!'
            },
            'safety': {
                'keywords': ['safe', 'safety', 'risk', 'side effect', 'infection'],
                'response': 'Blood donation is safe! We use sterile equipment for each donation. Mild side effects (dizziness, minor bruising) are rare. Your body replenishes donated blood within weeks.'
            },
            'frequency': {
                'keywords': ['how often', 'frequency', 'when can i donate again', 'donation interval'],
                'response': 'Safe donation frequency: You can donate whole blood every 8 weeks (56 days). Plasma donors can donate every 2 weeks. This ensures your health and blood quality.'
            },
            'greeting': {
                'keywords': ['hi', 'hello', 'hey', 'help', 'support', 'chat'],
                'response': f'Hello! I\'m {self.name}, your blood donation assistant. I can help you with: donation FAQs, emergency requests, finding donors, and navigation. What would you like to know?'
            }
        }
    
    def process_message(self, user_message: str, user_id: int = None) -> dict:
        """
        Process user message and generate AI response.
        
        Args:
            user_message: User's chat message
            user_id: ID of user (optional)
        
        Returns:
            dict: Response with message, suggestions, and metadata
        """
        try:
            # Clean input
            message_lower = user_message.lower().strip()
            
            if not message_lower:
                return {
                    'success': False,
                    'message': 'Please enter a message.',
                    'suggestions': ['Ask about donation', 'Find blood donors', 'Emergency support']
                }
            
            # Match intent and get response
            response = self._match_intent_and_respond(message_lower)
            
            # Save conversation to database if user logged in
            if user_id:
                self._save_conversation(user_id, user_message, response['response'])
            
            return {
                'success': True,
                'message': response['response'],
                'intent': response.get('intent', 'general'),
                'confidence': response.get('confidence', 0.7),
                'suggestions': response.get('suggestions', self._get_follow_up_suggestions()),
                'timestamp': datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            current_app.logger.error(f"Error in chatbot: {e}")
            return {
                'success': False,
                'message': 'Sorry, I encountered an error. Please try again later.',
                'suggestions': ['Start over', 'Contact support']
            }
    
    def get_conversation_history(self, user_id: int, limit: int = 10) -> dict:
        """
        Get conversation history for a user.
        
        Args:
            user_id: ID of user
            limit: Maximum messages to return
        
        Returns:
            dict: Conversation history
        """
        try:
            conversations = ChatConversation.query.filter_by(
                user_id=user_id
            ).order_by(ChatConversation.created_at.desc()).limit(limit).all()
            
            history = []
            for conv in reversed(conversations):  # Reverse to chronological order
                history.append({
                    'timestamp': conv.created_at.isoformat(),
                    'user_message': conv.message,
                    'bot_response': conv.response
                })
            
            return {
                'success': True,
                'user_id': user_id,
                'conversation_count': len(history),
                'history': history
            }
        
        except Exception as e:
            current_app.logger.error(f"Error retrieving conversation: {e}")
            return {'success': False, 'message': str(e)}
    
    def _match_intent_and_respond(self, message: str) -> dict:
        """Match user intent and generate response."""
        # Check each category
        for intent, data in self.knowledge_base.items():
            for keyword in data['keywords']:
                if keyword in message:
                    return {
                        'intent': intent,
                        'response': data['response'],
                        'confidence': 0.9,
                        'suggestions': self._get_follow_up_suggestions(intent)
                    }
        
        # Default response if no match
        return {
            'intent': 'unknown',
            'response': f'I understand you\'re asking: "{message}". Unfortunately, I don\'t have specific information about that. Would you like to: 1) Browse FAQ section 2) Contact our support team 3) Ask another question?',
            'confidence': 0.3,
            'suggestions': ['Check FAQ', 'Contact support', 'Ask something else']
        }
    
    def _get_follow_up_suggestions(self, intent: str = None) -> list:
        """Get follow-up question suggestions."""
        suggestions = {
            'donation': ['Can I donate with tattoos?', 'What should I eat before donating?', 'How to find nearest donation center?'],
            'eligibility': ['What medical conditions prevent donation?', 'Can pregnant women donate?', 'Any age restrictions?'],
            'emergency': ['Find emergency donors', 'Request blood now', 'See priority queue'],
            'search': ['Search by blood group', 'Find donors near me', 'Contact a donor'],
            'process': ['Check donation schedule', 'What to expect', 'Recovery tips'],
            'general': ['Ask about donation', 'Find blood donors', 'Emergency support', 'Check my status']
        }
        
        return suggestions.get(intent, suggestions['general'])
    
    def _save_conversation(self, user_id: int, user_message: str, bot_response: str):
        """Save conversation to database for analytics."""
        try:
            conversation = ChatConversation(
                user_id=user_id,
                message=user_message,
                response=bot_response
            )
            db.session.add(conversation)
            db.session.commit()
        except Exception as e:
            current_app.logger.warning(f"Failed to save conversation: {e}")
    
    def get_chat_stats(self, user_id: int = None) -> dict:
        """
        Get chatbot usage statistics.
        
        Args:
            user_id: Optional - stats for specific user
        
        Returns:
            dict: Statistics
        """
        try:
            if user_id:
                count = ChatConversation.query.filter_by(user_id=user_id).count()
                return {
                    'user_id': user_id,
                    'total_messages': count,
                    'active': count > 0
                }
            else:
                total_messages = ChatConversation.query.count()
                total_users = db.session.query(ChatConversation.user_id).distinct().count()
                
                return {
                    'total_messages': total_messages,
                    'total_users': total_users,
                    'average_messages_per_user': round(total_messages / max(total_users, 1), 2)
                }
        
        except Exception as e:
            current_app.logger.error(f"Error getting chat stats: {e}")
            return {'success': False, 'message': str(e)}


# Initialize chatbot
chatbot_assistant = ChatbotAssistant()
