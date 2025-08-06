# client/game_client.py
import asyncio
import sys
import json
import base64
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
from PIL import Image
import io

# Removed specific imports for TextContent, StructuredContent, ImageContent
# We will rely on the .type attribute (string) of the content object.
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# FIRST LLM: Tool Selection
TOOL_SELECTOR_PROMPT = """
You are a tool selector for an escape room game. Your only job is to pick which MCP tool to call based on the user's input.

Pick the most appropriate tool from the available list. Call exactly ONE tool - never explain or suggest, just pick and call.

If the user query corresponds to a single action, call that action. 
If the user query corresponds to wanting a hint, call the give_hint tool.
If the user query corresponds to wanting to do multiple actions at once, call the multiple_actions tool.
If the query is not a valid action, call the impossible_action tool.
"""

# SECOND LLM: Storytelling (for actions)
STORYTELLER_PROMPT = """
You are a creative narrator for an escape room game. You will receive:
1. What the player tried to do
2. The factual result from the game

Your job: Rewrite the factual result to be more engaging and atmospheric while keeping all the same information.

RULES:
- Keep all factual information exactly the same
- Don't add new game mechanics, items, or rooms
- Don't hint at solutions the player hasn't discovered  
- Make it more immersive and story-like
- Keep the same success/failure outcome
- MAXIMUM 2 sentences and under 40 words
- Use vivid but appropriate language

Transform dry responses into engaging narrative while preserving all facts.
"""

# SECOND LLM: Multiple Actions Handler
MULTIPLE_ACTIONS_PROMPT = """
You are handling a situation where a player tried to do multiple things at once in an escape room game. You will receive:
1. What the player originally tried to do
2. The result from executing just ONE of those actions

Your job: Explain that we can only do one thing at a time, mention what we did, and present the result engagingly.

RULES:
- Start with something like "It seems you tried to do multiple things at once. Let's go one step at a time" or "I can only do one thing in one time"
- Clearly state what action you took first
- Then give the engaging result of that action
- Keep it under 40 words total
- Use a helpful, guiding tone

Example: "Let's go one step at a time. For now, I opened the door. Your heart sinks as thick metal bars block your escape!"
"""
HINT_PROMPT = """
You are a helpful assistant providing hints for an escape room game. You will receive a hint from the game.

Your job: Make the hint clear, direct, and encouraging while keeping it brief.

RULES:
- Keep the exact same hint information 
- Use a warm, encouraging tone
- Be straightforward - no dramatic storytelling
- Start with something like "Everyone gets stuck sometimes" or "Here's a hint to help you progress"
- Keep it under 30 words
- Don't add new information, just make the delivery friendlier

Make hints feel supportive and clear, not flowery or dramatic.
"""

class TwoLLMGameClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()

    async def connect_to_server(self, server_url: str):
        # Let AsyncExitStack manage the streamablehttp_client context
        read_stream, write_stream, _ = await self.exit_stack.enter_async_context(
            streamablehttp_client(url=server_url, headers={})
        )

        # Let AsyncExitStack manage the ClientSession context
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        await self.session.initialize()
        #print(f"✅ DEBUG: Connected to MCP server at {server_url}")

    async def process_query(self, query: str) -> Dict[str, Any]:
        """Main processing with two LLM calls"""
        #print(f"\n🎯 DEBUG: Processing '{query}'")
        
        # STEP 1: Tool Selection LLM
        tool_call = await self.select_tool(query)
        
        # STEP 2: Execute the selected tool
        tool_result = await self.execute_tool(tool_call)
        
        # STEP 3: Enhancement LLM (different prompts for hints vs actions)
        enhanced_response = await self.enhance_response(query, tool_result, tool_call["name"])
        
        final_result = {
            "message": enhanced_response,
            "image_data": tool_result.get("image_data"),
            "success": tool_result.get("success", True),
            "won": tool_result.get("won", False)
        }
        return final_result

    async def select_tool(self, query: str) -> Dict[str, Any]:
        """FIRST LLM: Select which tool to call"""
        
        # Get available tools
        response = await self.session.list_tools()
        available_tools = [
            {
                "name": tool.name,
                "description": tool.description or "No description",
                "input_schema": tool.inputSchema,
            }
            for tool in response.tools
        ]
        # --- DEBUG: Print available tools received from server ---
        #M1 received available tools from server: {[t['name'] for t in available_tools]}")
        # --- END DEBUG ---

        try:
            llm_response = self.anthropic.messages.create(
                model="claude-3-5-haiku-20241022",
                system=TOOL_SELECTOR_PROMPT,
                max_tokens=200,
                messages=[{"role": "user", "content": query}],
                tools=available_tools,
            )

            # Extract tool call
            for content in llm_response.content:
                if content.type == "tool_use":
                    selected = {
                        "name": content.name,
                        "input": content.input
                    }
                    #print(f"🤖 DEBUG: LLM1 selected '{selected['name']}' with input: {selected['input']}")
                    return selected
            
            # Fallback if no tool call
            #print("🤖 DEBUG: LLM1 no tool call, using fallback to 'impossible_action'")
            return {
                "name": "impossible_action",
                "input": {"action": query}
            }
            
        except Exception as e:
            #print(f"❌ DEBUG: LLM1 error during tool selection: {e}")
            return {
                "name": "impossible_action", 
                "input": {"action": query}
            }

    async def execute_tool(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the selected MCP tool"""
        #print(f"⚙️ DEBUG: Attempting to execute '{tool_call['name']}' with input: {tool_call['input']}")
        
        try:
            # Call the actual tool
            mcp_result = await self.session.call_tool(tool_call["name"], tool_call["input"])
            
            # --- DEBUG: Inspect raw mcp_result ---
            #print(f"DEBUG: Raw mcp_result received: {mcp_result}")
            if mcp_result.content and len(mcp_result.content) > 0:
                first_content = mcp_result.content[0]
                
                
                if hasattr(first_content, 'text'):
                    pass
                if hasattr(first_content, 'data'):
                    pass
            else:
                pass
            # --- END DEBUG ---

            result_data = {}
            if mcp_result.content and len(mcp_result.content) > 0:
                first_content = mcp_result.content[0]
                content_type_str = first_content.type # Get type as string

                if content_type_str == "structured": # Check string type for structured content
                    if hasattr(first_content, 'data'):
                        result_data = first_content.data
                    else:
                        try:
                            # Fallback: if structured type but no .data, try parsing .text as JSON
                            result_data = json.loads(first_content.text)
                        except (json.JSONDecodeError, AttributeError):
                            result_data = {"message": f"Server returned structured type but no data/parseable text: {first_content}", "success": False}
                elif content_type_str == "text": # Check string type for text content
                    try:
                        # Even if it's 'text' type, our server always returns JSON strings
                        result_data = json.loads(first_content.text)
                    except json.JSONDecodeError:
                        result_data = {"message": first_content.text, "success": False}
                elif content_type_str == "image": # Check string type for image content
                    if hasattr(first_content, 'data'):
                        result_data = {"message": "Image received.", "image": first_content.data, "success": True}
                    else:
                        result_data = {"message": "Image received, but data missing.", "success": True}
                else:
                    result_data = {"message": f"Unknown content type string received: {content_type_str}", "success": False}
            else:
                result_data = {"message": "Server returned empty response.", "success": False}

            # Prepare formatted result, ensuring all keys are present with defaults
            formatted_result = {
                "message": result_data.get("message", "No message from tool."),
                "image_data": result_data.get("image"),
                "success": result_data.get("success", True),
                "won": result_data.get("won", False),
                "is_multiple_actions": False # Default
            }

            # Special handling for multiple_actions tool
            if tool_call["name"] == "multiple_actions":
                primary_action = tool_call["input"].get("primary_action", "open_door")
                #print(f"⚙️ DEBUG: Multiple actions detected, primary: {primary_action}")
                formatted_result["is_multiple_actions"] = True
                formatted_result["primary_action"] = primary_action

            #print(f"⚙️ DEBUG: Tool execution formatted result: '{formatted_result['message'][:60]}...'")
            return formatted_result
              
        except Exception as e:
            #print(f"❌ DEBUG: Tool execution error: {e}. Returning generic failure.")
            return {
                "message": f"Something went wrong during tool execution: {str(e)}",
                "image_data": None,
                "success": False,
                "won": False,
                "is_multiple_actions": False
            }

    async def enhance_response(self, user_query: str, tool_result: Dict[str, Any], tool_name: str) -> str:
        """SECOND LLM: Enhance the response with appropriate prompt based on tool type"""
        
        factual_response = tool_result["message"]
        
        # Choose the right system prompt based on the tool/situation 
        if tool_name == "give_hint":
            system_prompt = HINT_PROMPT
            #print(f"💡 DEBUG: LLM2 using HINT prompt")
        elif tool_result.get("is_multiple_actions", False):
            system_prompt = MULTIPLE_ACTIONS_PROMPT
            #print(f"🔄 DEBUG: LLM2 using MULTIPLE_ACTIONS prompt")
        else:
            system_prompt = STORYTELLER_PROMPT
            #print(f"🎭 DEBUG: LLM2 using STORYTELLER prompt")
        
        # Build the enhancement prompt
        if tool_result.get("is_multiple_actions", False):
            primary_action = tool_result.get("primary_action", "unknown action")
            enhancement_prompt = f"""
Player tried: {user_query}
Primary action taken: {primary_action}
Game result: {factual_response}
Success: {tool_result.get("success", True)}

Explain that we can only do one thing at a time, mention what we did first, and present the result:
"""
        else:
            enhancement_prompt = f"""
Player tried: {user_query}
Game result: {factual_response}
Success: {tool_result.get("success", True)}

{"Make this hint more encouraging and direct:" if tool_name == "give_hint" else "Make this response more engaging and atmospheric:"}
"""
       #print(f"DEBUG: LLM2 enhancement prompt (first 100 chars): '{enhancement_prompt[:100]}...'")

        try:
            llm_response = self.anthropic.messages.create(
                model="claude-3-5-haiku-20241022",
                system=system_prompt,
                max_tokens=150,
                messages=[{"role": "user", "content": enhancement_prompt}]
            )
            
            enhanced = llm_response.content[0].text.strip()
            #print(f"🎭 DEBUG: LLM2 ENHANCED: '{enhanced[:50]}...'")
            return enhanced
            
        except Exception as e:
            #print(f"❌ DEBUG: LLM2 error during enhancement: {e}")
            return factual_response

    def display_image(self, image_data: str):
        """Simple image display - saves to file"""
        if not image_data:
            #print("🖼️ DEBUG: No image data to display.")
            return
              
        try:
            image_bytes = base64.b64decode(image_data)
            pil_image = Image.open(io.BytesIO(image_bytes))
            pil_image.save("current_room.png")
            #print("🖼️ DEBUG: Image saved as current_room.png")
        except Exception as e:
            #print(f"❌ DEBUG: Image display error: {e}")
            pass

    async def chat_loop(self):
        print("\n Welcome to the MCP Game")
        print("=" * 40)
        print("\n You are in an escape room, trapped. View your room and the surroundings by opening the current_room.png file. This will be updated as you play the game. Type commands to take actions that help you escape.")
        print("\n Good luck :)")

        while True:
            try:
                user_input = input("\n> ").strip()
                
                if user_input.lower() == "quit":
                    print("👋 Thanks for playing!")
                    break
                elif user_input.lower() == "restart":
                    result = await self.process_query("reset the game")
                    print(f"\n🔄 {result['message']}")
                    if result['image_data']:
                        self.display_image(result['image_data'])
                    continue
                elif not user_input:
                    continue

                # Process with two-LLM system
                result = await self.process_query(user_input)
                
                # Display enhanced result
                print(f"\n{result['message']}")
                
                if result['image_data']:
                    self.display_image(result['image_data'])
                
                # Check for win condition
                if result.get('won', False):
                    print("\n🎉 CONGRATULATIONS! YOU ESCAPED! 🎉")

            except KeyboardInterrupt:
                print("\n👋 Game interrupted. Goodbye!")
                break
            except Exception as e:
                #print(f"\n❌ DEBUG: Top-level chat loop error: {str(e)}")
                pass

    async def cleanup(self):
        await self.exit_stack.aclose()


async def main():
    server_url = "http://localhost:8000/mcp" 

    client = TwoLLMGameClient()
    
    try:
        await client.connect_to_server(server_url)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
