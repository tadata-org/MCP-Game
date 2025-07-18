Installation:
    Clone or download this project
    Install dependencies:
    bashpip install -r requirements.txt

    Set up Anthropic API:

    Get an API key from Anthropic
    Create a .env file in the client/ directory:
    ANTHROPIC_API_KEY=your_api_key_here

Playing:
    cd client
    python game_client.py ../server/behind_bars_server.py


Debugging: 
    In behind_bars_server.py, add: logging.basicConfig(level=logging.INFO)


Note: disregard client-old and server-old. 

