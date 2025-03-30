import logging
import random
import json
import os
from dotenv import load_dotenv
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load soccer player pairs
try:
    with open("soccer_player_pairs.json", "r") as f:
        SOCCER_PLAYER_PAIRS = json.load(f)
except FileNotFoundError:
    logger.error("soccer_player_pairs.json not found! Please create this file.")
    logger.info("You can use the soccer_player_pairs.json in the repository as a template.")
    SOCCER_PLAYER_PAIRS = []  # Empty list as fallback


class Role(Enum):
    CIVILIAN = "civilian"
    UNDERCOVER = "undercover"
    MR_WHITE = "mr_white"


class GameState(Enum):
    WAITING_FOR_PLAYERS = "waiting_for_players"
    PLAYING = "playing"
    VOTING = "voting"
    GAME_OVER = "game_over"
    MR_WHITE_GUESSING = "mr_white_guessing"


class Player:
    def __init__(self, user_id: int, username: str, first_name: str):
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.role: Optional[Role] = None
        self.word: Optional[str] = None
        self.has_spoken: bool = False
        self.has_voted: bool = False
        self.vote_target: Optional[int] = None
        self.eliminated: bool = False

    def display_name(self) -> str:
        """Returns the best available name for display"""
        if self.username:
            return f"@{self.username}"
        return self.first_name


class Game:
    def __init__(self, chat_id: int, creator_id: int):
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.state = GameState.WAITING_FOR_PLAYERS
        self.players: Dict[int, Player] = {}
        self.turn_order: List[int] = []
        self.current_turn_idx: int = 0
        self.civilian_word: Optional[str] = None
        self.undercover_word: Optional[str] = None
        self.round_number: int = 0
        self.settings = {
            "mr_white_start": False,
            "tiebreaker": "random",  # 'random' or 'none'
            "civilian_count": 0,
            "undercover_count": 0,
            "mr_white_count": 0,
        }

    def add_player(self, user_id: int, username: str, first_name: str) -> bool:
        """Add a player to the game if not already in"""
        if user_id in self.players:
            return False
        self.players[user_id] = Player(user_id, username, first_name)
        return True

    def remove_player(self, user_id: int) -> bool:
        """Remove a player from the game"""
        if user_id not in self.players:
            return False
        del self.players[user_id]
        return True

    def start_game(self) -> bool:
        """Set up and start the game"""
        if len(self.players) < 3:
            return False  # Need at least 3 players

        # Make sure we have player pairs
        if not SOCCER_PLAYER_PAIRS:
            return False

        # Determine role counts based on player count
        total_players = len(self.players)
        # Auto-adjust role counts based on total players
        if self.settings["civilian_count"] == 0:
            # Special case for exactly 3 players
            if total_players == 3:
                self.settings["civilian_count"] = 2
                # Randomly choose between having 1 Undercover or 1 Mr. White
                if random.choice([True, False]):
                    self.settings["undercover_count"] = 1
                    self.settings["mr_white_count"] = 0
                else:
                    self.settings["undercover_count"] = 0
                    self.settings["mr_white_count"] = 1
            # Default role distribution for other player counts
            elif total_players == 4:
                self.settings["civilian_count"] = 2
                self.settings["undercover_count"] = 1
                self.settings["mr_white_count"] = 1
            elif total_players <= 6:
                self.settings["civilian_count"] = total_players - 3
                self.settings["undercover_count"] = 2
                self.settings["mr_white_count"] = 1
            else:
                self.settings["civilian_count"] = total_players - 4
                self.settings["undercover_count"] = 2
                self.settings["mr_white_count"] = 2

        # Pick a random pair of soccer players
        player_pair = random.choice(SOCCER_PLAYER_PAIRS)
        self.civilian_word = player_pair["civilian"]
        self.undercover_word = player_pair["undercover"]

        # Assign roles randomly
        player_ids = list(self.players.keys())
        random.shuffle(player_ids)

        # Assign civilians
        for i in range(self.settings["civilian_count"]):
            if i < len(player_ids):
                self.players[player_ids[i]].role = Role.CIVILIAN
                self.players[player_ids[i]].word = self.civilian_word

        # Assign undercover
        for i in range(self.settings["civilian_count"], self.settings["civilian_count"] + self.settings["undercover_count"]):
            if i < len(player_ids):
                self.players[player_ids[i]].role = Role.UNDERCOVER
                self.players[player_ids[i]].word = self.undercover_word

        # Assign Mr. White
        for i in range(self.settings["civilian_count"] + self.settings["undercover_count"], total_players):
            if i < len(player_ids):
                self.players[player_ids[i]].role = Role.MR_WHITE
                self.players[player_ids[i]].word = None

        # Set turn order randomly
        self.turn_order = player_ids.copy()
        random.shuffle(self.turn_order)

        # Check if we need to reorder due to Mr. White start setting
        if not self.settings["mr_white_start"]:
            # Make sure first player is not Mr. White
            first_player_idx = 0
            while (
                first_player_idx < len(self.turn_order) and 
                self.players[self.turn_order[first_player_idx]].role == Role.MR_WHITE
            ):
                first_player_idx += 1
            
            if first_player_idx < len(self.turn_order) and first_player_idx > 0:
                # Swap first non-Mr. White player to the start
                self.turn_order[0], self.turn_order[first_player_idx] = self.turn_order[first_player_idx], self.turn_order[0]

        self.current_turn_idx = 0
        self.state = GameState.PLAYING
        self.round_number = 1
        return True

    def next_turn(self) -> Optional[int]:
        """Move to the next player's turn, return their user_id or None if round is over"""
        if self.state != GameState.PLAYING:
            return None

        # Mark current player as having spoken
        current_player_id = self.get_current_player_id()
        if current_player_id:
            self.players[current_player_id].has_spoken = True

        # Find next non-eliminated player
        original_idx = self.current_turn_idx
        while True:
            self.current_turn_idx = (self.current_turn_idx + 1) % len(self.turn_order)
            next_player_id = self.turn_order[self.current_turn_idx]
            if not self.players[next_player_id].eliminated:
                # If we've gone full circle, everyone has spoken
                if self.current_turn_idx == original_idx:
                    self.state = GameState.VOTING
                    return None
                # Found next active player
                return next_player_id
            # If we've gone full circle and everyone is eliminated, game is over
            if self.current_turn_idx == original_idx:
                self.state = GameState.GAME_OVER
                return None

    def get_current_player_id(self) -> Optional[int]:
        """Get the current player's user_id"""
        if self.state != GameState.PLAYING or len(self.turn_order) == 0:
            return None
        current_player_id = self.turn_order[self.current_turn_idx]
        if self.players[current_player_id].eliminated:
            return self.next_turn()
        return current_player_id

    def all_players_spoken(self) -> bool:
        """Check if all non-eliminated players have spoken"""
        for player_id, player in self.players.items():
            if not player.eliminated and not player.has_spoken:
                return False
        return True

    def cast_vote(self, voter_id: int, target_id: int) -> bool:
        """Cast a vote to eliminate a player"""
        if (
            self.state != GameState.VOTING
            or voter_id not in self.players
            or target_id not in self.players
            or self.players[voter_id].eliminated
            or self.players[target_id].eliminated
            or self.players[voter_id].has_voted
        ):
            return False

        self.players[voter_id].has_voted = True
        self.players[voter_id].vote_target = target_id
        return True

    def all_players_voted(self) -> bool:
        """Check if all non-eliminated players have voted"""
        for player_id, player in self.players.items():
            if not player.eliminated and not player.has_voted:
                return False
        return True

    def resolve_votes(self) -> Optional[int]:
        """Resolve votes and eliminate a player, return their user_id or None if tied with 'none' tiebreaker"""
        if self.state != GameState.VOTING:
            return None

        vote_count: Dict[int, int] = {}
        for player_id, player in self.players.items():
            if not player.eliminated and player.has_voted and player.vote_target is not None:
                vote_count[player.vote_target] = vote_count.get(player.vote_target, 0) + 1

        # Find the player(s) with the most votes
        max_votes = 0
        max_vote_players: List[int] = []
        for player_id, votes in vote_count.items():
            if votes > max_votes:
                max_votes = votes
                max_vote_players = [player_id]
            elif votes == max_votes:
                max_vote_players.append(player_id)

        # No votes cast
        if not max_vote_players:
            return None

        # Handle ties
        eliminated_player_id = None
        if len(max_vote_players) == 1:
            eliminated_player_id = max_vote_players[0]
        elif self.settings["tiebreaker"] == "random":
            eliminated_player_id = random.choice(max_vote_players)
        # else tiebreaker is "none", no elimination

        # Eliminate the player
        if eliminated_player_id:
            self.players[eliminated_player_id].eliminated = True
            
            # Check if Mr. White was eliminated
            if self.players[eliminated_player_id].role == Role.MR_WHITE:
                self.state = GameState.MR_WHITE_GUESSING
                return eliminated_player_id
            
            # Reset for next round
            self._prepare_next_round(eliminated_player_id)
            
        return eliminated_player_id

    def _prepare_next_round(self, last_eliminated_id: Optional[int] = None):
        """Prepare for the next round after elimination"""
        # Reset voting status
        for player in self.players.values():
            player.has_voted = False
            player.vote_target = None
            player.has_spoken = False

        # Increment round number
        self.round_number += 1

        # Set next player turn after the eliminated player
        if last_eliminated_id in self.turn_order:
            eliminated_idx = self.turn_order.index(last_eliminated_id)
            self.current_turn_idx = eliminated_idx
            # Find next non-eliminated player
            next_player = self.next_turn()
            if next_player:
                self.state = GameState.PLAYING
            else:
                # No more players or everybody has spoken
                self.check_win_condition()
        else:
            # Reset to first player if eliminated player not found
            self.current_turn_idx = 0
            next_player = self.get_current_player_id()
            if next_player:
                self.state = GameState.PLAYING
            else:
                self.check_win_condition()

    def check_mr_white_guess(self, guess: str) -> bool:
        """Check if Mr. White's guess is correct"""
        return guess.lower() == self.civilian_word.lower()

    def check_win_condition(self) -> Optional[Role]:
        """Check if any role has won the game, return the winning role or None if game continues"""
        civilian_count = 0
        undercover_count = 0
        mr_white_count = 0

        # Count remaining players by role
        for player_id, player in self.players.items():
            if not player.eliminated:
                if player.role == Role.CIVILIAN:
                    civilian_count += 1
                elif player.role == Role.UNDERCOVER:
                    undercover_count += 1
                elif player.role == Role.MR_WHITE:
                    mr_white_count += 1

        # Check win conditions
        if civilian_count == 0 or (undercover_count + mr_white_count) >= civilian_count:
            # Undercover win if they equal or outnumber civilians
            self.state = GameState.GAME_OVER
            return Role.UNDERCOVER
        elif undercover_count == 0 and mr_white_count == 0:
            # Civilians win if all others are eliminated
            self.state = GameState.GAME_OVER
            return Role.CIVILIAN

        # Game continues
        return None

    def get_alive_players(self) -> List[Player]:
        """Get a list of non-eliminated players"""
        return [p for p in self.players.values() if not p.eliminated]

    def reset_after_mr_white_guess(self, mr_white_won: bool):
        """Continue the game after Mr. White guessing"""
        if mr_white_won:
            self.state = GameState.GAME_OVER
        else:
            self._prepare_next_round()


# Game storage - maps chat_id to Game
games: Dict[int, Game] = {}

# Active Mr. White guesses - maps user_id to chat_id
active_mr_white_guesses: Dict[int, int] = {}


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
        "/done - Finish your turn (when playing)\n"
        "/next - Force next player (in-person games)\n"
        "/allspoken - Skip to voting phase\n"
        "/vote @username - Vote to eliminate a player\n"
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

    games[chat_id] = Game(chat_id, user_id)
    games[chat_id].add_player(user_id, username, first_name)

    await update.message.reply_text(
        f"New game created by {first_name}! Join with /join"
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
        
    if not SOCCER_PLAYER_PAIRS:
        await update.message.reply_text(
            "Error: No soccer player pairs available. Cannot start game."
        )
        return

    if game.start_game():
        # Send game started message to group
        player_list = "\n".join(
            [f"- {player.display_name()}" for player in game.players.values()]
        )
        await update.message.reply_text(
            f"Game started with {len(game.players)} players!\n\n"
            f"Players:\n{player_list}\n\n"
            f"I've sent each player their role and soccer player via private message.\n"
            f"First player to describe: {game.players[game.get_current_player_id()].display_name()}"
        )

        # Send private messages to each player with their role and word
        for player_id, player in game.players.items():
            if player.role == Role.CIVILIAN:
                message = (
                    f"You are a *CIVILIAN*\n\n"
                    f"Your soccer player is: *{player.word}*\n\n"
                    f"Describe this player without naming them directly. Make others "
                    f"believe you have the same player while trying to identify the Undercover."
                )
            elif player.role == Role.UNDERCOVER:
                message = (
                    f"You are *UNDERCOVER*\n\n"
                    f"Your soccer player is: *{player.word}*\n\n"
                    f"Describe this player without naming them directly. Try to blend in "
                    f"with the Civilians without revealing you have a different player."
                )
            else:  # Mr. White
                message = (
                    f"You are *MR. WHITE*\n\n"
                    f"You don't know any soccer player's name!\n\n"
                    f"Listen carefully to others and try to figure out the Civilians' player. "
                    f"If you're caught, you'll have one chance to guess the correct player name to win."
                )

            try:
                await context.bot.send_message(
                    chat_id=player_id,
                    text=message,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send PM to {player_id}: {e}")
                await update.message.reply_text(
                    f"⚠️ Could not send a private message to {player.display_name()}. "
                    f"Make sure you've started a chat with me (@YourBotUsername) first!"
                )
    else:
        await update.message.reply_text(
            "Failed to start the game. Make sure there are enough players."
        )


async def done_turn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark current player as done with their turn."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text(
            "No game in progress."
        )
        return

    game = games[chat_id]
    if game.state != GameState.PLAYING:
        await update.message.reply_text(
            "Game is not in the playing phase."
        )
        return

    current_player_id = game.get_current_player_id()
    if current_player_id != user_id:
        await update.message.reply_text(
            "It's not your turn."
        )
        return

    next_player_id = game.next_turn()
    if next_player_id:
        await update.message.reply_text(
            f"{game.players[user_id].display_name()} has finished their turn.\n\n"
            f"Next player: {game.players[next_player_id].display_name()}"
        )
    else:
        # Round over, move to voting
        await update.message.reply_text(
            f"{game.players[user_id].display_name()} has finished their turn.\n\n"
            f"All players have spoken! Time to vote.\n"
            f"Use /vote @username to vote who you think is the Undercover or Mr. White."
        )


async def next_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force move to next player (for in-person games)."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text(
            "No game in progress."
        )
        return

    game = games[chat_id]
    if game.state != GameState.PLAYING:
        await update.message.reply_text(
            "Game is not in the playing phase."
        )
        return

    if game.creator_id != user_id:
        await update.message.reply_text(
            "Only the game creator can force next player."
        )
        return

    current_player_id = game.get_current_player_id()
    next_player_id = game.next_turn()
    
    if next_player_id:
        await update.message.reply_text(
            f"{game.players[current_player_id].display_name()} has finished their turn.\n\n"
            f"Next player: {game.players[next_player_id].display_name()}"
        )
    else:
        # Round over, move to voting
        await update.message.reply_text(
            f"{game.players[current_player_id].display_name()} has finished their turn.\n\n"
            f"All players have spoken! Time to vote.\n"
            f"Use /vote @username to vote who you think is the Undercover or Mr. White."
        )


async def all_spoken(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Skip to voting phase if all players have spoken or by creator force."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text(
            "No game in progress."
        )
        return

    game = games[chat_id]
    if game.state != GameState.PLAYING:
        await update.message.reply_text(
            "Game is not in the playing phase."
        )
        return

    if game.creator_id != user_id:
        await update.message.reply_text(
            "Only the game creator can force voting phase."
        )
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
        await update.message.reply_text(
            "No game in progress."
        )
        return

    game = games[chat_id]
    if game.state != GameState.VOTING:
        await update.message.reply_text(
            "It's not voting time yet."
        )
        return

    if user_id not in game.players or game.players[user_id].eliminated:
        await update.message.reply_text(
            "You can't vote because you're not in the game or have been eliminated."
        )
        return

    if game.players[user_id].has_voted:
        await update.message.reply_text(
            "You've already voted this round."
        )
        return

    # Parse the username from the command
    if not context.args:
        await update.message.reply_text(
            "Please specify who to vote for: /vote @username"
        )
        return

    target_username = context.args[0].lstrip('@')
    target_id = None
    
    # Find the player by username
    for pid, player in game.players.items():
        if player.username == target_username:
            target_id = pid
            break

    if not target_id:
        await update.message.reply_text(
            f"Could not find player with username @{target_username}"
        )
        return

    if game.players[target_id].eliminated:
        await update.message.reply_text(
            "This player has already been eliminated."
        )
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
                await update.message.reply_text(
                    f"{eliminated_player.display_name()} has been eliminated!\n"
                    f"They were a {eliminated_player.role.value.upper()}"
                )
                
                if eliminated_player.role == Role.MR_WHITE:
                    # Mr. White gets one guess
                    active_mr_white_guesses[eliminated_id] = chat_id
                    
                    await update.message.reply_text(
                        f"{eliminated_player.display_name()} was Mr. White and gets one chance to guess!\n"
                        f"I've sent them a private message to make their guess."
                    )
                    
                    try:
                        await context.bot.send_message(
                            chat_id=eliminated_id,
                            text="You've been caught as Mr. White! What do you think the Civilians' soccer player is? Reply with just the name.",
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
                        # Display next player
                        next_player_id = game.get_current_player_id()
                        await update.message.reply_text(
                            f"Round {game.round_number} begins!\n"
                            f"First player: {game.players[next_player_id].display_name()}"
                        )
            else:
                # No elimination (tie with 'none' tiebreaker)
                await update.message.reply_text(
                    "Voting resulted in a tie! No player is eliminated this round."
                )
                
                # Reset for next round
                game._prepare_next_round()
                
                # Start next round
                next_player_id = game.get_current_player_id()
                await update.message.reply_text(
                    f"Round {game.round_number} begins!\n"
                    f"First player: {game.players[next_player_id].display_name()}"
                )
    else:
        await update.message.reply_text(
            "Failed to register vote. Make sure both you and the target are valid players."
        )


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


async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """End the current game session."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in games:
        await update.message.reply_text(
            "No game in progress to end."
        )
        return

    game = games[chat_id]
    
    # Only the game creator or an admin can end the game
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    is_admin = chat_member.status in ["creator", "administrator"]
    
    if game.creator_id != user_id and not is_admin:
        await update.message.reply_text(
            "Only the game creator or a group admin can end the game."
        )
        return
    
    # Show game summary if the game had started
    if game.state != GameState.WAITING_FOR_PLAYERS:
        # Create game summary
        summary = "🛑 Game terminated!\n\n"
        
        if game.civilian_word and game.undercover_word:
            summary += f"The words were:\n- Civilians: *{game.civilian_word}*\n- Undercover: *{game.undercover_word}*\n\n"
        
        summary += "Player Roles:\n"
        for player in game.players.values():
            if player.role:
                summary += f"- {player.display_name()}: {player.role.value.upper()}\n"
            else:
                summary += f"- {player.display_name()}: (No role assigned)\n"
        
        await update.message.reply_text(summary, parse_mode="Markdown")
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


async def game_over(
    update: Optional[Update], 
    context: ContextTypes.DEFAULT_TYPE, 
    winner: Role,
    chat_id: Optional[int] = None
) -> None:
    """Handle game over condition."""
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
    
    # Create winner message
    if winner == Role.CIVILIAN:
        winner_message = "🎉 The CIVILIANS have won! 🎉"
    elif winner == Role.UNDERCOVER:
        winner_message = "🎭 The UNDERCOVER players have won! 🎭"
    else:  # Mr. White
        winner_message = "🃏 MR. WHITE has won with a correct guess! 🃏"
    
    # Create game summary
    summary = (
        f"{winner_message}\n\n"
        f"Game Summary:\n"
        f"- Civilians ({len(alive_civilians)}/{len(civilians)} remaining): "
        f"Soccer player was *{game.civilian_word}*\n"
        f"- Undercover ({len(alive_undercovers)}/{len(undercovers)} remaining): "
        f"Soccer player was *{game.undercover_word}*\n"
        f"- Mr. White ({len(alive_mr_whites)}/{len(mr_whites)} remaining)\n\n"
        f"Player Roles:\n"
    )
    
    # Add all player roles
    for player in game.players.values():
        status = "ALIVE" if not player.eliminated else "eliminated"
        summary += f"- {player.display_name()}: {player.role.value.upper()} ({status})\n"
    
    summary += "\nGame over! Start a new game with /newgame"
    
    # Send final message
    await context.bot.send_message(
        chat_id=chat_id,
        text=summary,
        parse_mode="Markdown"
    )
    
    # Remove game from active games
    del games[chat_id]


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

    if option == "mrwhitestart":
        if value in ["on", "true", "yes", "1"]:
            game.settings["mr_white_start"] = True
            await update.message.reply_text("Mr. White can now be the first player.")
        elif value in ["off", "false", "no", "0"]:
            game.settings["mr_white_start"] = False
            await update.message.reply_text("Mr. White can't be the first player.")
        else:
            await update.message.reply_text("Invalid value. Use 'on' or 'off'.")
    
    elif option == "tiebreaker":
        if value == "random":
            game.settings["tiebreaker"] = "random"
            await update.message.reply_text("Ties will be broken randomly.")
        elif value == "none":
            game.settings["tiebreaker"] = "none"
            await update.message.reply_text("Ties will result in no elimination.")
        else:
            await update.message.reply_text("Invalid value. Use 'random' or 'none'.")
    
    elif option == "civilians":
        try:
            count = int(value)
            if count >= 0:
                game.settings["civilian_count"] = count
                await update.message.reply_text(f"Civilian count set to {count} (0 = auto).")
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
            else:
                await update.message.reply_text("Count must be non-negative.")
        except ValueError:
            await update.message.reply_text("Invalid value. Use a number.")
    
    else:
        await update.message.reply_text(
            "Unknown option. Available options: mrwhitestart, tiebreaker, civilians, undercover, mrwhite"
        )


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
    
    # Check if soccer_player_pairs.json has any entries
    if not SOCCER_PLAYER_PAIRS:
        print("Warning: No soccer player pairs loaded. Games will not function properly.")
        print("Please create a soccer_player_pairs.json file with player pairs.")

    # Create the Application and pass it your bot's token
    application = Application.builder().token(token).build()

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
    application.add_handler(CommandHandler("settings", settings))
    
    # Add the new end game command
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
    application.run_polling()


if __name__ == "__main__":
    main()