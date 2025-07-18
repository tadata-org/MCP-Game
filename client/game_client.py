# client/game_client.py
import asyncio
import sys
import json
import base64
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
from PIL import Image
import io

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """
You are an action parser for a simple escape room game.

1. Parse what the player wants to do
2. Call the appropriate MCP tool, if one exists
3. If there is not an MCP tool corresponding to what they said, use the catch_all impossible tool given.
"""

class SimpleGameClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()
        #self.conversation_history: List[Dict[str, Any]] = []

    async def connect_to_server(self, server_script_path: str):
        command = "python"
        server_params = StdioServerParameters(command=command, args=[server_script_path])

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        response = await self.session.list_tools()
        tools = response.tools
        #print(f"🔗 Connected to MCP server")
        #print(f"📋 Available tools: {[tool.name for tool in tools]}")

    async def process_query(self, query: str) -> Dict[str, Any]:
        #print(f"\n🎯 Processing: '{query}'")

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

        try:
            # Ask Claude to parse the action - NO CONVERSATION HISTORY
            llm_response = self.anthropic.messages.create(
                model="claude-3-5-haiku-20241022",  # Fixed model name
                system=SYSTEM_PROMPT,
                max_tokens=500,
                messages=[{"role": "user", "content": query}],  # Just current query
                tools=available_tools,
            )

            # Check what Claude wants to do
            text_content = []
            tool_calls = []
            
            for content in llm_response.content:
                if content.type == "text":
                    text_content.append(content.text)
                elif content.type == "tool_use":
                    tool_calls.append(content)

            # Execute tool calls
            if tool_calls:
                for tool_call in tool_calls:
                    #print(f"🔧 Calling MCP tool: {tool_call.name}")
                    
                    # Call the MCP server
                    mcp_result = await self.session.call_tool(tool_call.name, tool_call.input)
                    
                    # Parse the JSON response from server
                    result_data = json.loads(mcp_result.content[0].text)
                    
                    return {
                        "message": result_data["message"],
                        "image_data": result_data.get("image"),
                        "success": result_data.get("success", True),
                        "won": result_data.get("won", False)
                    }
            else:
                # No tool call, just text response
                response_text = "\n".join(text_content) if text_content else "I'm not sure what you want to do."
                
                return {
                    "message": response_text,
                    "image_data": None,
                    "success": True,
                    "won": False
                }

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            print(error_msg)
            return {
                "message": error_msg,
                "image_data": None,
                "success": False,
                "won": False
            }

    def display_image(self, image_data: str):
        """Simple image display - saves to file and tells user"""
        if not image_data:
            return
            
        try:
            # Decode base64 image
            image_bytes = base64.b64decode(image_data)
            pil_image = Image.open(io.BytesIO(image_bytes))
            
            # Save to file
            pil_image.save("current_room.png")
            #print("🖼️  Room image saved as 'current_room.png'")
            
        except Exception as e:
            print(f"❌ Image error: {e}")

    async def chat_loop(self):
        print("\n Welcome to the MCP Game")
        print("=" * 40)
        print("\n You are in a room, trapped.")
        print("\n You must escape by typing what you wish to try")
        print("\n Good luck :)")


        # print("You're trapped in a room with 3 doors and a safe.")
        # print("Try commands like:")
        # print("  - 'look behind door 1'")
        # print("  - 'take key'") 
        # print("  - 'use key on safe'")
        # print("  - 'enter code 1234'")
        # print("  - 'what do I see'")
        # print("Type 'quit' to exit or 'restart' to reset the game.")
        # print("=" * 40)
        
        # Get initial room state
        try:
            initial = await self.process_query("describe the room")
            #print(f"\n {initial['message']}")
            if initial['image_data']:
                self.display_image(initial['image_data'])
        except Exception as e:
            print(f"❌ Could not get initial state: {e}")

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

                # Process the query
                result = await self.process_query(user_input)
                
                # Display result
                print(f"\nGame Master Says: {result['message']}")
                
                if result['image_data']:
                    self.display_image(result['image_data'])
                
                # Check for win condition
                if result.get('won', False):
                    print("\n🎉 CONGRATULATIONS! YOU ESCAPED! 🎉")
                    #print("Type 'restart' to play again or 'quit' to exit.")

            except KeyboardInterrupt:
                print("\n👋 Game interrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")

    async def cleanup(self):
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python game_client.py <path_to_server_script>")
        print("Example: python game_client.py ../server/game_server.py")
        sys.exit(1)

    client = SimpleGameClient()
    
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())