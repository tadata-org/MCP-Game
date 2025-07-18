# server/behind_bars_server.py
from typing import Any
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
import json
import base64
from PIL import Image
import io
import os
import logging

#logging.basicConfig(level=logging.INFO)
logging.disable(logging.CRITICAL)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("behind-bars-escape")

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

# Global game state
game_state = GameState()

# Image Composer
class EscapeImageComposer:
    def __init__(self):
        server_dir = os.path.dirname(os.path.abspath(__file__))
        self.assets_path = os.path.join(server_dir, "assets")
        self.asset_cache = {}
        self.canvas_size = (1280, 720)
        logger.info(f"Escape room image composer initialized: {self.assets_path}")
        
    def load_asset(self, filename: str) -> Image.Image:
        if filename in self.asset_cache:
            return self.asset_cache[filename]
            
        filepath = os.path.join(self.assets_path, filename)
        
        if os.path.exists(filepath):
            logger.debug(f"Loading {filename}")
            img = Image.open(filepath)
            
            if img.size != self.canvas_size:
                logger.warning(f"{filename} is {img.size}, resizing to {self.canvas_size}")
                img = img.resize(self.canvas_size, Image.Resampling.LANCZOS)
            
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            self.asset_cache[filename] = img
            return img
        else:
            logger.warning(f"Missing asset: {filename}")
            placeholder = Image.new('RGBA', self.canvas_size, (0, 0, 0, 0))
            return placeholder
    
    def compose_room_image(self, state: GameState) -> str:
        """Compose escape room image based on game state"""
        logger.info("🚪 COMPOSING ESCAPE ROOM")
        logger.info(f"📊 State: {state.to_dict()}")
        
        layers_applied = []
        
        # Base room (always present)
        final_image = self.load_asset("room_base.png").copy()
        layers_applied.append("✅ room_base.png (base room)")
        
        # Door state
        if state.door_opened:
            if state.bars_cut:
                # Door open with bars cut - escape route visible
                door_overlay = self.load_asset("door_open_bars_cut.png")
                layers_applied.append("✅ door_open_bars_cut.png (ESCAPE ROUTE!)")
            else:
                # Door open but bars still intact
                door_overlay = self.load_asset("door_open_bars.png")
                layers_applied.append("✅ door_open_bars.png (blocked by bars)")
        else:
            # Door closed
            door_overlay = self.load_asset("door_closed.png")
            layers_applied.append("✅ door_closed.png (door closed)")
        
        final_image = Image.alpha_composite(final_image, door_overlay)
        
        # Rug state
        if state.rug_lifted:
            if state.key_taken:
                # Rug lifted, key taken
                rug_overlay = self.load_asset("rug_lifted_empty.png")
                layers_applied.append("✅ rug_lifted_empty.png (key taken)")
            else:
                # Rug lifted, key visible
                rug_overlay = self.load_asset("rug_lifted_key.png")
                layers_applied.append("✅ rug_lifted_key.png (KEY VISIBLE)")
        else:
            # Rug not lifted
            rug_overlay = self.load_asset("rug_normal.png")
            layers_applied.append("✅ rug_normal.png (rug in place)")
        
        final_image = Image.alpha_composite(final_image, rug_overlay)
        
        # Safe state
        if state.safe_opened:
            if state.bolt_cutter_taken:
                # Safe open, bolt cutter taken
                safe_overlay = self.load_asset("safe_open_empty.png")
                layers_applied.append("✅ safe_open_empty.png (tool taken)")
            else:
                # Safe open, bolt cutter visible
                safe_overlay = self.load_asset("safe_open_tool.png")
                layers_applied.append("✅ safe_open_tool.png (BOLT CUTTER VISIBLE)")
        else:
            # Safe closed
            safe_overlay = self.load_asset("safe_closed.png")
            layers_applied.append("✅ safe_closed.png (safe locked)")
        
        final_image = Image.alpha_composite(final_image, safe_overlay)
        
        # Inventory overlays
        if "key" in state.inventory:
            key_inv = self.load_asset("inventory_key.png")
            final_image = Image.alpha_composite(final_image, key_inv)
            layers_applied.append("✅ inventory_key.png (carrying key)")
        
        if "bolt_cutter" in state.inventory:
            tool_inv = self.load_asset("inventory_bolt_cutter.png")
            final_image = Image.alpha_composite(final_image, tool_inv)
            layers_applied.append("✅ inventory_bolt_cutter.png (carrying tool)")
        
        # Print composition summary
        logger.info("🚪 ESCAPE ROOM COMPOSITION:")
        for i, layer in enumerate(layers_applied, 1):
            logger.info(f"   {i}. {layer}")
        
        # Convert to base64
        try:
            rgb_image = Image.new('RGB', self.canvas_size, (255, 255, 255))
            rgb_image.paste(final_image, mask=final_image.split()[-1])
            
            buffer = io.BytesIO()
            rgb_image.save(buffer, format='PNG', optimize=True, quality=95)
            image_data = base64.b64encode(buffer.getvalue()).decode()
            
            logger.info(f"✅ Generated escape room image ({len(image_data)} chars)")
            return image_data
            
        except Exception as e:
            logger.error(f"❌ Failed to encode escape room image: {e}")
            return ""

# Global image composer
escape_composer = EscapeImageComposer()

# MCP Tools
@mcp.tool(
    name="open_door",
    description="Opens the door to see what's behind it. Possible user prompts: open the door, look behind the door, check the door pls, etc."
)
def open_door() -> str:
    logger.info("Opening door")
    
    if game_state.door_opened:
        if game_state.bars_cut:
            return json.dumps({
                "success": True,
                "message": "The door is already open, and you've cut through the bars. Freedom awaits!",
                "image": escape_composer.compose_room_image(game_state)
            })
        else:
            return json.dumps({
                "success": True,
                "message": "The door is already open, but metal bars block your path.",
                "image": escape_composer.compose_room_image(game_state)
            })
    
    # Open the door for the first time
    game_state.door_opened = True
    
    return json.dumps({
        "success": True,
        "message": "You open the door, but your heart sinks. Thick metal bars block your escape! You'll need to find another way through.",
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="look_under_rug",
    description="Lift the rug to see what's underneath. Possible user prompts: remove rug, check below rug, throw away rug, move rug to the side, etc."
)
def look_under_rug() -> str:
    logger.info("Looking under rug")
    
    if game_state.rug_lifted:
        if game_state.key_taken:
            return json.dumps({
                "success": True,
                "message": "You've already lifted the rug and taken the key from underneath.",
                "image": escape_composer.compose_room_image(game_state)
            })
        else:
            return json.dumps({
                "success": True,
                "message": "The rug is lifted, revealing the key underneath.",
                "image": escape_composer.compose_room_image(game_state)
            })
    
    # Lift the rug for the first time
    game_state.rug_lifted = True
    
    return json.dumps({
        "success": True,
        "message": "You lift the corner of the rug and discover a small brass key hidden underneath!",
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="take_key",
    description="Pick up the key from under the rug. Possible user prompts: pick up/take/steal/grab the key, etc. "
)
def take_key() -> str:
    logger.info("Taking key")
    
    if game_state.key_taken:
        return json.dumps({
            "success": False,
            "message": "You already have the key.",
            "image": escape_composer.compose_room_image(game_state)
        })
    
    if not game_state.rug_lifted:
        return json.dumps({
            "success": False,
            "message": "You don't see any key. Maybe you should look under the rug first?",
            "image": escape_composer.compose_room_image(game_state)
        })
    
    # Take the key
    game_state.key_taken = True
    game_state.inventory.append("key")
    
    return json.dumps({
        "success": True,
        "message": "You pick up the brass key. It feels solid and well-made.",
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="open_safe",
    description="Use the key to open the safe. Possible user prompts: look inside safe, open safe, look inside valut, inspect vault, etc. "
)
def open_safe() -> str:
    logger.info("Opening safe")
    
    if game_state.safe_opened:
        if game_state.bolt_cutter_taken:
            return json.dumps({
                "success": True,
                "message": "The safe is already open and empty. You've taken the bolt cutter.",
                "image": escape_composer.compose_room_image(game_state)
            })
        else: return take_bolt_cutter()
            # return json.dumps({
            #     "success": True,
            #     "message": "The safe is already open, revealing a heavy-duty bolt cutter inside.",
            #     "image": escape_composer.compose_room_image(game_state)
            # })
    
    if "key" not in game_state.inventory:
        return json.dumps({
            "success": False,
            "message": "The safe is locked.",
            "image": escape_composer.compose_room_image(game_state)
        })
    
    # Open the safe
    game_state.safe_opened = True
    
    return json.dumps({
        "success": True,
        "message": "You insert the key into the safe's lock. It turns smoothly! The safe opens with a satisfying click, revealing a heavy-duty bolt cutter inside.",
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="take_bolt_cutter",
    description="This takes the bolt cutter from the safe/vault. Possible user prompts that relate to this: pick up the tool, grab the bolt cutter, take the item inside box, take the thing inside the safe,pick up the heavy-duty bolt cutter inside the safe, etc."
)
def take_bolt_cutter() -> str:
    logger.info("Taking bolt cutter")
    
    if game_state.bolt_cutter_taken:
        return json.dumps({
            "success": False,
            "message": "You already have the bolt cutter.",
            "image": escape_composer.compose_room_image(game_state)
        })
    
    if not game_state.safe_opened:
        return json.dumps({
            "success": False,
            "message": "The safe is locked. ",
            "image": escape_composer.compose_room_image(game_state)
        })
    
    # Take the bolt cutter
    game_state.bolt_cutter_taken = True
    game_state.inventory.append("bolt_cutter")
    
    return json.dumps({
        "success": True,
        "message": "You lift the heavy bolt cutter from the safe. Its weight feels reassuring.",
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="cut_bars",
    description="Use the bolt cutter to cut through the metal bars. Possible user prompts: break the bars, cut the bars, open the bars, etc."
)
def cut_bars() -> str:
    logger.info("Cutting bars")
    
    if game_state.bars_cut:
        return json.dumps({
            "success": True,
            "message": "You've already cut through the bars. The path to freedom is clear!",
            "image": escape_composer.compose_room_image(game_state),
            "won": True
        })
    
    if not game_state.door_opened:
        return json.dumps({
            "success": False,
            "message": "You need to open the door first to see the bars.",
            "image": escape_composer.compose_room_image(game_state)
        })
    
    if "bolt_cutter" not in game_state.inventory:
        return json.dumps({
            "success": False,
            "message": "You don't have anything to cut the bars with.",
            "image": escape_composer.compose_room_image(game_state)
        })
    
    # Cut the bars - ESCAPE!
    game_state.bars_cut = True
    game_state.escaped = True
    
    return json.dumps({
        "success": True,
        "message": "You position the bolt cutter on the metal bars and squeeze with all your might. SNAP! The bars give way with a satisfying crack. You've created an opening large enough to escape through. Freedom at last!",
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict(),
        "won": True
    })

@mcp.tool(
    name="describe_room",
    description="Returns a description of the current state of the room. Good to call this tool, if, for example, the users prompt suggests forgetting parts of the current state."
)
def describe_room() -> str:
    logger.info("Describing escape room")
    
    desc = "You stand in a simple room with concrete walls. "
    
    # Describe door
    if game_state.door_opened:
        if game_state.bars_cut:
            desc += "The door is open and you've cut through the metal bars - your escape route is clear! "
        else:
            desc += "The door is open, but thick metal bars block your path. "
    else:
        desc += "A heavy door dominates one wall. "
    
    # Describe rug
    if game_state.rug_lifted:
        if game_state.key_taken:
            desc += "The rug is lifted in one corner, revealing the empty hiding spot where you found the key. "
        else:
            desc += "The rug is lifted, revealing a brass key underneath. "
    else:
        desc += "A worn rug covers part of the floor. "
    
    # Describe safe
    if game_state.safe_opened:
        if game_state.bolt_cutter_taken:
            desc += "The safe stands open and empty - you've taken its contents. "
        else:
            desc += "The safe is open, revealing a heavy bolt cutter inside. "
    else:
        desc += "A metal safe sits against the wall, securely locked. "
    
    # Describe inventory
    if game_state.inventory:
        desc += f"You're carrying: {', '.join(game_state.inventory)}. "
    
    # Win condition
    if game_state.escaped:
        desc += "You have successfully escaped the room!"
    
    return json.dumps({
        "success": True,
        "message": desc.strip(),
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict(),
        "won": game_state.escaped
    })

# @mcp.tool(
#     name="reset_escape_room",
#     description="Reset the escape room to start over"
# )
def reset_escape_room() -> str:
    global game_state
    logger.info("Resetting escape room")
    
    game_state = GameState()
    
    return json.dumps({
        "success": True,
        "message": "The room resets itself. The door closes, the rug settles back into place, the safe locks, and your inventory empties. You can start your escape attempt again.",
        "image": escape_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })


@mcp.tool(
    name="impossible_action",
    description="Handle any action that isn't possible (that doesn't have a specific tool) - use this as a catch-all for all impossible actions"
)
def impossible_action(action: str = "do something impossible") -> str:
    logger.info(f"Impossible action attempted: {action}")
    
    # Some variety in responses
    responses = [
        f"You try to {action}, but that's not going to work in this situation.",
        f"Yikes! You can't {action} here.",
        f"Nice try, but {action} isn't possible right now.",
        f"You attempt to {action}, but nothing happens.",
        f"That's creative, but {action} won't help you escape.",
    ]
    
    import random
    selected_response = random.choice(responses)
    
    return json.dumps({
        "success": False,
        "message": selected_response,
        "image": escape_composer.compose_room_image(game_state)
    })

if __name__ == "__main__":
    logger.info("🚪 Starting 'Behind Bars' Escape Room MCP Server...")
    logger.info("Required assets (all 1920x1080 PNG):")
    
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
    logger.info("  3. take_key → add to inventory")
    logger.info("  4. open_safe → reveal bolt cutter")
    logger.info("  5. take_bolt_cutter → add to inventory")
    logger.info("  6. cut_bars → ESCAPE!")
    
    mcp.run(transport="stdio")