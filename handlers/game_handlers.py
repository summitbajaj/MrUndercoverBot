import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from models.enums import GameState, Role
from utils.message_utils import (
    generate_player_turn_message, generate_next_player_message,
    generate_voting_phase_message, generate_elimination_message,
    generate_mr_white_guessing_message, generate_mr_white_private_message
)
from handlers.command_handlers import game_over
from config import games, active_mr_white_guesses

logger = logging.getLogger(__name__)

async def done_turn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark current player as done with their turn and store their description."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    # Extract description text (everything after /done)
    description = ""
    if " " in message_text:
        description = message_text[message_text.index(" ")+1:].strip()

    if chat_id not in games:
        await update.message.reply_text("No game in progress.")
        return

    game = games[chat_id]
    if game.state != GameState.PLAYING:
        await update.message.reply_text("Game is not in the playing phase.")
        return

    current_player_id = game.get_current_player_id()
    if current_player_id != user_id:
        await update.message.reply_text("It's not your turn.")
        return
        
    # Store the player's description if provided
    if description:
        game.players[user_id].description = description
    
    # Generate response text based on whether description was provided
    response_text = generate_player_turn_message(game, user_id, description)

    # Mark current player as having spoken
    game.players[user_id].has_spoken = True
    
    # Check if this was the last player to speak
    all_spoken = True
    for player_id, player in game.players.items():
        if not player.eliminated and not player.has_spoken:
            all_spoken = False
            break
    
    # If all players have spoken, move to voting phase
    if all_spoken:
        game.state = GameState.VOTING
        voting_message = generate_voting_phase_message()
        await update.message.reply_text(
            f"{response_text}\n\n"
            f"🗳️ {voting_message}\n\n"
            f"Use /vote @username to vote for who you think is the Undercover or Mr. White."
        )
        return
    
    # Otherwise, move to next player
    next_player_id = game.next_turn()
    if next_player_id:
        # Continue to next player
        next_player_message = generate_next_player_message(game, next_player_id)
        await update.message.reply_text(f"{response_text}\n\n{next_player_message}")
    else:
        # This is a fallback in case next_turn returns None but we haven't detected all_spoken
        # (This shouldn't happen with the fixed logic, but it's a safety measure)
        game.state = GameState.VOTING
        voting_message = generate_voting_phase_message()
        await update.message.reply_text(
            f"{response_text}\n\n"
            f"🗳️ {voting_message}\n\n"
            f"Use /vote @username to vote for who you think is the Undercover or Mr. White."
        )


async def next_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force move to next player (for in-person games)."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text("No game in progress.")
        return

    game = games[chat_id]
    if game.state != GameState.PLAYING:
        await update.message.reply_text("Game is not in the playing phase.")
        return

    if game.creator_id != user_id:
        # Check if user is admin
        try:
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            is_admin = chat_member.status in ["creator", "administrator"]
            if not is_admin:
                await update.message.reply_text("Only the game creator or a group admin can force next player.")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("Only the game creator can force next player.")
            return

    current_player_id = game.get_current_player_id()
    response_text = generate_player_turn_message(game, current_player_id)
    
    next_player_id = game.next_turn()
    if next_player_id:
        next_player_message = generate_next_player_message(game, next_player_id)
        await update.message.reply_text(f"{response_text}\n\n{next_player_message}")
    else:
        # Round over, move to voting
        voting_message = generate_voting_phase_message()
        await update.message.reply_text(f"{response_text}\n\n{voting_message}")


async def all_spoken(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Skip to voting phase if all players have spoken or by creator force."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text("No game in progress.")
        return

    game = games[chat_id]
    if game.state != GameState.PLAYING:
        await update.message.reply_text("Game is not in the playing phase.")
        return

    # Check if user is creator or admin
    if game.creator_id != user_id:
        try:
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            is_admin = chat_member.status in ["creator", "administrator"]
            if not is_admin:
                await update.message.reply_text("Only the game creator or a group admin can force voting phase.")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("Only the game creator can force voting phase.")
            return

    # Force move to voting phase
    game.state = GameState.VOTING
    
    await update.message.reply_text(
        "Moving to voting phase!\n"
        "Use /vote @username to vote who you think is the Undercover or Mr. White."
    )


async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vote to eliminate a player."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text("No game in progress.")
        return

    game = games[chat_id]
    if game.state != GameState.VOTING:
        await update.message.reply_text("It's not voting time yet.")
        return

    if user_id not in game.players or game.players[user_id].eliminated:
        await update.message.reply_text(
            "You can't vote because you're not in the game or have been eliminated."
        )
        return

    if game.players[user_id].has_voted:
        await update.message.reply_text("You've already voted this round.")
        return

    # Parse the username from the command
    if not context.args:
        await update.message.reply_text("Please specify who to vote for: /vote @username")
        return

    target_username = context.args[0].lstrip('@')
    target_id = None
    
    # Find the player by username
    for pid, player in game.players.items():
        if player.username == target_username:
            target_id = pid
            break

    if not target_id:
        await update.message.reply_text(f"Could not find player with username @{target_username}")
        return

    if game.players[target_id].eliminated:
        await update.message.reply_text("This player has already been eliminated.")
        return

    # Cast vote
    if game.cast_vote(user_id, target_id):
        await update.message.reply_text(
            f"{game.players[user_id].display_name()} voted for {game.players[target_id].display_name()}"
        )

        # Check if all players have voted
        if game.all_players_voted():
            eliminated_id = game.resolve_votes()
            
            if eliminated_id:
                eliminated_player = game.players[eliminated_id]
                await update.message.reply_text(generate_elimination_message(game, eliminated_id))
                
                if game.state == GameState.MR_WHITE_GUESSING:
                    # Mr. White gets one guess
                    active_mr_white_guesses[eliminated_id] = chat_id
                    
                    await update.message.reply_text(generate_mr_white_guessing_message(game, eliminated_id))
                    
                    try:
                        await context.bot.send_message(
                            chat_id=eliminated_id,
                            text=generate_mr_white_private_message()
                        )
                    except Exception as e:
                        logger.error(f"Failed to send PM to Mr. White {eliminated_id}: {e}")
                        await update.message.reply_text(
                            f"⚠️ Could not send a private message to {eliminated_player.display_name()}. "
                            f"Make sure you've started a chat with me first!"
                        )
                else:
                    # Check win conditions
                    winner = game.check_win_condition()
                    if winner:
                        await game_over(update, context, winner)
                    else:
                        # Display next player - IMPROVED TRANSITION MESSAGING
                        next_player_id = game.get_current_player_id()
                        await update.message.reply_text(
                            f"📢 Round {game.round_number} begins!\n\n"
                            f"Players should take turns describing their soccer player without naming them.\n"
                            f"First player: {game.players[next_player_id].display_name()}\n\n"
                            f"When finished with your turn, use /done followed by your description."
                        )
            else:
                # No elimination (tie with 'none' tiebreaker)
                await update.message.reply_text(
                    "Voting resulted in a tie! No player is eliminated this round."
                )
                
                # Reset for next round
                game._prepare_next_round()
                
                # Start next round - IMPROVED TRANSITION MESSAGING
                next_player_id = game.get_current_player_id()
                await update.message.reply_text(
                    f"📢 Round {game.round_number} begins!\n\n"
                    f"Players should take turns describing their soccer player without naming them.\n"
                    f"First player: {game.players[next_player_id].display_name()}\n\n"
                    f"When finished with your turn, use /done followed by your description."
                )
    else:
        await update.message.reply_text(
            "Failed to register vote. Make sure both you and the target are valid players."
        )