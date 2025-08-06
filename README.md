# MCP Game: Behind Bars

An interactive text-based adventure game built using the Model Context Protocol (MCP) framework. This game features a prison escape scenario where players must navigate through rooms, solve puzzles, and collect items to escape.

## 🎮 Game Overview

"Behind Bars" is a text-based adventure game where you find yourself trapped in a prison cell. Your goal is to escape by exploring the environment, solving puzzles, and finding the right tools and keys. The game uses AI-powered responses to create an immersive and dynamic experience.

## 🏗️ Architecture

This project consists of two main components:

- **Client** (`client/`): A Python client that handles user interaction and communicates with the game server
- **Server** (`server/`): A FastAPI-based server that manages the game state, room logic, and AI interactions

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- An Anthropic API key (for AI interactions)

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
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
# Create a .env file in the client directory
echo "ANTHROPIC_API_KEY=your_api_key_here" > client/.env
```

### Running the Game

1. Start the game client:
```bash
cd client
python game_client.py ../server/behind_bars_server.py
```

2. Follow the on-screen instructions to play the game!

## 🎯 Game Features

- **Interactive Text Adventure**: Navigate through rooms using natural language commands
- **AI-Powered Responses**: Dynamic responses based on your actions and the current game state
- **Inventory System**: Collect and use items to solve puzzles
- **Multiple Endings**: Different outcomes based on your choices and actions
- **Visual Elements**: ASCII art and room descriptions for immersive gameplay

## 🛠️ Technical Details

### Client (`client/`)
- Built with Python and the MCP framework
- Handles user input/output and game state management
- Communicates with the server via MCP protocol
- Integrates with Anthropic's Claude API for AI responses

### Server (`server/`)
- FastAPI-based server implementation
- Manages game logic and room states
- Handles asset management (images, room layouts)
- Provides MCP-compatible endpoints

### Dependencies

**Client Dependencies:**
- `anthropic>=0.57.1` - AI API integration
- `mcp>=1.11.0` - Model Context Protocol
- `python-dotenv>=1.1.1` - Environment variable management

**Server Dependencies:**
- `httpx>=0.28.1` - HTTP client
- `mcp[cli]>=1.11.0` - MCP server implementation

## 🎨 Game Assets

The server includes various game assets in the `server/assets/` directory:
- Room layouts and backgrounds
- Item sprites (keys, tools, etc.)
- Door states (open/closed)
- Safe and security elements

## 🔧 Development

### Project Structure
```
mcp-game/
├── client/
│   ├── game_client.py      # Main client application
│   ├── pyproject.toml      # Client dependencies
│   └── current_room.png    # Current room display
├── server/
│   ├── behind_bars_server.py  # Main server implementation
│   ├── assets/               # Game assets
│   └── pyproject.toml        # Server dependencies
├── README.md
└── .gitignore
```

### Adding New Features

1. **New Rooms**: Add room logic in the server and corresponding assets
2. **New Items**: Create item sprites and add to the inventory system
3. **New Puzzles**: Implement puzzle logic in the server's room handlers
4. **AI Enhancements**: Modify the client's AI interaction logic

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with the Model Context Protocol (MCP) framework
- AI powered by Anthropic's Claude
- Game assets created specifically for this project

## 🐛 Known Issues

- Currently optimized for Python 3.11+
- Requires stable internet connection for AI interactions
- Some edge cases in room navigation may occur

## 📞 Support

If you encounter any issues or have questions, please open an issue on GitHub.

---

**Enjoy escaping from Behind Bars!** 🚪🔑 

