from typing import Dict, List

# Store last used settings for each chat
chat_settings: Dict[int, Dict[str, any]] = {}

def save_chat_settings(chat_id: int, settings: Dict[str, any]) -> None:
    """Save settings for a chat to be reused in future games."""
    chat_settings[chat_id] = settings.copy()

def get_chat_settings(chat_id: int) -> Dict[str, any]:
    """Get previously saved settings for a chat, or default settings if none exist."""
    default_settings = {
        "mr_white_start": False,
        "tiebreaker": "random",  # 'random' or 'none'
        "civilian_count": 0,
        "undercover_count": 0,
        "mr_white_count": 0,
    }
    return chat_settings.get(chat_id, default_settings).copy()

def validate_game_settings(settings: Dict[str, any], player_count: int) -> Dict[str, str]:
    """
    Validate game settings and return validation errors if any.
    
    Args:
        settings: Game settings dictionary
        player_count: Number of players in the game
        
    Returns:
        Dictionary of error messages keyed by setting name
    """
    errors = {}
    
    # Skip validation if using automatic role distribution
    if (settings["civilian_count"] == 0 and 
        settings["undercover_count"] == 0 and 
        settings["mr_white_count"] == 0):
        return errors
    
    # Calculate total roles
    total_roles = (
        settings["civilian_count"] +
        settings["undercover_count"] +
        settings["mr_white_count"]
    )
    
    # Check if total roles match player count
    if total_roles != player_count:
        errors["total_roles"] = f"Total roles ({total_roles}) don't match player count ({player_count})."
    
    # Check if civilians are enough (should be more than undercover)
    if settings["civilian_count"] <= settings["undercover_count"]:
        errors["civilian_count"] = f"Civilians ({settings['civilian_count']}) should outnumber Undercover players ({settings['undercover_count']})."
    
    # Check if there are any civilians
    if settings["civilian_count"] == 0:
        errors["civilian_count"] = "There must be at least one civilian."
        
    # Check if there are any bad roles
    if settings["undercover_count"] == 0 and settings["mr_white_count"] == 0:
        errors["bad_roles"] = "There must be at least one Undercover or Mr. White."
    
    return errors