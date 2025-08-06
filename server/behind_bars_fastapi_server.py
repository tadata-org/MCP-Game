# server/behind_bars_fastapi_server.py
from typing import Any, Dict
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
# from fastapi_mcp import FastApiMCP # Moved this import down
import json
import base64
from PIL import Image
import io
import os
import logging

# Configure logging to be less verbose for FastAPI itself,
# but keep our custom game logging at INFO level.
#logging.disable(logging.CRITICAL)
logging.basicConfig(level=logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Set our custom game logger to INFO

# Initialize FastAPI app
app = FastAPI(
    title="Behind Bars Escape Room MCP Server",
    description="An escape room game server exposing actions as MCP tools via FastAPI."
)

# Game State for Behind Bars
class GameState:
    def __init__(self):
        self.door_opened = False
        self.rug_lifted = False
        self.key_taken = False
        self.safe_opened = False
        self.bolt_cutter_taken = False
        self.bars_cut = False
        self.escaped = False
        self.inventory = []  # Will contain "key" and/or "bolt_cutter"
    
    def to_dict(self):
        """Converts the game state to a dictionary."""
        return {
            "door_opened": self.door_opened,
            "rug_lifted": self.rug_lifted,
            "key_taken": self.key_taken,
            "safe_opened": self.safe_opened,
            "bolt_cutter_taken": self.bolt_cutter_taken,
            "bars_cut": self.bars_cut,
            "escaped": self.escaped,
            "inventory": self.inventory
        }

    def reset(self):
        """Resets the game state to its initial values."""
        self.door_opened = False
        self.rug_lifted = False
        self.key_taken = False
        self.safe_opened = False
        self.bolt_cutter_taken = False
        self.bars_cut = False
        self.escaped = False
        self.inventory = []
        logger.info("Game state reset.")


# Global game state instance
game_state = GameState()

def smart_inventory_check():
    """
    Automatically collects visible items when needed.
    """
    collected = []
    
    if game_state.rug_lifted and not game_state.key_taken:
        game_state.key_taken = True 
        game_state.inventory.append("key")
        collected.append("key")
        logger.info("Auto-collected key.")
    
    if game_state.safe_opened and not game_state.bolt_cutter_taken:
        game_state.bolt_cutter_taken = True
        game_state.inventory.append("bolt_cutter") 
        collected.append("bolt_cutter")
        logger.info("Auto-collected bolt cutter.")
    
    return collected

# Image Composer
class EscapeImageComposer:
    def __init__(self):
        server_dir = os.path.dirname(os.path.abspath(__file__))
        self.assets_path = os.path.join(server_dir, "assets")
        self.asset_cache = {}
        self.canvas_size = (1280, 720)
        logger.info(f"Escape room image composer initialized. Assets path: {self.assets_path}")
        
    def load_asset(self, filename: str) -> Image.Image:
        if filename in self.asset_cache:
            return self.asset_cache[filename]
            
        filepath = os.path.join(self.assets_path, filename)
        
        if os.path.exists(filepath):
            logger.debug(f"Loading asset: {filename}")
            img = Image.open(filepath)
            
            if img.size != self.canvas_size:
                logger.warning(f"Asset '{filename}' is {img.size}, resizing to {self.canvas_size}")
                img = img.resize(self.canvas_size, Image.Resampling.LANCZOS)
            
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            self.asset_cache[filename] = img
            return img
        else:
            logger.error(f"Missing asset: {filepath}. Returning transparent placeholder.")
            placeholder = Image.new('RGBA', self.canvas_size, (0, 0, 0, 0))
            return placeholder
    
    def compose_room_image(self, state: GameState) -> str:
        logger.info("🚪 Composing escape room image...")
        logger.debug(f"📊 Current Game State: {state.to_dict()}")
        
        layers_applied = []
        final_image = self.load_asset("room_base.png").copy()
        layers_applied.append("✅ room_base.png (base room)")
        
        if state.door_opened:
            if state.bars_cut:
                door_overlay = self.load_asset("door_open_bars_cut.png")
                layers_applied.append("✅ door_open_bars_cut.png (ESCAPE ROUTE!)")
            else:
                door_overlay = self.load_asset("door_open_bars.png")
                layers_applied.append("✅ door_open_bars.png (blocked by bars)")
        else:
            door_overlay = self.load_asset("door_closed.png")
            layers_applied.append("✅ door_closed.png (door closed)")
        final_image = Image.alpha_composite(final_image, door_overlay)
        
        if state.rug_lifted:
            if state.key_taken:
                rug_overlay = self.load_asset("rug_lifted_empty.png")
                layers_applied.append("✅ rug_lifted_empty.png (key taken)")
            else:
                rug_overlay = self.load_asset("rug_lifted_key.png")
                layers_applied.append("✅ rug_lifted_key.png (KEY VISIBLE)")
        else:
            rug_overlay = self.load_asset("rug_normal.png")
            layers_applied.append("✅ rug_normal.png (rug in place)")
        final_image = Image.alpha_composite(final_image, rug_overlay)
        
        if state.safe_opened:
            if state.bolt_cutter_taken:
                safe_overlay = self.load_asset("safe_open_empty.png")
                layers_applied.append("✅ safe_open_empty.png (tool taken)")
            else:
                safe_overlay = self.load_asset("safe_open_tool.png")
                layers_applied.append("✅ safe_open_tool.png (BOLT CUTTER VISIBLE)")
        else:
            safe_overlay = self.load_asset("safe_closed.png")
            layers_applied.append("✅ safe_closed.png (safe locked)")
        final_image = Image.alpha_composite(final_image, safe_overlay)
        
        if "key" in state.inventory:
            key_inv = self.load_asset("inventory_key.png")
            final_image = Image.alpha_composite(final_image, key_inv)
            layers_applied.append("✅ inventory_key.png (carrying key)")
        
        if "bolt_cutter" in state.inventory:
            tool_inv = self.load_asset("inventory_bolt_cutter.png")
            final_image = Image.alpha_composite(final_image, tool_inv)
            layers_applied.append("✅ inventory_bolt_cutter.png (carrying tool)")
        
        logger.info("🚪 ESCAPE ROOM IMAGE COMPOSITION SUMMARY:")
        for i, layer in enumerate(layers_applied, 1):
            #logger.info(f"   {i}. {layer}")
            pass
        
        rgb_image = Image.new('RGB', self.canvas_size, (255, 255, 255))
        rgb_image.paste(final_image, mask=final_image.split()[-1])
            
        buffer = io.BytesIO()
        try:
            rgb_image.save(buffer, format='PNG', optimize=True, quality=95)
            image_data = base64.b64encode(buffer.getvalue()).decode()
            logger.info(f"✅ Generated escape room image ({len(image_data)} chars)")
            return image_data
        except Exception as e:
            logger.error(f"❌ Failed to encode escape room image: {e}")
            return ""

# Global image composer instance
escape_composer = EscapeImageComposer()

# --- FastAPI Endpoints (replacing MCP tools) ---

@app.post(
    "/open_door",
    operation_id="open_door", # Explicit operation_id for MCP tool naming
    summary="Opens/checks the main door.",
    description="Use when player wants to: open door, check door, look at door, examine door, try door."
)
async def open_door() -> Dict[str, Any]:
    logger.info("API call: open_door")
    
    response_data = {}
    if game_state.door_opened:
        if game_state.bars_cut:
            response_data = {
                "success": True,
                "message": "The door is already open, and you've cut through the bars. Freedom awaits!",
                "image": escape_composer.compose_room_image(game_state),
                "won": True
            }
        else:
            response_data = {
                "success": True,
                "message": "The door is already open, but metal bars block your path.",
                "image": escape_composer.compose_room_image(game_state)
            }
    else:
        game_state.door_opened = True
        response_data = {
            "success": True,
            "message": "You open the door, but your heart sinks. Thick metal bars block your escape! You'll need to find another way through.",
            "image": escape_composer.compose_room_image(game_state),
            "state": game_state.to_dict()
        }
    logger.info(f"DEBUG: open_door returning: {response_data['message'][:50]}...")
    return response_data

@app.post(
    "/look_under_rug",
    operation_id="look_under_rug",
    summary="Lifts/moves the rug to see underneath.",
    description="Lifts/moves the rug to see underneath. Use when player wants to: lift rug, move rug, look under rug, check rug, search rug."
)
async def look_under_rug() -> Dict[str, Any]:
    logger.info("API call: look_under_rug")
    
    response_data = {}
    if game_state.rug_lifted:
        if game_state.key_taken:
            response_data = {
                "success": True,
                "message": "You've already taken the key from here.",
                "image": escape_composer.compose_room_image(game_state)
            }
        else:
            response_data = {
                "success": True,
                "message": "The rug is lifted, revealing the key underneath.",
                "image": escape_composer.compose_room_image(game_state)
            }
    else:
        game_state.rug_lifted = True
        response_data = {
            "success": True,
            "message": "You lift the corner of the rug and discover a small brass key hidden underneath!",
            "image": escape_composer.compose_room_image(game_state),
            "state": game_state.to_dict()
        }
    logger.info(f"DEBUG: look_under_rug returning: {response_data['message'][:50]}...")
    return response_data

@app.post(
    "/take_key",
    operation_id="take_key",
    summary="Picks up the brass key from under the rug.",
    description="Picks up the brass key from under the rug. Use when player wants to: take key, pick up key, grab key, get key."
)
async def take_key() -> Dict[str, Any]:
    logger.info("API call: take_key")
    
    response_data = {}
    if game_state.key_taken:
        response_data = {
            "success": False,
            "message": "You already have the key.",
            "image": escape_composer.compose_room_image(game_state)
        }
    elif not game_state.rug_lifted:
        response_data = {
            "success": False,
            "message": "You don't see any key. Maybe you should look under the rug first?",
            "image": escape_composer.compose_room_image(game_state)
        }
    else:
        game_state.key_taken = True
        game_state.inventory.append("key")
        response_data = {
            "success": True,
            "message": "You pick up the brass key. It feels solid and well-made.",
            "image": escape_composer.compose_room_image(game_state),
            "state": game_state.to_dict()
        }
    logger.info(f"DEBUG: take_key returning: {response_data['message'][:50]}...")
    return response_data

@app.post(
    "/open_safe",
    operation_id="open_safe",
    summary="Uses the brass key to unlock the safe.",
    description="Uses the brass key to unlock the safe. Use when player wants to: open safe, unlock safe, use key on safe, put key in safe, key safe."
)
async def open_safe() -> Dict[str, Any]:
    logger.info("API call: open_safe")
    
    response_data = {}
    if game_state.safe_opened:
        if game_state.bolt_cutter_taken:
            response_data = {
                "success": True,
                "message": "The safe is already open and empty.",
                "image": escape_composer.compose_room_image(game_state)
            }
        else:
            response_data = {
                "success": True,
                "message": "The safe is already open, revealing a heavy-duty bolt cutter inside.",
                "image": escape_composer.compose_room_image(game_state)
            }
    else:
        collected = smart_inventory_check()
        
        if "key" not in game_state.inventory:
            response_data = {
                "success": False,
                "message": "The safe is locked.",
                "image": escape_composer.compose_room_image(game_state)
            }
        else:
            game_state.safe_opened = True
            
            message = "You insert the key into the safe's lock. It turns smoothly! The safe opens with a satisfying click, revealing a heavy-duty bolt cutter inside."
            if "key" in collected:
                message = "You grab the key from under the rug and use it on the safe. It turns smoothly! The safe opens with a satisfying click, revealing a heavy-duty bolt cutter inside."
            response_data = {
                "success": True,
                "message": message,
                "image": escape_composer.compose_room_image(game_state),
                "state": game_state.to_dict()
            }
    logger.info(f"DEBUG: open_safe returning: {response_data['message'][:50]}...")
    return response_data

@app.post(
    "/take_bolt_cutter",
    operation_id="take_bolt_cutter",
    summary="Takes the bolt cutter from inside the open safe.",
    description="Takes the bolt cutter from inside the open safe. Use when player wants to: take bolt cutter, take tool, grab cutter, get item from safe."
)
async def take_bolt_cutter() -> Dict[str, Any]:
    logger.info("API call: take_bolt_cutter")
    
    response_data = {}
    if game_state.bolt_cutter_taken:
        response_data = {
            "success": False,
            "message": "You already have the bolt cutter.",
            "image": escape_composer.compose_room_image(game_state)
        }
    elif not game_state.safe_opened:
        response_data = {
            "success": False,
            "message": "The safe is locked.",
            "image": escape_composer.compose_room_image(game_state)
        }
    else:
        game_state.bolt_cutter_taken = True
        game_state.inventory.append("bolt_cutter")
        response_data = {
            "success": True,
            "message": "You lift the heavy bolt cutter from the safe. Its weight feels reassuring.",
            "image": escape_composer.compose_room_image(game_state),
            "state": game_state.to_dict()
        }
    logger.info(f"DEBUG: take_bolt_cutter returning: {response_data['message'][:50]}...")
    return response_data

@app.post(
    "/cut_bars",
    operation_id="cut_bars",
    summary="Uses bolt cutter to cut through metal bars on the door.",
    description="Uses bolt cutter to cut through metal bars on the door. Use when player wants to: cut bars, use bolt cutter, break bars, cutter bars."
)
async def cut_bars() -> Dict[str, Any]:
    logger.info("API call: cut_bars")
    
    response_data = {}
    if game_state.bars_cut:
        response_data = {
            "success": True,
            "message": "You've already cut through the bars. The path to freedom is clear!",
            "image": escape_composer.compose_room_image(game_state),
            "won": True
        }
    elif not game_state.door_opened:
        response_data = {
            "success": False,
            "message": "You need to open the door first to see the bars.",
            "image": escape_composer.compose_room_image(game_state)
        }
    else:
        collected = smart_inventory_check()
        
        if "bolt_cutter" not in game_state.inventory:
            response_data = {
                "success": False,
                "message": "You don't have anything to cut the bars with.",
                "image": escape_composer.compose_room_image(game_state)
            }
        else:
            game_state.bars_cut = True
            game_state.escaped = True
            
            message = "You position the bolt cutter on the metal bars and squeeze with all your might. SNAP! The bars give way with a satisfying crack. You've created an opening large enough to escape through. Freedom at last!"
            if "bolt_cutter" in collected:
                message = "You grab the bolt cutter from the safe and immediately put it to work on the metal bars. SNAP! The bars give way with a satisfying crack. You've created an opening large enough to escape through. Freedom at last!"
            response_data = {
                "success": True,
                "message": message,
                "image": escape_composer.compose_room_image(game_state),
                "state": game_state.to_dict(),
                "won": True
            }
    logger.info(f"DEBUG: cut_bars returning: {response_data['message'][:50]}...")
    return response_data

@app.post(
    "/use_key_on_door",
    operation_id="use_key_on_door",
    summary="Tries to use the brass key on the main door lock.",
    description="Tries to use the brass key on the main door lock. Use when player says: use key on door, unlock door with key, put key in door."
)
async def use_key_on_door() -> Dict[str, Any]:
    logger.info("API call: use_key_on_door")
    
    response_data = {}
    collected = smart_inventory_check()
    
    if "key" not in game_state.inventory:
        response_data = {
            "success": False,
            "message": "You don't have a key yet.",
            "image": escape_composer.compose_room_image(game_state)
        }
    else:
        message = "The small brass key doesn't fit the door's heavy lock. It's much too small."
        if "key" in collected:
            message = "You grab the key from under the rug and try it on the door, but it's much too small for the heavy lock."
        response_data = {
            "success": False,
            "message": message,
            "image": escape_composer.compose_room_image(game_state)
        }
    logger.info(f"DEBUG: use_key_on_door returning: {response_data['message'][:50]}...")
    return response_data

@app.post(
    "/use_bolt_cutter_on_door",
    operation_id="use_bolt_cutter_on_door",
    summary="Tries to use bolt cutter on the door itself (not bars).",
    description="Tries to use bolt cutter on the door itself (not bars). Use when player says: cut door, use bolt cutter on door, break door with cutter."
)
async def use_bolt_cutter_on_door() -> Dict[str, Any]:
    logger.info("API call: use_bolt_cutter_on_door")
    
    response_data = {}
    collected = smart_inventory_check()
    
    if "bolt_cutter" not in game_state.inventory:
        response_data = {
            "success": False,
            "message": "You don't have a bolt cutter.",
            "image": escape_composer.compose_room_image(game_state)
        }
    elif not game_state.door_opened:
        message = "You try to use the bolt cutter on the closed door, but it's solid material. Maybe you should open the door first to see what's behind it?"
        if "bolt_cutter" in collected:
            message = "You grab the bolt cutter from the safe and try to use it on the closed door, but it's solid material. Maybe you should open the door first to see what's behind it?"
        response_data = {
            "success": False,
            "message": message,
            "image": escape_composer.compose_room_image(game_state)
        }
    else:
        message = "The bolt cutter isn't meant for the door itself. But you notice those metal bars blocking your path - maybe the cutter would work on those?"
        if "bolt_cutter" in collected:
            message = "You grab the bolt cutter from the safe, but it's not meant for the door itself. However, you notice those metal bars blocking your path - maybe the cutter would work on those?"
        response_data = {
            "success": False,
            "message": message,
            "image": escape_composer.compose_room_image(game_state)
        }
    logger.info(f"DEBUG: use_bolt_cutter_on_door returning: {response_data['message'][:50]}...")
    return response_data

@app.post(
    "/give_hint",
    operation_id="give_hint",
    summary="Provides contextual hints when player asks for help.",
    description="Provides contextual hints when player asks for help. Use when player says: give me a hint, what should I do, I'm stuck, help me, need help, solution, etc."
)
async def give_hint() -> Dict[str, Any]:
    """Provides smart, contextual hints based on current game state."""
    logger.info("API call: give_hint")
    
    hint = ""
    if not game_state.door_opened and not game_state.rug_lifted:
        hint = "You're in an unfamiliar room. Try exploring what you can see - maybe start with that door or check around the floor."
    elif not game_state.door_opened and game_state.rug_lifted and not game_state.key_taken:
        hint = "You've discovered something interesting under the rug! Maybe pick it up, then see what's behind that door."
    elif not game_state.door_opened and game_state.key_taken:
        hint = "You have a key, but what's behind that door? Better open it and see what you're dealing with."
    elif game_state.door_opened and not game_state.rug_lifted:
        hint = "The door reveals your challenge, but you'll need tools to solve it. Search the room thoroughly - check under things."
    elif game_state.door_opened and game_state.rug_lifted and not game_state.key_taken:
        hint = "You can see both your obstacle and a potential solution. Pick up what you found and see what it opens."
    elif game_state.door_opened and game_state.key_taken and not game_state.safe_opened:
        hint = "The bars block your exit, but that key must open something in this room. What else has a lock?"
    elif game_state.safe_opened and not game_state.bolt_cutter_taken:
        hint = "The safe revealed exactly what you need! Take that tool - it looks perfect for your problem."
    elif game_state.bolt_cutter_taken and not game_state.bars_cut:
        hint = "You have the perfect tool for those metal bars blocking your escape. Time to put it to work!"
    elif not game_state.door_opened and game_state.safe_opened:
        hint = "You have a powerful tool now. Maybe see what's behind that door - you might need to cut through something."
    elif game_state.bars_cut:
        hint = "You've already found your way to freedom! The path is clear."
    else:
        if not game_state.door_opened:
            hint = "Start by opening that door to see what you're up against."
        elif not game_state.rug_lifted:
            hint = "Search the room carefully. Check under anything that looks moveable."
        elif not game_state.key_taken:
            hint = "You found something useful - make sure to pick it up!"
        elif not game_state.safe_opened:
            hint = "That key must fit somewhere in this room. Look for something else that's locked."
        elif not game_state.bolt_cutter_taken:
            hint = "Take that tool from the safe - you're going to need it!"
        else:
            hint = "You have everything you need. Use your tool on what's blocking your escape!"
    
    response_data = {
        "success": True,
        "message": hint,
        "image": escape_composer.compose_room_image(game_state)
    }
    logger.info(f"DEBUG: give_hint returning: {response_data['message'][:50]}...")
    return response_data

# Pydantic model for the 'impossible_action' input
class ImpossibleActionInput(BaseModel):
    action: str = Field(
        "do something impossible",
        description="The player's original phrase that led to an impossible action."
    )

@app.post(
    "/impossible_action",
    operation_id="impossible_action",
    summary="For actions that don't work or aren't possible.",
    description="When calling this tool, pass the player's original phrase as the 'action' parameter."
)
async def impossible_action(input: ImpossibleActionInput) -> Dict[str, Any]:
    logger.info(f"API call: impossible_action (action: {input.action})")
    
    response_data = {
        "success": False,
        "message": "That's not possible right now.",
        "image": escape_composer.compose_room_image(game_state)
    }
    logger.info(f"DEBUG: impossible_action returning: {response_data['message'][:50]}...")
    return response_data

# Pydantic model for the 'multiple_actions' input
class MultipleActionsInput(BaseModel):
    primary_action: str = Field(
        "open_door",
        description="The primary/first action to execute, exactly as it appears in the MCP tool list."
    )

@app.post(
    "/multiple_actions",
    operation_id="multiple_actions",
    summary="For when player requests multiple actions at once.",
    description="Pass the primary/first action to execute as 'primary_action' parameter, exactly how it appears in the MCP tool list."
)
async def multiple_actions(input: MultipleActionsInput) -> Dict[str, Any]:
    logger.info(f"API call: multiple_actions (primary_action: {input.primary_action})")
    
    action_map = {
        "open_door": open_door,
        "look_under_rug": look_under_rug,
        "take_key": take_key,
        "open_safe": open_safe,
        "take_bolt_cutter": take_bolt_cutter,
        "cut_bars": cut_bars,
        "use_key_on_door": use_key_on_door,
        "use_bolt_cutter_on_door": use_bolt_cutter_on_door,
        "give_hint": give_hint,
        "impossible_action": impossible_action,
        "reset_game": reset_game
    }
    
    if input.primary_action in action_map:
        logger.info(f"DEBUG: multiple_actions calling mapped function: {input.primary_action}")
        # Pass input if the target function expects it (e.g., impossible_action, multiple_actions itself)
        if input.primary_action in ["impossible_action", "multiple_actions"]:
            result = await action_map[input.primary_action](input)
        else:
            result = await action_map[input.primary_action]()
        
        result_data = result
    else:
        logger.warning(f"DEBUG: multiple_actions received unmapped primary_action: {input.primary_action}. Falling back to impossible_action.")
        result_data = await impossible_action(ImpossibleActionInput(action=input.primary_action))
    
    original_message = result_data["message"]
    result_data["message"] = f"MULTIPLE_ACTIONS_DETECTED: We can only do one thing at a time. I executed '{input.primary_action}' first. RESULT: {original_message}"
    
    logger.info(f"DEBUG: multiple_actions returning: {result_data['message'][:50]}...")
    return result_data

@app.post(
    "/reset_game",
    operation_id="reset_game",
    summary="Resets the game state to its initial configuration.",
    description="Use this tool to restart the escape room game from the beginning."
)
async def reset_game() -> Dict[str, Any]:
    logger.info("API call: reset_game")
    game_state.reset()
    response_data = {
        "success": True,
        "message": "The game has been reset. You are back in the initial room.",
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    }
    logger.info(f"DEBUG: reset_game returning: {response_data['message'][:50]}...")
    return response_data


# --- IMPORTANT: FastApiMCP initialization and mounting MUST be AFTER all endpoint definitions ---
from fastapi_mcp import FastApiMCP # Moved import here
mcp = FastApiMCP(app)
mcp.mount_http()

# --- DEBUG: Print registered MCP tools by inspecting FastAPI's OpenAPI schema ---
@app.on_event("startup")
async def startup_event():
    logger.info("--- SERVER STARTUP DEBUG ---")
    logger.info("Attempting to list tools from FastAPI's internal OpenAPI schema...")
    
    openapi_schema = app.openapi()
    
    found_operation_ids = []
    for path, path_data in openapi_schema.get("paths", {}).items():
        for method, method_data in path_data.items():
            operation_id = method_data.get("operationId")
            if operation_id:
                found_operation_ids.append(operation_id)
                
    if found_operation_ids:
        logger.info(f"DEBUG: FastAPI OpenAPI schema contains {len(found_operation_ids)} operation_ids (potential MCP tools): {found_operation_ids}")
    else:
        logger.warning("DEBUG: FastAPI OpenAPI schema contains NO operation_ids. This is the root cause if client sees empty tools.")
    
    logger.info("Please check http://localhost:8000/docs for a visual list of exposed FastAPI endpoints.")
    logger.info("FastAPI-MCP converts these to MCP tools based on these operation_ids.")
    logger.info("--- END SERVER STARTUP DEBUG ---")


# Run the FastAPI application using uvicorn
if __name__ == "__main__":
    logger.info("🚪 Starting 'Behind Bars' Escape Room FastAPI-MCP Server...")
    logger.info("Required assets (all 1280x720 PNG):")
      
    required_assets = [
        "room_base.png              # Base room background",
        "door_closed.png            # Closed door overlay",
        "door_open_bars.png         # Open door with bars blocking",
        "door_open_bars_cut.png     # Open door with bars cut (escape route)",
        "rug_normal.png             # Rug in normal position",  
        "rug_lifted_key.png         # Rug lifted with key visible",
        "rug_lifted_empty.png       # Rug lifted, key taken",
        "safe_closed.png            # Closed safe overlay",
        "safe_open_tool.png         # Open safe with bolt cutter visible",
        "safe_open_empty.png        # Open safe, tool taken",
        "inventory_key.png          # Key icon in inventory area",
        "inventory_bolt_cutter.png  # Bolt cutter icon in inventory area"
    ]
      
    for asset in required_assets:
        logger.info(f"  ./assets/{asset}")
      
    logger.info("\nGame progression:")
    logger.info("  1. open_door → see bars blocking exit")
    logger.info("  2. look_under_rug → find key")  
    logger.info("  3. open_safe (auto-grabs key if needed) → reveal bolt cutter")
    logger.info("  4. cut_bars (auto-grabs bolt cutter if needed) → ESCAPE!")
    logger.info("\nServer will be available at http://localhost:8000")
    logger.info("MCP tools will be exposed at http://localhost:8000/mcp")
    logger.info("Swagger UI for API documentation at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
