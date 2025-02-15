import os
import time
import sys
import re
import requests
import subprocess
import logging
from pathlib import Path
from packaging import version
from colorama import init, Fore, Style
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

# Logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    filename="app.log",
    format='[%(filename)s] %(levelname)s : %(message)s',
    encoding="utf-8"
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('[%(filename)s] %(levelname)s : %(message)s'))
logging.getLogger().addHandler(console_handler)

# Initialize colorama for cross-platform colored output
init(autoreset=True)

# Set up ruamel.yaml in round-trip mode (preserves order and comments)
yaml = YAML(typ='rt')
yaml.preserve_quotes = True
yaml.encoding = "utf-8"

# Default configuration content
DEFAULT_CONFIG_CONTENT = r"""version: "1.0.4" # Don't touch here

# Discord Bot Configuration
Discord:
  token: "YOUR_DISCORD_BOT_TOKEN"
  # This is the token used to authenticate your bot with Discord.
  # Keep this token secure and do not share it publicly.

  channel_bot_chat: [12345678]  # The ID of the channel where the bot responds.
  # Use the Discord channel ID where you want the bot to send messages.
  # The bot will listen and send messages to this channel.

  admin_role: [12345678]  # The ID of the administrator role in Discord.
  # Only users with this role will have administrator commands privileges.
  # This option is not yet available!!!

  use_cai_avatar: true  # Whether to use the Character.AI profile picture for the bot.
  # If set to true, the bot will display the avatar from Character.AI.

  use_cai_display_name: true  # Whether to use the Character.AI display name for the bot.
  # If true, the bot's name will be replaced by the display name of the Character.AI character.

  messages_cache: "messages_cache.json"  # Path to the file where messages are cached.
  # This file stores the chat history for the bot.
  # It is used to keep track of conversations and ensure consistency.
  # If you have a lot of data, this file could grow in size.

# Character.AI Configuration
CAI:
  token: "YOUR_CHARACTER_AI_TOKEN"
  # This is the token for authenticating your bot with Character.AI.
  # Like the Discord token, keep this token private and do not share it.

  character_id: "7OQWCw72T2hHr8JwNIjXd8KpTy663wI_piz4XCHbeZ4"  # The ID of the Character.AI character.
  # This is the unique identifier for the character you want the bot to use.
  # The default ID is from Neuro-Sama

  chat_id: "---"
  # This is the ID of the specific chat session you want the bot to join.
  # It allows the bot to maintain continuity in its interactions with users.
  # Use “---” if you don't have a chat ID, the program will automatically fill in a new ID.

  new_chat_on_reset: true  # Whether to create a new chat session when resetting.
  # If set to true, a new chat session will be created each time the bot is reset.
  # If set to false, the bot will continue the current chat session after a reset.

  system_message: >
    [DO NOT RESPOND TO THIS MESSAGE!]

    You are connected to a Discord channel, 
    where several people may be present. Your objective is to interact with them in the chat.

    Greet the participants and introduce yourself by fully translating your message into English.

    Now, send your message introducing yourself in the chat, following the language of this message!

# Bot Interaction Settings
Options:
  auto_update: true # If true, the program will check for a new update every time it starts up
  #If true, the program will automatically search for an update
  # For realases or commits, this depends on how you run Bridge

  repo_url: "git@github.com:LixxRarin/CharacterAI-Discord-Bridge.git" # Repository url
  # This is the repository where the program will check and update.
  # Only touch this if you know what you're doing here!

  repo_branch: "main" 
  # This is the branch where the program will check and update.
  # Only touch this if you know what you're doing here!
  
  max_response_attempts: -1  # Set the number of response attempts, -1 for automatic retries.
  # The bot will try to respond a maximum of this many times. If set to -1, the bot will keep retrying until a valid response is received.

  send_message_line_by_line: true  # Whether to send bot messages one line at a time.
  # If true, the bot will send each message in the chat as separate lines, rather than sending everything at once.
  # This can make the interaction feel more natural or less overwhelming.

  debug_mode: true  # Enable debug mode for troubleshooting.
  # When true, the bot will log detailed information about its processes in the console, which is helpful for debugging.
  # This mode should be off in production to avoid excessive logging.
  # This option is not yet available!!!

# Message Formatting Rules
MessageFormatting:
  remove_IA_text_from: ['\*[^*]*\*', '\[[^\]]*\]', '"']
  remove_user_text_from: ['\*[^*]*\*', '\[[^\]]*\]']
  # Remove certain patterns from the AI and user messages.
  # This removes text enclosed in asterisks (often used for emphasis or actions),
  # any text in square brackets (often for OOC), and any quotation marks.
  # Adjust these patterns as needed based on the format of your messages.

  remove_emojis:
    user: false
    AI: false
  # Whether to remove emojis from user or/and AI messages.
  # If set to true, emojis will be stripped from user messages before they are processed.
  # Setting to false keeps emojis in the conversation.

  user_reply_format_syntax: "[(Reply: @{reply_name}:) {reply_message}]\n[[time} ~ @{username} - {name}:] {message}"
  user_format_syntax: "[{time} ~ @{username} - {name}:] {message}"
"""


def merge_ordered(user_cfg, default_cfg):
    """
    Merges two CommentedMaps preserving the order from default_cfg.
    For each key in default_cfg, if user_cfg contains that key,
    its value is used (merging recursively for dicts).
    Then, any extra keys from user_cfg are appended in their original order.
    """
    merged = CommentedMap()
    # Iterate over keys in default_cfg to preserve order
    for key, default_val in default_cfg.items():
        if key in user_cfg:
            user_val = user_cfg[key]
            if isinstance(default_val, dict) and isinstance(user_val, dict):
                merged[key] = merge_ordered(user_val, default_val)
            else:
                merged[key] = user_val
        else:
            merged[key] = default_val
        # Preserve comments if available
        if hasattr(user_cfg, 'ca') and key in user_cfg.ca.items:
            merged.ca.items[key] = user_cfg.ca.items.get(key)
        elif hasattr(default_cfg, 'ca') and key in default_cfg.ca.items:
            merged.ca.items[key] = default_cfg.ca.items.get(key)

    # Append extra keys from user_cfg that are not in default_cfg, in original order
    for key in user_cfg:
        if key not in default_cfg:
            merged[key] = user_cfg[key]
            if hasattr(user_cfg, 'ca') and key in user_cfg.ca.items:
                merged.ca.items[key] = user_cfg.ca.items.get(key)
    return merged

class ConfigManager:
    def __init__(self, config_file="config.yml"):
        """
        Manages the configuration file.
        """
        self.config_file = config_file
        self.default_config = yaml.load(DEFAULT_CONFIG_CONTENT)
        self.user_config = self.load_user_config()

    def load_user_config(self):
        if not os.path.exists(self.config_file):
            return None
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return yaml.load(f)
        except Exception as e:
            logging.error("Error loading user configuration: %s", e)
            return None

    def is_version_outdated(self):
        user_version = self.user_config.get("version") if self.user_config else None
        default_version = self.default_config.get("version")
        if user_version is None:
            logging.warning("No version found in user configuration. Assuming outdated.")
            return True
        return version.parse(user_version) < version.parse(default_version)

    def merge_configs(self):
        """
        Merges the user's configuration with the default configuration,
        preserving the order from the default file.
        """
        if self.user_config is None:
            return self.default_config
        merged = merge_ordered(self.user_config, self.default_config)
        # Ensure the root "version" is updated
        merged["version"] = self.default_config.get("version")
        return merged

    def check_and_update(self):
        if self.user_config is None:
            logging.warning("Configuration file '%s' not found. Creating a new one...", self.config_file)
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(self.default_config, f)
                logging.info("Configuration file '%s' created successfully!", self.config_file)
            except Exception as e:
                logging.critical("Failed to create configuration file: %s", e)
            return

        if self.is_version_outdated():
            logging.warning("Updating configuration '%s' to version %s", self.config_file, self.default_config.get("version"))
            updated_config = self.merge_configs()
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(updated_config, f)
                logging.info("Configuration file '%s' updated successfully!", self.config_file)
            except Exception as e:
                logging.critical("Failed to update configuration file: %s", e)
        else:
            logging.info("Configuration file '%s' is up-to-date.", self.config_file)

class AutoUpdater:
    def __init__(self, repo_url, current_version, branch="main", is_exe=None):
        """
        Initializes the AutoUpdater.
        
        :param repo_url: Git repository URL (e.g., git@github.com:username/repo.git)
        :param current_version: Current version of the program (e.g., "1.0.2")
        :param branch: Branch to check for updates (default: "main")
        :param is_exe: Whether the program is running as an executable (auto-detected if None)
        """
        self.repo_url = repo_url
        self.current_version = current_version
        self.branch = branch
        self.is_exe = is_exe if is_exe is not None else self.is_running_as_exe()
        
        # Extract repository owner and name from URL
        self.repo_owner, self.repo_name = self._extract_repo_info(repo_url)
        self.base_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}"
        self.headers = {'Accept': 'application/vnd.github.v3+json'}
        
        self.exe_path = Path(sys.executable).resolve() if self.is_exe else None
        self.script_dir = Path(__file__).parent.resolve()

    def check_and_update(self):
        # Avoid infinite update loops by checking an environment flag
        if os.environ.get("SKIP_AUTOUPDATE") == "1":
            logging.info("Skipping update check to avoid infinite restart loop.")
            return

        if self.is_exe:
            latest_release = self._get_latest_release()
            if latest_release and version.parse(latest_release['tag_name']) > version.parse(self.current_version):
                logging.info("New executable version detected. Updating...")
                self._update_exe(latest_release)
            else:
                logging.info("No executable updates available.")
        else:
            if self._update_from_commit():
                logging.info("Source update applied; restarting program.")
                self._restart_program()

    def _extract_repo_info(self, repo_url):
        match = re.match(r"(?:git@github\.com:|https:\/\/github\.com\/)([\w-]+)/([\w-]+)(?:\.git)?", repo_url)
        if not match:
            raise ValueError("Invalid repository URL")
        return match.group(1), match.group(2)

    def _get_latest_release(self):
        try:
            response = requests.get(f"{self.base_url}/releases/latest", headers=self.headers)
            if response.status_code == 200:
                return response.json()
            else:
                logging.error("Failed to fetch latest release: Status code %s", response.status_code)
                return None
        except Exception as e:
            logging.error("Error fetching release: %s", e)
            return None

    def _update_exe(self, release_data):
        asset = next((a for a in release_data.get('assets', []) if a.get('name', '').endswith('.exe')), None)
        if not asset:
            logging.error("No .exe asset found in the release")
            return
        try:
            download_url = asset['browser_download_url']
            new_exe_content = requests.get(download_url).content

            update_script = f"""
@echo off
TIMEOUT /T 3 /NOBREAK
del "{self.exe_path}"
echo {new_exe_content.decode('latin1', errors='ignore')} > "{self.exe_path}"
start "" "{self.exe_path}"
del "%~f0"
"""
            with open("update.bat", "w", encoding="utf-8") as f:
                f.write(update_script)
            subprocess.Popen(["update.bat"], shell=True)
            sys.exit(0)
        except Exception as e:
            logging.error("Executable update failed: %s", e)

    def _update_from_commit(self):
        try:
            if (self.script_dir / '.git').exists():
                status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, cwd=self.script_dir)
                if status.stdout.strip():
                    logging.warning("There are uncommitted local changes. Consider committing or discarding them.")
                subprocess.run(['git', 'fetch', 'origin', self.branch], check=True, cwd=self.script_dir)
                subprocess.run(['git', 'reset', '--hard', f'origin/{self.branch}'], check=True, cwd=self.script_dir)
                logging.info("Code updated via Git (branch: %s)", self.branch)
                return True
            else:
                from selfupdate import update
                update()
                logging.info("Code updated via selfupdate library.")
                return True
        except Exception as e:
            logging.error("Source update failed: %s", e)
            return False

    def _restart_program(self):
        new_env = os.environ.copy()
        new_env["SKIP_AUTOUPDATE"] = "1"
        if self.is_exe:
            subprocess.Popen([str(self.exe_path)], env=new_env)
        else:
            subprocess.Popen([sys.executable] + sys.argv, env=new_env)
        sys.exit(0)

    @staticmethod
    def is_running_as_exe():
        return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def startup_screen():
    os.system("cls" if os.name == "nt" else "clear")
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}Project: {Fore.WHITE}Bridge - CharacterAI personas in Discord.
{Fore.YELLOW}Description: {Fore.WHITE}An AI-powered Discord bot using Character.AI! :3
{Fore.YELLOW}Creator: {Fore.WHITE}LixxRarin
{Fore.YELLOW}GitHub: {Fore.WHITE}https://github.com/LixxRarin/CharacterAI-Discord-Bridge
{Fore.YELLOW}Version: {Fore.WHITE}1.0.3
{Style.RESET_ALL}
"""
    print(banner)
    time.sleep(2)

def main():
    startup_screen()

    # Manage and update the configuration file
    config_manager = ConfigManager()
    config_manager.check_and_update()

    try:
        with open("config.yml", "r", encoding="utf-8") as file:
            config_data = yaml.load(file)
        logging.info("Configuration file 'config.yml' loaded successfully.")
    except FileNotFoundError as e:
        logging.critical("Configuration file 'config.yml' not found: %s", e)
        sys.exit(1)

    # Initialize AutoUpdater using configuration data
    updater = AutoUpdater(
        repo_url=config_data["Options"]["repo_url"],
        current_version="1.0.3",
        branch=config_data["Options"].get("repo_branch", "main")
    )

    if config_data["Options"].get("auto_update", False):
        updater.check_and_update()

    # Place additional bot/application logic here

if __name__ == "__main__":
    main()
