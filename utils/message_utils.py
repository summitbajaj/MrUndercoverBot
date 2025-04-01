from models.game import Game
from models.enums import Role

def generate_game_start_message(game: Game) -> str:
    """Generate the game start message with player list"""
    player_list = "\n".join(
        [f"- {player.display_name()}" for player in game.players.values()]
    )
    
    return (
        f"Game started with {len(game.players)} players!\n\n"
        f"Players:\n{player_list}\n\n"
        f"I've sent each player their soccer player via private message.\n"
        f"First player to describe: {game.players[game.get_current_player_id()].display_name()}"
    )

def generate_role_message(role: Role, word: str) -> str:
    """Generate the private message to send to a player about their role."""
    if role == Role.CIVILIAN or role == Role.UNDERCOVER:
        # Don't reveal if they're civilian or undercover!
        return (
            f"Your soccer player is: *{word}*\n\n"
            f"Describe this player without naming them directly. Listen to others' "
            f"descriptions carefully to determine who might have a different player."
        )
    else:  # Mr. White
        return (
            f"You are *MR. WHITE*\n\n"
            f"You don't know any soccer player's name!\n\n"
            f"Listen carefully to others and try to figure out the Civilians' player. "
            f"If you're caught, you'll have one chance to guess the correct player name to win."
        )

def generate_player_turn_message(game: Game, user_id: int, description: str = "") -> str:
    """Generate message for a player's turn."""
    player = game.players[user_id]
    
    if description:
        return f"{player.display_name()} described: \"{description}\""
    else:
        return f"{player.display_name()} has finished their turn without a description."

def generate_next_player_message(game: Game, next_player_id: int) -> str:
    """Generate message announcing the next player."""
    return f"Next player: {game.players[next_player_id].display_name()}"

def generate_voting_phase_message() -> str:
    """Generate message for voting phase."""
    return (
        "All players have spoken! Time to vote.\n"
        "Use /vote @username to vote who you think is the Undercover or Mr. White."
    )

def generate_elimination_message(game: Game, eliminated_id: int) -> str:
    """Generate message when a player is eliminated."""
    eliminated_player = game.players[eliminated_id]
    return (
        f"{eliminated_player.display_name()} has been eliminated!\n"
        f"They were a {eliminated_player.role.value.upper()}"
    )

def generate_mr_white_guessing_message(game: Game, eliminated_id: int) -> str:
    """Generate message when Mr. White gets to guess."""
    eliminated_player = game.players[eliminated_id]
    return (
        f"{eliminated_player.display_name()} was Mr. White and gets one chance to guess!\n"
        f"I've sent them a private message to make their guess."
    )

def generate_mr_white_private_message() -> str:
    """Generate private message to Mr. White for guessing."""
    return "You've been caught as Mr. White! What do you think the Civilians' soccer player is? Reply with just the name."

def generate_game_over_message(game: Game, winner: Role) -> str:
    """Generate game over message with results."""
    # Count final statistics
    civilians = [p for p in game.players.values() if p.role == Role.CIVILIAN]
    undercovers = [p for p in game.players.values() if p.role == Role.UNDERCOVER]
    mr_whites = [p for p in game.players.values() if p.role == Role.MR_WHITE]
    
    alive_civilians = [p for p in civilians if not p.eliminated]
    alive_undercovers = [p for p in undercovers if not p.eliminated]
    alive_mr_whites = [p for p in mr_whites if not p.eliminated]
    
    # Create winner message with explanation
    if winner == Role.CIVILIAN:
        winner_message = "🎉 The CIVILIANS have won! 🎉\nThey successfully eliminated all Undercover and Mr. White players."
    elif winner == Role.UNDERCOVER:
        winner_message = "🎭 The UNDERCOVER players have won! 🎭\nThey successfully infiltrated and outnumbered the Civilians."
    else:  # Mr. White
        winner_message = "🃏 MR. WHITE has won with a correct guess! 🃏\nThey successfully identified the Civilians' soccer player."
    
    # Create game summary - Escape any Markdown characters
    civilian_word = game.civilian_word.replace("*", "\\*").replace("_", "\\_") if game.civilian_word else "None"
    undercover_word = game.undercover_word.replace("*", "\\*").replace("_", "\\_") if game.undercover_word else "None"
    
    summary = (
        f"{winner_message}\n\n"
        f"Game Summary:\n"
        f"- Civilians ({len(alive_civilians)}/{len(civilians)} remaining): "
        f"Soccer player was {civilian_word}\n"
        f"- Undercover ({len(alive_undercovers)}/{len(undercovers)} remaining): "
        f"Soccer player was {undercover_word}\n"
        f"- Mr. White ({len(alive_mr_whites)}/{len(mr_whites)} remaining)\n\n"
        f"Player Roles:\n"
    )
    
    # Add all player roles
    for player in game.players.values():
        status = "ALIVE" if not player.eliminated else "eliminated"
        summary += f"- {player.display_name()}: {player.role.value.upper()} ({status})\n"
    
    summary += "\nGame over! Start a new game with /newgame"
    
    return summary

def generate_clues_message(game: Game) -> str:
    """Generate a message with all player descriptions from the current and previous rounds."""
    descriptions = []
    
    # Group descriptions by players
    player_descriptions = {}
    for user_id, player in game.players.items():
        if player.description:
            if player.display_name() not in player_descriptions:
                player_descriptions[player.display_name()] = []
            
            status_prefix = "❌ " if player.eliminated else ""
            player_descriptions[player.display_name()].append(
                f"{status_prefix}\"{player.description}\""
            )
    
    # Format the descriptions by player
    for player_name, player_descs in player_descriptions.items():
        descriptions.append(f"{player_name}: {' | '.join(player_descs)}")
    
    if not descriptions:
        return "No descriptions available yet."
        
    # Format the descriptions
    return f"📝 All player descriptions up to Round {game.round_number}:\n\n" + "\n".join(descriptions)