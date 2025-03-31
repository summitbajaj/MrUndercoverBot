#!/usr/bin/env python
"""
Soccer Mr. Undercover Telegram Bot
"""

import os
import logging
from dotenv import load_dotenv

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import logger
from handlers.command_handlers import (
    start, help_command, new_game, join_game, 
    start_game, settings, end_game, setup_bot_commands,
    show_clues
)
from handlers.game_handlers import (
    done_turn, next_player, all_spoken, vote
)
from handlers.mr_white_handler import handle_mr_white_guess

def main() -> None:
    """Start the bot."""
    # Load environment variables
    load_dotenv()
    
    # Get the bot token from environment variable
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
        print("Please create a .env file with TELEGRAM_BOT_TOKEN=your_token or set it as an environment variable.")
        return
    
    # Create the Application and pass it your bot's token
    application = Application.builder().token(token).build()

    # Set up descriptive commands
    application.post_init = setup_bot_commands

    # Command handlers - Note: The order matters!
    # Add the group-specific start command first (more specific)
    application.add_handler(CommandHandler("start", start_game, filters=filters.ChatType.GROUPS))
    # Add the general start command after (less specific)
    application.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    
    # Other commands
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("newgame", new_game))
    application.add_handler(CommandHandler("join", join_game))
    application.add_handler(CommandHandler("done", done_turn))
    application.add_handler(CommandHandler("next", next_player))
    application.add_handler(CommandHandler("allspoken", all_spoken))
    application.add_handler(CommandHandler("vote", vote))
    application.add_handler(CommandHandler("clues", show_clues))
    application.add_handler(CommandHandler("settings", settings))
    
    # Add the end game command
    application.add_handler(CommandHandler("end", end_game))
    application.add_handler(CommandHandler("terminate", end_game))
    
    # Handle Mr. White guesses via private message
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_mr_white_guess
        )
    )

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot starting...")
    application.run_polling()


if __name__ == "__main__":
    main()