import os
import io
import requests
import pandas as pd
from dotenv import load_dotenv
import discord
import logging
from openai import AsyncOpenAI

# --- CONFIGURATION ---
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

# --- DATA LOADING ---
def load_csv():
    print("📥 Loading CSV from source...")
    with requests.get(CSV_URL, stream=True) as r:
        r.raise_for_status()
        data = pd.read_csv(io.BytesIO(r.content))
    print(f"✅ CSV Loaded: {len(data)} rows, {len(data.columns)} columns")
    return data

df = load_csv()

SYSTEM_PROMPT = """
You are HydroBot, a data assistant for GloFAS v5 calibration results.
You have access to a pandas DataFrame `df` with one row per calibration station.

Column groups and meanings:
- Station info: ID, name, basin, river, provider, iso, lat, lon
- Grid coords: grid_x, grid_y (LISFLOOD grid coordinates)
- Drainage area: DrainageArea_prov (provider-given, km²), DrainageArea_LDD (from LDD raster, km²)
- GloFAS flags: SourceGlo (in GloFAS v4, bool), GlofasV5 (in GloFAS v5, bool)
- Observation period: Obs_start, Obs_end, Split_date_CALstart (calibration period start)
- Performance metrics:
    KGEmod: modified Kling-Gupta Efficiency (calibration score, higher=better, max=1)
    JSD: Jensen-Shannon Divergence on flow duration curve (lower=better)
- Function: station function classification
- Region: world region
- Elevation: elv_mean, elv_median (meters a.s.l.)
- Leaf Area Index: laii_mean/median (initial), laif_mean/median (final)
- Slope: gradient_mean, gradient_median
- Land use: lusemask_mean/median, fracforest_mean/median, fracirrigated_mean/median, fracother_mean/median (fractions 0-1)
- Soil: soildepth1_f_mean/median (frozen, mm), soildepth1_o_mean/median (other, mm)
         ksat1_f_mean/median (hydraulic conductivity frozen), ksat1_o_mean/median (other)
- Climate (catchment averages):
    tp_mean_annual: mean annual total precipitation (mm/year)
    tp_std_interann: interannual precipitation variability (mm)
    tp_seasonality: precipitation seasonality index
    eT0_mean_annual: mean annual reference evapotranspiration (mm/year)
    eT0_std_interann: interannual ET0 variability (mm)
    eT0_seasonality: ET0 seasonality index
    ta_mean: mean annual air temperature (°C)
    ta_std_interann: interannual temperature variability (°C)
    ta_seasonality: temperature seasonality index
    aridity_index: aridity index (ET0/P ratio, >1 = arid)
- Calibration parameters (param_*): LISFLOOD model parameters, NaN = not calibrated
- glacier_frac: glacier fraction of catchment (0-1)

RULES:
1. Use ONLY standard pandas/numpy methods (df.groupby(), .mean(), .max(), etc.)
2. For calibrated stations only, filter: df[df['param_GwLoss'].notna()]
3. Do NOT invent functions not defined in this script.
4. Return ONLY executable Python code, no explanations.
5. For "which station/basin is highest/lowest" questions use this pattern:
   print(f"Station: {df.groupby('name')['KGEmod'].mean().idxmax()}, Value: {df.groupby('name')['KGEmod'].mean().max():.3f}")
"""

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ HydroBot online as {client.user}")

@client.event
async def on_message(message):
    global df
    if message.author == client.user:
        return

    is_mentioned = client.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    if not (is_mentioned or is_dm):
        return

    question = message.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()

    if question.lower() == "!reload":
        df = load_csv()
        await message.channel.send("🔄 CSV reloaded successfully!")
        return

    if not question:
        await message.channel.send("I'm listening! Ask me something about the GloFAS stations. 💧")
        return

    async with message.channel.typing():
        try:
            completion = await client_ai.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question}
                ]
            )

            code = completion.choices[0].message.content.strip().replace("```python", "").replace("```", "").strip()

            if "df" in code:
                import sys
                from io import StringIO
                output_buffer = StringIO()
                old_stdout = sys.stdout
                sys.stdout = output_buffer

                try:
                    import numpy as np
                    locs = {"df": df, "pd": pd, "np": np}
                    lines = [line for line in code.split('\n') if line.strip()]

                    if lines:
                        if len(lines) > 1:
                            exec('\n'.join(lines[:-1]), {}, locs)
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

# --- RUN ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client.run(DISCORD_BOT_TOKEN)