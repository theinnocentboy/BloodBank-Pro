"""
Feature 4: AI Chatbot Assistant

Provides intelligent assistance to users through conversational AI.

Features:
- Answers donation FAQ
- Guides emergency users
- Explains donation process
- Pre-compiled Regex Intent Matching (Optimized)
- Maintains conversation history
- Session-based memory

Uses highly optimized rule-based responses.
"""

from flask import current_app
from datetime import datetime
import re
from bloodbank.models import ChatConversation, User
from bloodbank.extensions import db


class ChatbotAssistant:
    """AI Chatbot for blood donation assistance."""
    
    def __init__(self):
        self.name = "BloodBot"
        self.version = "1.0"
        
        # Raw Knowledge Base
        raw_knowledge_base = {
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
                'keywords': ['emergency', 'urgent', 'critical', 'asap', 'immediate', 'or', 'er'],
                'response': 'For emergency blood requests: Click "Request Blood" and select "Emergency". Our AI will prioritize your request and notify nearby donors immediately.'
            },
            'blood_groups': {
                'keywords': ['blood group', 'blood type', 'o\+', 'a\+', 'b\+', 'ab\+', 'o\-', 'a\-', 'b\-', 'ab\-'],
                'response': 'Blood groups: O+ (universal donor), O- (emergency donor), AB+ (universal recipient), AB- (rare). Check your type with our search tool!'
            },
            'search': {
                'keywords': ['search', 'find donor', 'find blood', 'locate', 'nearest'],
                'response': 'Use our Smart Donor Search tool: 1) Select blood group 2) Choose location/city 3) AI finds nearest donors 4) View contact info and make request.'
            },
            'safety': {
                'keywords': ['safe', 'safety', 'risk', 'side effect', 'infection'],
                'response': 'Blood donation is safe! We use sterile equipment for each donation. Mild side effects are rare. Your body replenishes donated blood within weeks.'
            },
            'frequency': {
                'keywords': ['how often', 'frequency', 'when can i donate again', 'interval'],
                'response': 'Safe donation frequency: You can donate whole blood every 8 weeks (56 days). Plasma donors can donate every 2 weeks.'
            },
            'greeting': {
                'keywords': ['hi', 'hello', 'hey', 'help', 'support', 'chat'],
                'response': f'Hello! I\'m {self.name}, your blood donation assistant. I can help with FAQs, emergency requests, and finding donors. What would you like to know?'
            }
        }
        
        # O(1) Pre-compilation Optimization: 
        # Compile keywords into fast regex patterns to prevent substring false-positives
        self.knowledge_base = {}
        for intent, data in raw_knowledge_base.items():
            compiled_patterns = []
            for kw in data['keywords']:
                # Negative lookbehinds/lookaheads ensure we match exact words, 
                # safely handling characters like '+' and '-' in blood types.
                pattern = re.compile(rf'(?<![a-z0-9]){kw}(?![a-z0-9])', re.IGNORECASE)
                compiled_patterns.append(pattern)
                
            self.knowledge_base[intent] = {
                'patterns': compiled_patterns,
                'response': data['response']
            }
    
    def process_message(self, user_message: str, user_id: int = None) -> dict:
        """Process user message and generate AI response."""
        try:
            # Clean input
            message_clean = user_message.strip()
            
            if not message_clean:
                return {
                    'success': False,
                    'message': 'Please enter a message.',
                    'suggestions': ['Ask about donation', 'Find blood donors', 'Emergency support']
                }
            
            # Match intent and get response
            response = self._match_intent_and_respond(message_clean)
            
            # Save conversation to database if user logged in
            if user_id:
                self._save_conversation(user_id, message_clean, response['response'])
            
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
        """Get conversation history for a user."""
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
        """Match user intent using pre-compiled regex objects."""
        for intent, data in self.knowledge_base.items():
            for pattern in data['patterns']:
                if pattern.search(message):
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
        """Get chatbot usage statistics."""
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