from typing import Optional
from models.enums import Role

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
        self.description: Optional[str] = None  # Store player's description

    def display_name(self) -> str:
        """Returns the best available name for display"""
        if self.username:
            return f"@{self.username}"
        return self.first_name