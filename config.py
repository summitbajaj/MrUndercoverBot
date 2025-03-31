import logging
import json
from typing import Dict, List

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load soccer player pairs
try:
    with open("data/soccer_player_pairs.json", "r") as f:
        SOCCER_PLAYER_PAIRS = json.load(f)
except FileNotFoundError:
    logger.error("soccer_player_pairs.json not found! Please create this file.")
    logger.info("You can use the soccer_player_pairs.json in the repository as a template.")
    SOCCER_PLAYER_PAIRS = []  # Empty list as fallback

# Game storage - maps chat_id to Game
games = {}

# Active Mr. White guesses - maps user_id to chat_id
active_mr_white_guesses = {}