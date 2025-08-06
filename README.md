# MCP Game: Behind Bars

Welcome! There are many powerful ways the Model Context Protocol is being used: It helps internal teams access company data, and users interact with the software without needing to go through their UI, to name a couple. 

But this project applies MCPs in a totally different way. This is an interactive text-based adventure game where you are trapped in an escape room, and players must navigate through the room, solve puzzles, and collect items to escape.

## 🏗️ Architecture

As I mentioned, this uses the MCP. Here is how: 

This project consists of two main components, the client and the server.

- **Client** (`client/`): A Python client that handles user interaction and communicates with the game server. It is responsible for interacting with the user, calling LLMs, and calling on MCP tools (which map to the different actions you can take in the room) from the server.
- **Server** (`server/`): A FastAPI-based server that manages the game state, room logic, and all the actions you can take. We turned it into an MCP server in three lines of code using the FastAPI-MCP open source project (https://github.com/tadata-org/fastapi_mcp)

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- An Anthropic API key (for AI interactions)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/tadata-org/MCP-Game
cd mcp-game
```

2. Install dependencies:
```bash
# Install client dependencies
cd client
pip install -e .

# Install server dependencies  
cd ../server
pip install -e .
```

3. Set up your environment variables:
```bash
# Create a .env file in the client directory to connect to the LLM
echo "ANTHROPIC_API_KEY=your_api_key_here" > client/.env
```

### Running the Game

1. Run the server:

```bash
cd server
uvicorn behind_bars_fastapi_server:app --reload --port 8000
```


2. Start the game client:
```bash
cd client
python game_client.py
```

3. Follow the on-screen instructions to play the game!

## 🎯 Game Features

- **Interactive Text Adventure**: Navigate through the room, taking actions, using natural language commands
- **AI-Powered Responses**: Dynamic responses based on your actions and the current game state
- **Inventory System**: Collect and use items to solve puzzles
- **Visual Elements**: Images and room descriptions for immersive gameplay

## 🛠️ Technical Details

### Client (`client/`)
- Built with Python
- Handles user input/output and game state management
- Communicates with the server via MCP protocol
- Integrates with Anthropic's API for AI responses. One LLM call parses the user's action, and a second narrates back the result. 
- Uses Streamable HTTP to communicate with the server

### Server (`server/`)
- FastAPI-based server implementation
- Used FastAPI-MCP to turn it into an MCP server
- Manages game logic and room states
- Handles asset management (for images)
- Has an endpoint for each action avaliable
- Uses Streamable HTTP to communicate with the client


### Adding New Features

This project is largely a "proof-of-concept", that the MCP is useful in some game applications, where the power of LLM is desired. The client and server architecture of the MCP lends itself very nicely to such scenarios, where MCP "tools" are the actions available for the LLM (and by extension, the user) to interact with the game. 

We encourage you to expand on our single escape room by, perhaps: 

1. **New Rooms**: Add room logic (and corresponding assets)
2. **New Items and Puzzles**: Make the rooms more complex, with multple directions the user can take it
4. **AI Enhancements**: Modify the client's AI interaction logic (the game is broadly as good as the LLM prompts which power it. We spent a lot of time playing with these prompts, and encourage you to do the same!)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License.

## 📞 Support

If you encounter any issues or have questions, please open an issue on GitHub.

---

**Enjoy escaping from Behind Bars!** 🚪🔑 

