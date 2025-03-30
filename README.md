# Soccer Mr. Undercover Telegram Bot

A Telegram bot implementation of the "Mr. Undercover" social deduction game with a soccer theme. Players are assigned soccer player names and must describe their player without naming them directly.

## Installation

### Prerequisites
- Python 3.8 or higher
- `python-telegram-bot` library (v20.0+)

### Setup

1. **Clone the repository or download the files**

2. **Install dependencies**
   ```
   pip install python-telegram-bot python-dotenv
   ```

3. **Create a Telegram Bot**
   - Talk to [@BotFather](https://t.me/BotFather) on Telegram
   - Use the `/newbot` command and follow instructions
   - Copy your API token

4. **Configure environment variables**
   - Create a `.env` file based on the `.env.example` template
   - Add your Telegram bot token: `TELEGRAM_BOT_TOKEN=your_token_here`

5. **Run the bot**
   ```
   python soccer_undercover_bot.py
   ```

## Game Rules

### Roles
- **Civilians**: Majority of players who all receive the same soccer player name
- **Undercover**: Player(s) who receive a similar but different player name
- **Mr. White**: Player(s) who don't receive any soccer player name

### Game Flow
1. Players join the game via Telegram
2. Bot assigns roles and sends private messages with soccer player names
3. Players take turns describing their player without naming them directly
4. After all players have spoken, voting begins
5. Player with most votes is eliminated and their role is revealed
6. If Mr. White is eliminated, they get one guess at the Civilians' word
7. Game continues until a winner is determined

### Win Conditions
- **Civilians**: Win if all Undercover and Mr. White players are eliminated
- **Undercover**: Win if they outnumber Civilians
- **Mr. White**: Wins instantly by correctly guessing the Civilians' word when eliminated

## Available Commands

| Command | Description |
|---------|-------------|
| `/newgame` | Create a new game |
| `/join` | Join an existing game |
| `/start` | Start the game after players have joined |
| `/done` | Indicate player has finished their turn |
| `/next` | Move to the next player (for in-person games) |
| `/allspoken` | Skip to voting phase |
| `/vote @username` | Cast vote to eliminate a player |
| `/settings` | Configure game options |
| `/help` | Show available commands |

## Configuration Options

- **Mr. White Start**: Toggle whether Mr. White can be the first player
  ```
  /settings mrwhitestart [on/off]
  ```

- **Tie-Breaking**: Toggle between random selection or no elimination for ties
  ```
  /settings tiebreaker [random/none]
  ```

- **Role Counts**: Configure the number of each role
  ```
  /settings civilians [number]
  /settings undercover [number]
  /settings mrwhite [number]
  ```
  Note: Setting any count to 0 will enable automatic distribution based on player count.

## Adding Custom Soccer Player Pairs

Edit the `soccer_player_pairs.json` file to add, remove, or modify player pairs. The format is:

```json
[
    {
        "civilian": "Player Name 1",
        "undercover": "Similar Player Name 1"
    },
    {
        "civilian": "Player Name 2",
        "undercover": "Similar Player Name 2"
    }
]
```

Choose player pairs that are similar in some way (position, playing style, nationality, etc.) but still distinct enough to create an interesting game.