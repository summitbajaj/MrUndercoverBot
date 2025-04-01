import logging
from typing import Dict, List, Optional, Set, Tuple, Union

from telegram import Update
from telegram.ext import ContextTypes

from models.enums import Role, GameState
from models.game import Game
from utils.settings import save_chat_settings, get_chat_settings, validate_game_settings
from utils.message_utils import (
    generate_game_start_message, generate_role_message, 
    generate_clues_message, generate_game_over_message
)
from config import games, active_mr_white_guesses, logger, SOCCER_PLAYER_PAIRS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "Welcome to Soccer Mr. Undercover Bot! Use /help to see available commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "Soccer Mr. Undercover Bot Commands:\n\n"
        "/newgame - Create a new game\n"
        "/join - Join the current game\n"
        "/start - Start the game (creator only)\n"
        "/done [description] - Finish your turn with an optional description\n"
        "/next - Force next player (in-person games)\n"
        "/allspoken - Skip to voting phase\n"
        "/vote @username - Vote to eliminate a player\n"
        "/clues - Show all player descriptions from the current round\n"
        "/settings - Configure game options\n"
        "/end or /terminate - End the current game\n"
        "/help - Show this help message\n\n"
        "Game Rules:\n"
        "1. Each player is assigned a role: Civilian, Undercover, or Mr. White\n"
        "2. Civilians receive the same soccer player name\n"
        "3. Undercover players receive a similar but different player name\n"
        "4. Mr. White doesn't receive any name\n"
        "5. Players take turns describing their player without naming them\n"
        "6. After all players have spoken, voting begins\n"
        "7. The player with most votes is eliminated\n"
        "8. If Mr. White is eliminated, they get one guess\n"
        "9. Game continues until someone wins!"
    )
    await update.message.reply_text(help_text)


async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new game."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    if chat_id in games:
        await update.message.reply_text(
            "A game is already in progress. Join with /join or wait for it to end."
        )
        return

    # Create new game
    games[chat_id] = Game(chat_id, user_id)
    
    # Apply saved settings from previous games
    saved_settings = get_chat_settings(chat_id)
    games[chat_id].settings = saved_settings
    
    games[chat_id].add_player(user_id, username, first_name)

    # Show current settings
    settings_info = (
        f"Game created with the following settings:\n"
        f"- Mr. White Start: {saved_settings['mr_white_start']}\n"
        f"- Tiebreaker: {saved_settings['tiebreaker']}\n"
        f"- Role Distribution: "
    )
    
    if (saved_settings['civilian_count'] == 0 and 
        saved_settings['undercover_count'] == 0 and 
        saved_settings['mr_white_count'] == 0):
        settings_info += "Automatic based on player count"
    else:
        settings_info += (
            f"Manual ({saved_settings['civilian_count']} Civilians, "
            f"{saved_settings['undercover_count']} Undercover, "
            f"{saved_settings['mr_white_count']} Mr. White)"
        )

    await update.message.reply_text(
        f"New game created by {first_name}! Join with /join\n\n{settings_info}\n\n"
        f"You can change settings with /settings before starting the game."
    )


async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Join an existing game."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    if chat_id not in games:
        await update.message.reply_text(
            "No game in progress. Create one with /newgame"
        )
        return

    game = games[chat_id]
    if game.state != GameState.WAITING_FOR_PLAYERS:
        await update.message.reply_text(
            "Game already started. Wait for it to end."
        )
        return

    if game.add_player(user_id, username, first_name):
        await update.message.reply_text(
            f"{first_name} joined the game! ({len(game.players)} players)"
        )
    else:
        await update.message.reply_text(
            "You've already joined this game."
        )


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the game after players have joined."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text(
            "No game in progress. Create one with /newgame"
        )
        return

    game = games[chat_id]
    if game.creator_id != user_id:
        await update.message.reply_text(
            "Only the game creator can start the game."
        )
        return

    if game.state != GameState.WAITING_FOR_PLAYERS:
        await update.message.reply_text(
            "Game already started."
        )
        return

    # Check minimum player count
    current_players = len(game.players)
    if current_players < 3:
        await update.message.reply_text(
            f"⚠️ Need at least 3 players to start. Currently: {current_players} player{'s' if current_players != 1 else ''}.\n\n"
            f"Please wait for more players to join with /join"
        )
        return
    
    # Validate game settings if manually configured
    if (game.settings["civilian_count"] > 0 or 
        game.settings["undercover_count"] > 0 or 
        game.settings["mr_white_count"] > 0):
        
        validation_errors = validate_game_settings(game.settings, current_players)
        if validation_errors:
            error_msg = "⚠️ Cannot start game due to setting errors:\n"
            for error in validation_errors.values():
                error_msg += f"- {error}\n"
            error_msg += "\nPlease adjust settings with /settings or use automatic distribution (set all counts to 0)"
            
            await update.message.reply_text(error_msg)
            return
        
    if not SOCCER_PLAYER_PAIRS:
        await update.message.reply_text(
            "Error: No soccer player pairs available. Cannot start game."
        )
        return
        
    if not game.start_game():
        await update.message.reply_text(
            "Failed to start the game. Make sure there are enough players."
        )
        return

    # Send game started message to group
    await update.message.reply_text(generate_game_start_message(game))

    # Send private messages to each player with their role and word
    for player_id, player in game.players.items():
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=generate_role_message(player.role, player.word),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send PM to {player_id}: {e}")
            await update.message.reply_text(
                f"⚠️ Could not send a private message to {player.display_name()}. "
                f"Make sure you've started a chat with me (@YourBotUsername) first!"
            )


async def show_clues(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all descriptions from the current round."""
    chat_id = update.effective_chat.id
    
    if chat_id not in games:
        await update.message.reply_text("No game in progress.")
        return
        
    game = games[chat_id]
    
    if game.state == GameState.WAITING_FOR_PLAYERS:
        await update.message.reply_text("Game hasn't started yet.")
        return
        
    await update.message.reply_text(generate_clues_message(game))


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configure game settings."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text(
            "No game in progress. Create one with /newgame"
        )
        return

    game = games[chat_id]
    if game.creator_id != user_id:
        await update.message.reply_text(
            "Only the game creator can change settings."
        )
        return

    if game.state != GameState.WAITING_FOR_PLAYERS:
        await update.message.reply_text(
            "Settings can only be changed before the game starts."
        )
        return

    # Parse arguments
    if not context.args or len(context.args) < 2:
        # Show current settings
        settings_text = (
            "Current Settings:\n"
            f"- Mr. White Start: {game.settings['mr_white_start']}\n"
            f"- Tiebreaker: {game.settings['tiebreaker']}\n"
            f"- Civilian Count: {game.settings['civilian_count']} (0 = auto)\n"
            f"- Undercover Count: {game.settings['undercover_count']} (0 = auto)\n"
            f"- Mr. White Count: {game.settings['mr_white_count']} (0 = auto)\n\n"
            "Change settings with: /settings [option] [value]\n"
            "Options:\n"
            "- mrwhitestart [on/off]\n"
            "- tiebreaker [random/none]\n"
            "- civilians [number]\n"
            "- undercover [number]\n"
            "- mrwhite [number]"
        )
        await update.message.reply_text(settings_text)
        return

    option = context.args[0].lower()
    value = context.args[1].lower()
    setting_changed = False

    if option == "mrwhitestart":
        if value in ["on", "true", "yes", "1"]:
            game.settings["mr_white_start"] = True
            await update.message.reply_text("Mr. White can now be the first player.")
            setting_changed = True
        elif value in ["off", "false", "no", "0"]:
            game.settings["mr_white_start"] = False
            await update.message.reply_text("Mr. White can't be the first player.")
            setting_changed = True
        else:
            await update.message.reply_text("Invalid value. Use 'on' or 'off'.")
    
    elif option == "tiebreaker":
        if value == "random":
            game.settings["tiebreaker"] = "random"
            await update.message.reply_text("Ties will be broken randomly.")
            setting_changed = True
        elif value == "none":
            game.settings["tiebreaker"] = "none"
            await update.message.reply_text("Ties will result in no elimination.")
            setting_changed = True
        else:
            await update.message.reply_text("Invalid value. Use 'random' or 'none'.")
    
    elif option == "civilians":
        try:
            count = int(value)
            if count >= 0:
                game.settings["civilian_count"] = count
                await update.message.reply_text(f"Civilian count set to {count} (0 = auto).")
                setting_changed = True
            else:
                await update.message.reply_text("Count must be non-negative.")
        except ValueError:
            await update.message.reply_text("Invalid value. Use a number.")
    
    elif option == "undercover":
        try:
            count = int(value)
            if count >= 0:
                game.settings["undercover_count"] = count
                await update.message.reply_text(f"Undercover count set to {count} (0 = auto).")
                setting_changed = True
            else:
                await update.message.reply_text("Count must be non-negative.")
        except ValueError:
            await update.message.reply_text("Invalid value. Use a number.")
    
    elif option == "mrwhite":
        try:
            count = int(value)
            if count >= 0:
                game.settings["mr_white_count"] = count
                await update.message.reply_text(f"Mr. White count set to {count} (0 = auto).")
                setting_changed = True
            else:
                await update.message.reply_text("Count must be non-negative.")
        except ValueError:
            await update.message.reply_text("Invalid value. Use a number.")
    
    else:
        await update.message.reply_text(
            "Unknown option. Available options: mrwhitestart, tiebreaker, civilians, undercover, mrwhite"
        )
    
    # Save settings for future games in this chat if changed
    if setting_changed:
        save_chat_settings(chat_id, game.settings)
        
        # Validate with the current number of players
        validation_errors = validate_game_settings(game.settings, len(game.players))
        if validation_errors:
            warning_msg = "⚠️ Warning: Current settings may cause issues:\n"
            for error in validation_errors.values():
                warning_msg += f"- {error}\n"
            warning_msg += "\nThese will be checked again when starting the game."
            
            await update.message.reply_text(warning_msg)


async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """End the current game session with improved error handling."""
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if chat_id not in games:
            await update.message.reply_text(
                "No game in progress to end."
            )
            return

        game = games[chat_id]
        
        # Only the game creator or an admin can end the game
        try:
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            is_admin = chat_member.status in ["creator", "administrator"]
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            is_admin = False
        
        if game.creator_id != user_id and not is_admin:
            await update.message.reply_text(
                "Only the game creator or a group admin can end the game."
            )
            return
        
        # Clean up any active Mr. White guesses for this game
        mr_white_users = [uid for uid, cid in active_mr_white_guesses.items() if cid == chat_id]
        for uid in mr_white_users:
            if uid in active_mr_white_guesses:
                del active_mr_white_guesses[uid]
        
        # Show game summary if the game had started
        if game.state != GameState.WAITING_FOR_PLAYERS:
            # Create game summary
            summary = "🛑 Game terminated!\n\n"
            
            if game.civilian_word and game.undercover_word:
                # Escape Markdown characters in player names
                civilian_word = game.civilian_word.replace("*", "\\*").replace("_", "\\_")
                undercover_word = game.undercover_word.replace("*", "\\*").replace("_", "\\_")
                summary += f"The words were:\n- Civilians: {civilian_word}\n- Undercover: {undercover_word}\n\n"
            
            summary += "Player Roles:\n"
            for player in game.players.values():
                if player.role:
                    summary += f"- {player.display_name()}: {player.role.value.upper()}\n"
                else:
                    summary += f"- {player.display_name()}: (No role assigned)\n"
            
            # Send without Markdown parsing to avoid errors
            await update.message.reply_text(summary)
        else:
            # Game was created but never started
            if len(game.players) > 0:
                player_list = "\n".join([f"- {player.display_name()}" for player in game.players.values()])
                await update.message.reply_text(
                    f"🛑 Game cancelled before it started.\n\n"
                    f"Players who had joined:\n{player_list}"
                )
            else:
                await update.message.reply_text("Game has been cancelled.")
        
        # Remove the game
        del games[chat_id]
        
    except Exception as e:
        logger.error(f"Error ending game: {e}")
        await update.message.reply_text(
            "An error occurred while ending the game. The game has been terminated."
        )
        # Try to clean up even if there was an error
        if 'chat_id' in locals() and chat_id in games:
            del games[chat_id]


async def game_over(
    update: Optional[Update], 
    context: ContextTypes.DEFAULT_TYPE, 
    winner: Role,
    chat_id: Optional[int] = None
) -> None:
    """Handle game over condition."""
    try:
        if not chat_id and update:
            chat_id = update.effective_chat.id
        
        if not chat_id or chat_id not in games:
            return
        
        game = games[chat_id]
        game.state = GameState.GAME_OVER
        
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
        
        # Send final message without parse_mode to avoid Markdown errors
        await context.bot.send_message(
            chat_id=chat_id,
            text=summary
        )
        
        # Remove game from active games
        del games[chat_id]
        
    except Exception as e:
        logger.error(f"Error in game_over: {e}")
        # Try to clean up anyway
        if chat_id and chat_id in games:
            del games[chat_id]
            await context.bot.send_message(
                chat_id=chat_id,
                text="Game over! The game has ended."
            )


async def setup_bot_commands(application):
    """Set up descriptive commands that appear when typing /"""
    commands = [
        ("newgame", "Create a new game in this chat"),
        ("join", "Join the current game"),
        ("start", "Start the game after players have joined"),
        ("done", "Finish your turn with an optional description"),
        ("next", "Move to the next player (admin only)"),
        ("allspoken", "Skip to voting phase (admin only)"),
        ("vote", "Vote to eliminate a player (format: /vote @username)"),
        ("clues", "Show descriptions from the current round"),
        ("settings", "Configure game options"),
        ("end", "End the current game"),
        ("help", "Show available commands and game rules")
    ]
    
    # Set commands for the bot
    await application.bot.set_my_commands(commands)