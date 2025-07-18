from typing import Any
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
import logging

# Set up logging to help debug issues
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("escape-room")

# --- Game State ---
game_state = {
    "inventory": [],
    "doors": {
        "1": {"opened": False, "has_key": False},
        "2": {"opened": False, "has_key": True},
        "3": {"opened": False, "has_key": False}
    },
    "safe": {"locked": True, "opened": False, "code": "5274"}
}

# --- Tool Input Schemas ---
class DoorInput(BaseModel):
    door_id: str = Field(
        description="Must be exactly '1', '2', or '3'"
    )

class CodeInput(BaseModel):
    code: str = Field(
        description="The 4-digit code to enter into the safe"
    )

# --- Tools ---

@mcp.tool(
    name="describe_room",
    description="Describes the current room, including visible features and known inventory."
)
def describe_room() -> str:
    logger.info("describe_room called")
    
    msg = "You are in a dimly lit room. The air feels thick with mystery. You see three doors clearly labeled: door_1, door_2, and door_3. Against one wall stands a sturdy metal safe with a glowing keypad."
    
    # Add inventory info
    if "key" in game_state["inventory"]:
        msg += " You're holding a rusty key in your hand."
    
    # Add safe status
    if game_state["safe"]["opened"]:
        msg += " The safe is wide open, revealing bright daylight beyond - your escape route!"
    elif not game_state["safe"]["locked"]:
        msg += " The safe is unlocked (the keypad glows green), but the door is still closed."
    else:
        msg += " The safe appears to be locked tight."
    
    # Add opened doors info
    opened_doors = [door_id for door_id, door in game_state["doors"].items() if door["opened"]]
    if opened_doors:
        msg += f" You've already opened door(s): {', '.join([f'door_{d}' for d in opened_doors])}."
    
    logger.info(f"describe_room result: {msg}")
    return msg

@mcp.tool(
    name="look_behind_door",
    description="Opens a specific door and describes what is behind it. door_id must be '1', '2', or '3'."
)
def look_behind_door(input: DoorInput) -> str:
    door_id = input.door_id.strip()
    logger.info(f"look_behind_door called with door_id: '{door_id}'")
    
    # Strict validation
    if door_id not in ["1", "2", "3"]:
        error_msg = f"ERROR: Invalid door ID '{door_id}'. Must be exactly '1', '2', or '3'."
        logger.error(error_msg)
        return error_msg

    door = game_state["doors"][door_id]
    
    # Check if already opened
    if door["opened"]:
        if door.get("has_key"):
            return f"Door_{door_id} is already open. You can see the rusty key lying behind it."
        else:
            return f"Door_{door_id} is already open and empty."
    
    # Open the door
    door["opened"] = True
    logger.info(f"Opened door {door_id}")

    if door.get("has_key"):
        result = f"You pull open door_{door_id} with a loud creak. Behind it, glinting in the dim light, you spot a rusty old key lying on the ground!"
    else:
        result = f"You pull open door_{door_id} with a loud creak. Unfortunately, there's nothing behind it - just empty space and shadows."
    
    logger.info(f"look_behind_door result: {result}")
    return result

@mcp.tool(
    name="take_key",
    description="Takes the rusty key if it's visible behind an open door."
)
def take_key() -> str:
    logger.info("take_key called")
    
    # Check if already have key
    if "key" in game_state["inventory"]:
        return "You already have the key in your possession."
    
    # Look for available key
    for door_id, door in game_state["doors"].items():
        if door.get("has_key") and door["opened"]:
            door["has_key"] = False
            game_state["inventory"].append("key")
            result = f"You reach down and pick up the rusty key from behind door_{door_id}. It feels heavy and old in your hand."
            logger.info(f"Key taken from door {door_id}")
            return result
    
    return "You don't see any key available to take. You might need to look behind the doors first."

@mcp.tool(
    name="use_key_on_safe",
    description="Uses the key from your inventory to unlock the safe if it's locked."
)
def use_key_on_safe() -> str:
    logger.info("use_key_on_safe called")
    
    if "key" not in game_state["inventory"]:
        return "You don't have a key to use. You need to find and take a key first."
    
    if not game_state["safe"]["locked"]:
        return "The safe is already unlocked. The keypad glows green, ready for you to enter a code."
    
    # Unlock the safe
    game_state["safe"]["locked"] = False
    result = "You insert the rusty key into a small keyhole on the side of the safe and turn it. *CLICK!* The safe unlocks and the keypad lights up green. You notice a piece of paper taped inside the lock mechanism with numbers written on it: '5274'."
    
    logger.info("Safe unlocked with key")
    return result

@mcp.tool(
    name="enter_code",
    description="Enters a 4-digit code into the safe to try to open it. The safe must be unlocked first."
)
def enter_code(input: CodeInput) -> str:
    code = input.code.strip()
    logger.info(f"enter_code called with code: '{code}'")
    
    if game_state["safe"]["locked"]:
        return "The safe is still locked. You need to unlock it with a key before entering a code."
    
    if code == game_state["safe"]["code"]:
        if not game_state["safe"]["opened"]:
            game_state["safe"]["opened"] = True
            result = f"BEEP BEEP BEEP! You enter the code {code} on the keypad. The safe door swings open wide with a satisfying *WHOOSH*, revealing bright daylight streaming in from outside. You've found your escape route! Congratulations - you've successfully escaped the room!"
            logger.info("Safe opened - player escaped!")
            return result
        else:
            return f"You enter the code {code} again. The keypad beeps happily, but you've already opened the safe and can see your escape route."
    else:
        result = f"You carefully enter the code {code} on the keypad. *BUZZ* The keypad flashes red and makes an error sound. That's not the right code."
        logger.info(f"Wrong code entered: {code}")
        return result

# --- Debug function ---
def get_game_state() -> dict:
    return game_state

# --- Run Server ---
if __name__ == "__main__":
    logger.info("Starting escape room server...")
    logger.info(f"Initial game state: {game_state}")
    mcp.run(transport="stdio")