# DTT Platform

A scalable Discrete Trial Teaching (DTT) platform built with Flask and React.

## Setup

1. Create a Python virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables (create a .env file):
```
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///app.db  # For development
PORT=5008  # Optional, defaults to 5008
```

4. Initialize the database:
```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

## Running the Application

1. Start the Flask backend:
```bash
# Development mode
python wsgi.py

# Production mode with gunicorn
gunicorn wsgi:app
```

The server will start at http://localhost:5008 (or your configured PORT)

## API Endpoints

### Authentication
- POST /api/v1/auth/register - Register a new user
- POST /api/v1/auth/login - Login and get JWT token

### DTT Sessions
- POST /api/v1/dtt/generate-grid - Generate a new DTT grid
- POST /api/v1/dtt/log-interaction - Log user interactions
- GET /api/v1/dtt/stimuli - Get available stimuli

## Development

- The application uses Flask for the backend API
- SQLAlchemy for database operations
- JWT for authentication
- CORS enabled for development
- Environment variables control the port (PORT) and other configurations 