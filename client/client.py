import asyncio
import sys
import json
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

SYSTEM_PROMPT = """
You are the narrator and assistant for a text-based escape room game.

## Setting
The player is trapped in a mysterious, dimly lit room. The room contains:
- Three doors labeled door_1, door_2, and door_3
- A sturdy metal safe with a keypad
- A key may be hidden somewhere
The player's objective is to explore the room and find a way to escape by interacting with objects.

## Your Role
You respond to the player's text queries by either:
1. Narrating their actions
2. Calling a tool (from the list below) to carry out that action
3. Describing the result using immersive, in-character language

**You must only take actions using the tools available to you. DO NOT make up new actions or tool results.**
Each tool corresponds to a real function with defined behavior. Always follow its expected input schema.

## Critical Rules
- When dealing with doors, always use door_id as exactly "1", "2", or "3" - just the number as a string
- Never use values like "door_1", "first", "one", etc. for door identification
- Only use the tools that are currently available to you
- Always follow the exact input schema for each tool
"""


class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()
        self.conversation_history: List[Dict[str, Any]] = []
        self.debug_mode = True  # Enable debug by default

    def print_claude_input(self, system_prompt: str, messages: List[Dict], tools: List[Dict]):
        """Print exactly what Claude receives as input"""
        print("\n" + "="*80)
        print("🔍 EXACT INPUT TO CLAUDE API")
        print("="*80)
        
        print("\n📋 SYSTEM PROMPT:")
        print("-" * 40)
        print(system_prompt)
        
        print("\n💬 CONVERSATION HISTORY:")
        print("-" * 40)
        for i, msg in enumerate(messages):
            print(f"Message {i+1} - Role: {msg['role']}")
            content = msg['content']
            if isinstance(content, str):
                print(f"  Content: {content}")
            elif isinstance(content, list):
                print(f"  Content (complex): {len(content)} items")
                for j, item in enumerate(content):
                    if isinstance(item, dict):
                        if item.get('type') == 'text':
                            print(f"    {j+1}. text: {item.get('text', '')[:100]}...")
                        elif item.get('type') == 'tool_use':
                            print(f"    {j+1}. tool_use: {item.get('name')} with {item.get('input')}")
                        elif item.get('type') == 'tool_result':
                            print(f"    {j+1}. tool_result: {item.get('content', '')[:100]}...")
            print()
        
        print("\n🛠️  AVAILABLE TOOLS:")
        print("-" * 40)
        for i, tool in enumerate(tools):
            print(f"Tool {i+1}: {tool['name']}")
            print(f"  Description: {tool.get('description', 'No description')}")
            print(f"  Schema: {json.dumps(tool.get('input_schema', {}), indent=2)}")
            print()
        
        print("="*80)
        print("🚀 SENDING TO CLAUDE...")
        print("="*80)

    async def connect_to_server(self, server_script_path: str):
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(command=command, args=[server_script_path])

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        print(f"\n🎯 USER QUERY: '{query}'")
        
        # Add user query to conversation history
        self.conversation_history.append({"role": "user", "content": query})

        # Get available tools from the server
        response = await self.session.list_tools()
        available_tools = [
            {
                "name": tool.name,
                "description": tool.description or "No description provided.",
                "input_schema": tool.inputSchema,
            }
            for tool in response.tools
        ]

        # 🔍 SHOW EXACT INPUT TO CLAUDE
        if self.debug_mode:
            self.print_claude_input(SYSTEM_PROMPT, self.conversation_history, available_tools)

        try:
            # Send request to Claude with full conversation history
            response = self.anthropic.messages.create(
                model="claude-3-5-haiku-latest",
                system=SYSTEM_PROMPT,
                max_tokens=1000,
                messages=self.conversation_history,
                tools=available_tools,
            )

            print(f"\n✅ CLAUDE RESPONSE RECEIVED")
            print(f"📊 Response content count: {len(response.content)}")

            # Process Claude's response
            assistant_content = []
            tool_calls = []

            for i, content in enumerate(response.content):
                print(f"📝 Content {i}: type={content.type}")
                if content.type == "text" and isinstance(content.text, str):
                    assistant_content.append(content.text)
                    print(f"   Text: {content.text[:100]}...")
                elif content.type == "tool_use":
                    tool_calls.append(content)
                    print(f"   🔧 Tool call: {content.name} with args {content.input}")

            # Build response content for history
            if assistant_content or tool_calls:
                response_content = []
                
                # Add text content
                if assistant_content:
                    response_content.append({
                        "type": "text",
                        "text": "\n".join(assistant_content)
                    })
                
                # Add tool use content
                for tool_call in tool_calls:
                    response_content.append({
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": tool_call.input
                    })
                
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response_content
                })

            # Execute tool calls and handle responses
            final_text = assistant_content.copy()
            
            for tool_call in tool_calls:
                tool_name = tool_call.name
                tool_args = tool_call.input
                
                print(f"\n🔧 EXECUTING TOOL: '{tool_name}' with args: {tool_args}")
                
                try:
                    # Call the tool via MCP
                    result = await self.session.call_tool(tool_name, tool_args)
                    print(f"✅ Tool result: {result.content}")
                    
                    # Add tool result to conversation history
                    self.conversation_history.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call.id,
                                "content": result.content
                            }
                        ]
                    })
                    
                    # Get Claude's response to the tool result
                    if self.debug_mode:
                        print("\n🔄 GETTING CLAUDE'S NARRATIVE RESPONSE TO TOOL RESULT...")
                        self.print_claude_input(SYSTEM_PROMPT, self.conversation_history, available_tools)
                    
                    follow_up = self.anthropic.messages.create(
                        model="claude-3-5-haiku-latest",
                        system=SYSTEM_PROMPT,
                        max_tokens=1000,
                        messages=self.conversation_history,
                        tools=available_tools,
                    )
                    
                    # Process follow-up response
                    follow_up_text = []
                    for next_content in follow_up.content:
                        if next_content.type == "text" and isinstance(next_content.text, str):
                            follow_up_text.append(next_content.text)
                    
                    if follow_up_text:
                        # Add follow-up to history
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": "\n".join(follow_up_text)
                        })
                        
                        # Add to final output
                        final_text.extend(follow_up_text)
                        
                except Exception as tool_error:
                    print(f"❌ Tool execution failed: {tool_error}")
                    error_msg = f"Error executing {tool_name}: {tool_error}"
                    final_text.append(error_msg)

            result = "\n".join(final_text) if final_text else "I'm not sure how to respond to that."
            return result
            
        except Exception as e:
            print(f"❌ Exception in process_query: {e}")
            error_msg = f"Error processing query: {str(e)}"
            # Add error to history to maintain context
            self.conversation_history.append({
                "role": "assistant", 
                "content": error_msg
            })
            return error_msg

    def toggle_debug(self):
        """Toggle debug mode on/off"""
        self.debug_mode = not self.debug_mode
        print(f"🔧 Debug mode: {'ON' if self.debug_mode else 'OFF'}")

    def clear_history(self):
        """Clear conversation history - useful for starting a new game"""
        self.conversation_history = []

    def get_conversation_length(self) -> int:
        """Get the number of messages in conversation history"""
        return len(self.conversation_history)

    def print_conversation_summary(self):
        """Print a summary of the conversation for debugging"""
        print(f"\n=== Conversation History ({len(self.conversation_history)} messages) ===")
        for i, msg in enumerate(self.conversation_history):
            role = msg["role"]
            content = msg["content"]
            
            if isinstance(content, str):
                preview = content[:100] + "..." if len(content) > 100 else content
                print(f"{i+1}. {role}: {preview}")
            elif isinstance(content, list):
                print(f"{i+1}. {role}: [complex content with {len(content)} items]")
                for j, item in enumerate(content):
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_preview = item.get("text", "")[:50]
                            print(f"    {j+1}. text: {text_preview}...")
                        elif item.get("type") == "tool_use":
                            print(f"    {j+1}. tool_use: {item.get('name')} with {item.get('input')}")
                        elif item.get("type") == "tool_result":
                            print(f"    {j+1}. tool_result: {item.get('content', '')[:50]}...")
            else:
                print(f"{i+1}. {role}: {type(content)}")
        print("=" * 50)

    async def chat_loop(self):
        print("\nMCP Escape Room Game Started!")
        print("Commands: 'quit', 'history', 'restart', 'debug' (toggle debug), or game commands")
        
        # Start with room description
        try:
            initial_response = await self.process_query("describe the room")
            print(f"\n🎮 GAME OUTPUT:\n{initial_response}")
        except Exception as e:
            print(f"Error getting initial room description: {e}")

        while True:
            try:
                query = input("\n> ").strip()
                
                if query.lower() == "quit":
                    print("Thanks for playing! Goodbye!")
                    break
                elif query.lower() == "history":
                    self.print_conversation_summary()
                    continue
                elif query.lower() == "restart":
                    self.clear_history()
                    print("Game restarted! Starting fresh...")
                    initial_response = await self.process_query("describe the room")
                    print(f"\n🎮 GAME OUTPUT:\n{initial_response}")
                    continue
                elif query.lower() == "debug":
                    self.toggle_debug()
                    continue
                elif not query:
                    continue

                response = await self.process_query(query)
                print(f"\n🎮 GAME OUTPUT:\n{response}")

            except KeyboardInterrupt:
                print("\nGame interrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\nError: {str(e)}")
                print("Try again or type 'quit' to exit.")

    async def cleanup(self):
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        print("Example: python client.py escape_room_server.py")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())