import os
# os: Access environment variables

import json
# json: Format session state data as JSON strings

from typing import Optional
# Store session service reference
_session_service = None
_session_context = None

def set_session_context(session_service, app_name, user_id, session_id):
    """Set the session context for accessing session state."""
    global _session_service, _session_context
    _session_service = session_service
    _session_context = {
        'app_name': app_name,
        'user_id': user_id,
        'session_id': session_id
    }

def get_session_state(key: Optional[str] = None) -> str:
    """
    Retrieve session state information from the current session.
    
    This tool demonstrates that the agent can access session state through the Runner.
    The Runner automatically provides access to the session state for the current session.
    
    Available keys in session state:
    - user_name, user_email, user_phone
    - user_address, user_city, user_state, user_zip, user_country
    - user_recent_searches: List of recent searches
    - user_preferences: User preferences and interests
    
    Args:
        key: Optional specific key to retrieve (e.g., 'user_name', 'user_recent_searches'). 
             If None, returns all session state as JSON string.
    
    Returns:
        The session state value(s) as a formatted string. Lists are formatted as comma-separated values.
    """
    if not _session_service or not _session_context:
        return "Session context not available"
    
    try:
        session = _session_service.get_session(
            app_name=_session_context['app_name'],
            user_id=_session_context['user_id'],
            session_id=_session_context['session_id']
        )
        
        if key:
            if key not in session.state:
                return f"Key '{key}' not found. Available keys: {', '.join(session.state.keys())}"
            
            value = session.state.get(key)
            # Format lists nicely
            if isinstance(value, list):
                return ', '.join(str(v) for v in value)
            return str(value)
        else:
            return json.dumps(session.state, indent=2)
    except Exception as e:
        return f"Error accessing session state: {str(e)}"