import os
import io
import requests
import pandas as pd
from dotenv import load_dotenv
import discord
import time
import logging
import threading
import http.server
import socketserver
from openai import AsyncOpenAI

# --- 1. THE HEARTBEAT SERVER (Fly.io Stability) ---
def run_health_check_server():
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
    
    with socketserver.TCPServer(("", 8080), HealthHandler) as httpd:
        print("📡 Health check server active on 8080")
        httpd.serve_forever()

threading.Thread(target=run_health_check_server, daemon=True).start()

# --- 2. CONFIGURATION ---
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") 
CSV_URL = os.getenv("CSV_URL")
MODEL_NAME = "google/gemini-2.0-flash-001" 

if not DISCORD_BOT_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("❌ Missing API Keys in environment variables")

client_ai = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# --- 3. DATA LOADING ---
def load_csv():
    print("📥 Loading CSV from source...")
    with requests.get(CSV_URL, stream=True) as r:
        r.raise_for_status()
        data = pd.read_csv(io.BytesIO(r.content))
    print(f"✅ CSV Loaded: {len(data)} rows")
    return data

df = load_csv()
column_info = ", ".join(df.columns)

SYSTEM_PROMPT = f"""
You are a data assistant for a DataFrame `df`. Columns: {column_info}.

RULES:
1. Use ONLY standard pandas/numpy methods (e.g., df.groupby(), .mean(), .max()). 
2. Do NOT invent or use functions that are not defined in the script (like 'calculate_average_nse').
3. For questions about "which and how high", use this format:
   print(f"Basin: {{df.groupby('Basin')['NSE'].mean().idxmax()}}, Value: {{df.groupby('Basin')['NSE'].mean().max()}}")
4. Return ONLY the code.
"""

# --- 4. DISCORD BOT LOGIC ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ HydroBot online as {client.user}")

@client.event
async def on_message(message):
    global df
    if message.author == client.user: return

    is_mentioned = client.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    if not (is_mentioned or is_dm): return

    question = message.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
    
    if question.lower() == "!reload":
        df = load_csv()
        await message.channel.send("🔄 CSV reloaded successfully!")
        return

    if not question:
        await message.channel.send("I'm listening! Ask me something about the basins. 💧")
        return

    async with message.channel.typing():
        try:
            completion = await client_ai.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
            )
            
            code = completion.choices[0].message.content.strip().replace("```python", "").replace("```", "").strip()

            if "df" in code:
                import sys
                from io import StringIO
                output_buffer = StringIO()
                old_stdout = sys.stdout
                sys.stdout = output_buffer
                
                try:
                    # Smart Execution Logic
                    locs = {"df": df, "pd": pd}
                    lines = [line for line in code.split('\n') if line.strip()]
                    
                    if lines:
                        # Run all lines except the last one
                        if len(lines) > 1:
                            exec('\n'.join(lines[:-1]), {}, locs)
                        
                        # Try to evaluate the last line to catch "naked" variables
                        try:
                            last_val = eval(lines[-1], {}, locs)
                            if last_val is not None:
                                print(last_val)
                        except:
                            exec(lines[-1], {}, locs)

                    result = output_buffer.getvalue().strip()
                except Exception as e:
                    result = f"Execution Error: {str(e)}"
                finally:
                    sys.stdout = old_stdout
                
                reply = f"**Result:**\n{result}" if result else "✅ Done, but no result was returned."
            else:
                reply = code

            await message.channel.send(reply[:2000])

        except Exception as e:
            await message.channel.send(f"⚠️ System Error: {str(e)}")

# --- 5. RUN ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client.run(DISCORD_BOT_TOKEN)