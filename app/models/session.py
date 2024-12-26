from app import db
from datetime import datetime
import json

class Session(db.Model):
    __tablename__ = 'sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    config = db.Column(db.JSON)  # Stores session configuration (grid size, prompts, etc.)
    completed = db.Column(db.Boolean, default=False)
    
    # Store interactions as JSON
    interactions = db.Column(db.JSON)
    
    def add_interaction(self, interaction_data):
        """Add a new interaction to the session"""
        current = json.loads(self.interactions or '[]')
        current.append({
            'timestamp': datetime.utcnow().isoformat(),
            **interaction_data
        })
        self.interactions = json.dumps(current)
    
    def complete_session(self):
        """Mark the session as complete and set end time"""
        self.completed = True
        self.end_time = datetime.utcnow()
    
    def __repr__(self):
        return f'<Session {self.id} (User: {self.user_id})>' 