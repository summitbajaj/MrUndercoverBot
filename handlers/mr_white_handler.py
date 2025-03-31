import logging
from telegram import Update
from telegram.ext import ContextTypes

from models.enums import GameState
from handlers.command_handlers import game_over
from config import games, active_mr_white_guesses

logger = logging.getLogger(__name__)

async def handle_mr_white_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process Mr. White's guess for the civilian word."""
    user_id = update.effective_user.id
    
    # Check if this user is an active Mr. White making a guess
    if user_id not in active_mr_white_guesses:
        return
    
    chat_id = active_mr_white_guesses[user_id]
    if chat_id not in games:
        # Game no longer exists
        del active_mr_white_guesses[user_id]
        await update.message.reply_text(
            "The game you were playing no longer exists."
        )
        return
    
    game = games[chat_id]
    if game.state != GameState.MR_WHITE_GUESSING:
        # Not in guessing state anymore
        del active_mr_white_guesses[user_id]
        await update.message.reply_text(
            "Your guess is no longer valid. The game state has changed."
        )
        return
    
    # Process the guess
    guess = update.message.text.strip()
    correct = game.check_mr_white_guess(guess)
    
    # Send result to Mr. White
    await update.message.reply_text(
        f"Your guess: {guess}\n"
        f"{'Correct! You win!' if correct else 'Wrong! You lose!'}"
    )
    
    # Send result to the group
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{game.players[user_id].display_name()} guessed: {guess}\n"
              f"{'Correct! Mr. White wins the game!' if correct else 'Wrong! The game continues.'}"
    )
    
    # Clean up
    del active_mr_white_guesses[user_id]
    
    # Handle game state
    if correct:
        from models.enums import Role
        await game_over(None, context, Role.MR_WHITE, chat_id)
    else:
        game.reset_after_mr_white_guess(False)
        
        # Check if game should continue
        winner = game.check_win_condition()
        if winner:
            await game_over(None, context, winner, chat_id)
        else:
            # Continue with next player
            next_player_id = game.get_current_player_id()
            if next_player_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Round {game.round_number} begins!\n"
                          f"First player: {game.players[next_player_id].display_name()}"
                )