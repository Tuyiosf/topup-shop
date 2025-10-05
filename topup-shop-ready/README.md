# Topup Shop (Ready for Render)
- Flask app with Discord OAuth2 login, simple order/chat system, admin panel.
- Default games: Free Fire, ROV, Roblox
- Theme: Blue-White
- How to use:
  1. Copy `.env.example` -> `.env` and fill values (Discord client id/secret and your render URL)
  2. Push this repository to GitHub
  3. On Render, create a new Web Service -> connect GitHub repo
     - Build Command: `pip install -r requirements.txt`
     - Start Command: `python app.py`
  4. Deploy. Then update DISCORD_REDIRECT_URI in Discord Developer Portal to match your Render URL `/callback`
