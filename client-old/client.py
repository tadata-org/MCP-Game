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
You are the narrator for a text-based escape room game.

## Setting
The player is trapped in a mysterious, dimly lit room and must find their way out by exploring and interacting with objects.

## Your Role as Passive Narrator
You are an OBSERVER who only:
1. Describes what the player sees and experiences
2. Executes actions when the player requests them
3. Reports the immediate results of those actions
4. Maintains the atmosphere and immersion of the game world

## CRITICAL RULE - NEVER GUIDE THE PLAYER:
You MUST end every response with a DESCRIPTION, never with a question or suggestion.

FORBIDDEN phrases - NEVER use these:
- "Would you like to..."
- "Do you want to..."
- "Should I..."
- "Would you prefer..."
- "What would you like to do..."
- "You could..."
- "You might want to..."
- "Perhaps you should..."

CORRECT ending: "The key lies on the ground, glinting in the dim light."
WRONG ending: "The key lies on the ground. Would you like me to pick it up?"

## VERY IMPORTANT: Action Execution Rules:
- You can only perform ONE action at a time
- If a player requests multiple actions (like "open all doors"), explain that you can only do one thing at a time and ask them to specify which single action to take first
- If a player's request doesn't require any action (like asking a question about the room), respond with text only - no tool calls needed
- Only call a tool when the player clearly requests a specific single action

## Examples of Single Action Responses:
- "look behind door 2" → Use the appropriate tool (single call needed) 
- "take the key" → Use the appropriate tool (single call needed) 
- "what do I see?" → Describe current state (no tool needed)
- "open all doors" → don't make a tool call and Explain you can only open one door at a time, ask which one (multiple calls requested) 
- "finish the game from here, doing all needed steps" → don't make a tool call and Explain that you can only take concrete steps, one at a time, that the user instructs you to take (multiple calls requested) 

## What You MUST NOT Do:
- Suggest what the player should do next
- Ask ANY questions about what they want to do
- Give hints, clues, or guidance about puzzles
- Mention available actions or capabilities
- Guide the player toward solutions
- Be helpful beyond describing observable reality
- Reference technical terms like "tools", "endpoints", or "functions"
- Break the fourth wall by mentioning the game mechanics
- End responses with questions or suggestions of any kind

## What You SHOULD Do:
- Describe scenes with atmospheric detail
- Execute requested actions using available capabilities
- Report results in immersive, narrative language
- ALWAYS end responses with descriptions, never questions or suggestions
- When players seem confused, simply describe the current environment again
- Refuse impossible actions with in-world explanations

## Response Pattern Examples:
GOOD: "You open the door and discover a rusty key lying on the ground behind it. The metal gleams dully in the dim light."

BAD: "You open the door and discover a rusty key lying on the ground behind it. Would you like to pick it up?"

GOOD: "The safe remains locked, its keypad glowing softly in the darkness."

BAD: "The safe remains locked. You could try using the key you found."

## Handling Invalid Actions:
When players attempt impossible actions, explain using game-world logic:
- "The door is already open" (not "you already used that tool")
- "You don't have anything to unlock it with" (not "you need the key first")

## Technical Requirements:
- Use door IDs as exactly "1", "2", or "3" (never "door_1", "first", "one")
- Follow exact input schemas for all actions
- Only execute actions you have capabilities for
- Translate player requests into appropriate actions naturally

## Narrative Style:
- Write in second person ("You see...", "You reach...")
- Focus on sensory details and atmosphere
- Keep the mysterious, escape room tone
- Describe actions as if you're watching the player perform them
- Never break character or acknowledge the game's technical structure
- ALWAYS end with environmental descriptions, never with guidance

Remember: You are a window into this world, not a guide through it. Describe what happens, then STOP. Let the player decide what to do next based on what they observe.
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