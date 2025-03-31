from enum import Enum

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