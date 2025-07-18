# server/game_server.py
from typing import Any
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
import json
import base64
from PIL import Image
import io
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("simple-escape-room")

# Simple Game State
class GameState:
    def __init__(self):
        self.doors = {1: False, 2: False, 3: False}  # False = closed, True = open
        self.key_taken = False
        self.safe_unlocked = False
        self.safe_opened = False
        self.has_key = False
    
    def to_dict(self):
        return {
            "doors": self.doors,
            "key_taken": self.key_taken,
            "safe_unlocked": self.safe_unlocked,
            "safe_opened": self.safe_opened,
            "has_key": self.has_key
        }

# Global game state
game_state = GameState()

# Image Composer for 1920x1080 assets
class ImageComposer:
    def __init__(self, assets_path: str = "./assets"):
        self.assets_path = assets_path
        self.asset_cache = {}
        self.canvas_size = (1920, 1080)  # Fixed size for all assets
        logger.info(f"Image composer initialized for {self.canvas_size} assets")
        
    def load_asset(self, filename: str) -> Image.Image:
        """Load and cache a 1920x1080 RGBA asset"""
        if filename in self.asset_cache:
            return self.asset_cache[filename]
            
        filepath = os.path.join(self.assets_path, filename)
        
        if os.path.exists(filepath):
            logger.info(f"Loading {filename}")
            img = Image.open(filepath)
            
            # Ensure image is correct size
            if img.size != self.canvas_size:
                logger.warning(f"{filename} is {img.size}, resizing to {self.canvas_size}")
                img = img.resize(self.canvas_size, Image.Resampling.LANCZOS)
            
            # Ensure RGBA mode for transparency support
            if img.mode != 'RGBA':
                logger.info(f"Converting {filename} from {img.mode} to RGBA")
                img = img.convert('RGBA')
            
            self.asset_cache[filename] = img
            return img
        else:
            logger.warning(f"Missing asset: {filename} - creating placeholder")
            # Create transparent placeholder
            placeholder = Image.new('RGBA', self.canvas_size, (0, 0, 0, 0))
            return placeholder
    
    def compose_room_image(self, state: GameState) -> str:
        """Compose final room image with proper transparency handling"""
        logger.info(f"🎨 STARTING IMAGE COMPOSITION")
        logger.info(f"📊 Game state: {state.to_dict()}")
        
        layers_applied = []  # Track what we actually add
        
        # Start with base room image (should be opaque background)
        try:
            final_image = self.load_asset("room_base.png").copy()
            layers_applied.append("✅ room_base.png (background)")
            logger.info(f"🖼️  Base image loaded: {final_image.size}, mode: {final_image.mode}")
        except Exception as e:
            logger.error(f"❌ Failed to load room_base.png: {e}")
            final_image = Image.new('RGBA', self.canvas_size, (44, 24, 16, 255))
            layers_applied.append("❌ room_base.png (using fallback)")
        
        # Layer 1: Doors - each door overlay should have transparent areas
        logger.info("🚪 Adding door layers...")
        for door_num in [1, 2, 3]:
            try:
                if state.doors[door_num]:
                    # Door is open - show open door overlay
                    door_asset = f"door{door_num}_open.png"
                    door_overlay = self.load_asset(door_asset)
                    final_image = Image.alpha_composite(final_image, door_overlay)
                    layers_applied.append(f"✅ {door_asset} (door {door_num} OPEN)")
                    logger.info(f"   🔓 Added {door_asset}")
                else:
                    # Door is closed - show closed door overlay
                    door_asset = f"door{door_num}_closed.png"
                    door_overlay = self.load_asset(door_asset)
                    final_image = Image.alpha_composite(final_image, door_overlay)
                    layers_applied.append(f"✅ {door_asset} (door {door_num} CLOSED)")
                    logger.info(f"   🔒 Added {door_asset}")
            except Exception as e:
                logger.error(f"❌ Failed to add door {door_num} layer: {e}")
                layers_applied.append(f"❌ door{door_num} layer failed")
        
        # Layer 2: Key (only visible if door 2 is open and key not taken)
        logger.info("🔑 Checking key visibility...")
        if state.doors[2] and not state.key_taken:
            try:
                key_overlay = self.load_asset("key_behind_door2.png")
                final_image = Image.alpha_composite(final_image, key_overlay)
                layers_applied.append("✅ key_behind_door2.png (KEY VISIBLE)")
                logger.info("   🔑 Added key_behind_door2.png")
            except Exception as e:
                logger.error(f"❌ Failed to add key layer: {e}")
                layers_applied.append("❌ key_behind_door2.png failed")
        else:
            logger.info(f"   🚫 Key not visible (door2_open: {state.doors[2]}, key_taken: {state.key_taken})")
            layers_applied.append("🚫 key_behind_door2.png (not visible)")
        
        # Layer 3: Safe state
        logger.info("🔒 Adding safe layer...")
        try:
            if state.safe_opened:
                safe_asset = "safe_open.png"
                safe_state_desc = "OPEN"
            elif state.safe_unlocked:
                safe_asset = "safe_unlocked.png"
                safe_state_desc = "UNLOCKED"
            else:
                safe_asset = "safe_locked.png"
                safe_state_desc = "LOCKED"
            
            safe_overlay = self.load_asset(safe_asset)
            final_image = Image.alpha_composite(final_image, safe_overlay)
            layers_applied.append(f"✅ {safe_asset} (safe {safe_state_desc})")
            logger.info(f"   🔒 Added {safe_asset} (safe {safe_state_desc})")
            
        except Exception as e:
            logger.error(f"❌ Failed to add safe layer: {e}")
            layers_applied.append("❌ safe layer failed")
        
        # Layer 4: Inventory overlay (if player has key)
        logger.info("🎒 Checking inventory...")
        if state.has_key:
            try:
                inventory_overlay = self.load_asset("inventory_key.png")
                final_image = Image.alpha_composite(final_image, inventory_overlay)
                layers_applied.append("✅ inventory_key.png (PLAYER HAS KEY)")
                logger.info("   🎒 Added inventory_key.png")
            except Exception as e:
                logger.error(f"❌ Failed to add inventory layer: {e}")
                layers_applied.append("❌ inventory_key.png failed")
        else:
            logger.info("   🚫 No inventory (player doesn't have key)")
            layers_applied.append("🚫 inventory_key.png (no key)")
        
        # Print final layer summary
        logger.info("🎨 FINAL COMPOSITION SUMMARY:")
        for i, layer in enumerate(layers_applied, 1):
            logger.info(f"   {i}. {layer}")
        
        # Convert to base64
        try:
            logger.info("💾 Converting to base64...")
            # Convert RGBA to RGB for PNG output (with white background)
            rgb_image = Image.new('RGB', self.canvas_size, (255, 255, 255))
            rgb_image.paste(final_image, mask=final_image.split()[-1])  # Use alpha as mask
            
            # Save to buffer
            buffer = io.BytesIO()
            rgb_image.save(buffer, format='PNG', optimize=True, quality=95)
            image_data = base64.b64encode(buffer.getvalue()).decode()
            
            logger.info(f"✅ Generated {len(image_data)} character base64 image")
            logger.info(f"🎨 COMPOSITION COMPLETE - {len(layers_applied)} layers applied")
            return image_data
            
        except Exception as e:
            logger.error(f"❌ Failed to encode image: {e}")
            return ""

# Global image composer (assets relative to server file location)
server_dir = os.path.dirname(os.path.abspath(__file__))
assets_path = os.path.join(server_dir, "assets")
image_composer = ImageComposer(assets_path)

# Input schemas
class DoorInput(BaseModel):
    door_id: int = Field(description="Door number: 1, 2, or 3")

class CodeInput(BaseModel):
    code: str = Field(description="4-digit code")

# MCP Tools
@mcp.tool(
    name="look_behind_door",
    description="Look behind a specific door (opens it)"
)
def look_behind_door(input: DoorInput) -> str:
    door_id = input.door_id
    logger.info(f"Looking behind door {door_id}")
    
    if door_id not in [1, 2, 3]:
        return json.dumps({
            "success": False,
            "message": "Invalid door number. Must be 1, 2, or 3.",
            "image": image_composer.compose_room_image(game_state)
        })
    
    if game_state.doors[door_id]:
        return json.dumps({
            "success": False,
            "message": f"Door {door_id} is already open.",
            "image": image_composer.compose_room_image(game_state)
        })
    
    # Open the door
    game_state.doors[door_id] = True
    
    # Different messages for different doors
    if door_id == 1:
        message = "Door 1 swings open with a creak. Nothing behind it but empty darkness."
    elif door_id == 2:
        message = "Door 2 opens to reveal a rusty key lying on the ground behind it!"
    else:  # door 3
        message = "Door 3 creaks open. Just shadows and dust behind it."
    
    return json.dumps({
        "success": True,
        "message": message,
        "image": image_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="take_key",
    description="Take the key if it's visible"
)
def take_key() -> str:
    logger.info("Attempting to take key")
    
    if game_state.key_taken:
        return json.dumps({
            "success": False,
            "message": "You already have the key.",
            "image": image_composer.compose_room_image(game_state)
        })
    
    if not game_state.doors[2]:
        return json.dumps({
            "success": False,
            "message": "You don't see any key. Try looking behind the doors first.",
            "image": image_composer.compose_room_image(game_state)
        })
    
    # Take the key
    game_state.key_taken = True
    game_state.has_key = True
    
    return json.dumps({
        "success": True,
        "message": "You pick up the rusty key. It feels heavy and cold in your hand.",
        "image": image_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="use_key_on_safe",
    description="Use the key to unlock the safe"
)
def use_key_on_safe() -> str:
    logger.info("Attempting to use key on safe")
    
    if not game_state.has_key:
        return json.dumps({
            "success": False,
            "message": "You don't have a key to use.",
            "image": image_composer.compose_room_image(game_state)
        })
    
    if game_state.safe_unlocked:
        return json.dumps({
            "success": False,
            "message": "The safe is already unlocked.",
            "image": image_composer.compose_room_image(game_state)
        })
    
    # Unlock the safe
    game_state.safe_unlocked = True
    
    return json.dumps({
        "success": True,
        "message": "You insert the key into the safe's lock. Click! The safe unlocks and the keypad lights up green. You notice a piece of paper inside with the code: 5274",
        "image": image_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="enter_code",
    description="Enter a 4-digit code into the safe"
)
def enter_code(input: CodeInput) -> str:
    code = input.code
    logger.info(f"Entering code: {code}")
    
    if not game_state.safe_unlocked:
        return json.dumps({
            "success": False,
            "message": "The safe is still locked. You need to unlock it with a key first.",
            "image": image_composer.compose_room_image(game_state)
        })
    
    if game_state.safe_opened:
        return json.dumps({
            "success": False,
            "message": "The safe is already open!",
            "image": image_composer.compose_room_image(game_state)
        })
    
    if code == "5274":
        # Correct code - win the game!
        game_state.safe_opened = True
        return json.dumps({
            "success": True,
            "message": "SUCCESS! The safe door swings open wide, revealing bright daylight beyond. You've escaped!",
            "image": image_composer.compose_room_image(game_state),
            "state": game_state.to_dict(),
            "won": True
        })
    else:
        return json.dumps({
            "success": False,
            "message": f"You enter {code}. The safe beeps and flashes red. Wrong code!",
            "image": image_composer.compose_room_image(game_state)
        })

@mcp.tool(
    name="describe_room",
    description="Get description and image of current room state"
)
def describe_room() -> str:
    logger.info("Describing room")
    
    description = "You stand in a dimly lit escape room. "
    
    # Describe doors
    open_doors = [str(i) for i in [1, 2, 3] if game_state.doors[i]]
    closed_doors = [str(i) for i in [1, 2, 3] if not game_state.doors[i]]
    
    if closed_doors:
        description += f"Doors {', '.join(closed_doors)} are closed. "
    if open_doors:
        description += f"Doors {', '.join(open_doors)} stand open. "
    
    # Describe key
    if game_state.doors[2] and not game_state.key_taken:
        description += "A rusty key lies behind door 2. "
    elif game_state.has_key:
        description += "You're holding a rusty key. "
    
    # Describe safe
    if game_state.safe_opened:
        description += "The safe is wide open, showing your escape route!"
    elif game_state.safe_unlocked:
        description += "The safe is unlocked and ready for a code."
    else:
        description += "A metal safe sits against the wall, locked tight."
    
    return json.dumps({
        "success": True,
        "message": description,
        "image": image_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

@mcp.tool(
    name="reset_game",
    description="Reset the game to initial state"
)
def reset_game() -> str:
    global game_state
    logger.info("Resetting game")
    
    game_state = GameState()
    
    return json.dumps({
        "success": True,
        "message": "Game reset! You're back in the escape room.",
        "image": image_composer.compose_room_image(game_state),
        "state": game_state.to_dict()
    })

if __name__ == "__main__":
    logger.info("Starting escape room MCP server...")
    logger.info("Required assets (all 1920x1080 PNG):")
    
    required_assets = [
        "room_base.png           # Opaque background room",
        "door1_closed.png        # Door 1 closed overlay (transparent background)",
        "door1_open.png          # Door 1 open overlay (transparent background)",
        "door2_closed.png        # Door 2 closed overlay (transparent background)",
        "door2_open.png          # Door 2 open overlay (transparent background)",
        "door3_closed.png        # Door 3 closed overlay (transparent background)",
        "door3_open.png          # Door 3 open overlay (transparent background)",
        "key_behind_door2.png    # Key sprite (transparent background)",
        "safe_locked.png         # Safe locked overlay (transparent background)",
        "safe_unlocked.png       # Safe unlocked overlay (transparent background)",
        "safe_open.png           # Safe open overlay (transparent background)",
        "inventory_key.png       # Key icon in inventory area (transparent background)"
    ]
    
    for asset in required_assets:
        logger.info(f"  ./assets/{asset}")
    
    mcp.run(transport="stdio")