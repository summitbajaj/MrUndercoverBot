import random
from typing import Dict, List, Optional, Set, Tuple, Union
import logging

from models.enums import Role, GameState
from models.player import Player
from config import SOCCER_PLAYER_PAIRS

logger = logging.getLogger(__name__)

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

        # Check if all players have spoken
        all_spoken = True
        for player_id, player in self.players.items():
            if not player.eliminated and not player.has_spoken:
                all_spoken = False
                break
        
        # If all have spoken, move to voting
        if all_spoken:
            self.state = GameState.VOTING
            return None

        # Find next non-eliminated player who hasn't spoken
        original_idx = self.current_turn_idx
        found_next_player = False
        
        # Loop through players to find the next one
        for _ in range(len(self.turn_order)):
            self.current_turn_idx = (self.current_turn_idx + 1) % len(self.turn_order)
            next_player_id = self.turn_order[self.current_turn_idx]
            
            # If we've gone full circle back to original player, everyone has spoken
            if self.current_turn_idx == original_idx:
                break
                
            # Skip eliminated players and those who have already spoken
            if not self.players[next_player_id].eliminated and not self.players[next_player_id].has_spoken:
                found_next_player = True
                break
        
        # If no suitable next player was found, move to voting
        if not found_next_player:
            self.state = GameState.VOTING
            return None
            
        # Return the next player's ID
        return self.turn_order[self.current_turn_idx]

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
                
            # Special case: Check if we now have only Mr. White and one other player
            remaining_players = self.get_alive_players()
            if len(remaining_players) == 2:
                mr_white_player = next((p for p in remaining_players if p.role == Role.MR_WHITE), None)
                if mr_white_player:
                    # Force Mr. White guessing phase
                    self.state = GameState.MR_WHITE_GUESSING
                    return mr_white_player.user_id
            
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
            player.description = None  # Clear descriptions between rounds

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
        mr_white_id = None

        # Count remaining players by role
        for player_id, player in self.players.items():
            if not player.eliminated:
                if player.role == Role.CIVILIAN:
                    civilian_count += 1
                elif player.role == Role.UNDERCOVER:
                    undercover_count += 1
                elif player.role == Role.MR_WHITE:
                    mr_white_count += 1
                    mr_white_id = player_id

        # Special case: if only Mr. White and one other player remain
        # This should trigger the final guessing phase
        if mr_white_count == 1 and (civilian_count + undercover_count) == 1:
            self.state = GameState.MR_WHITE_GUESSING
            return None

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