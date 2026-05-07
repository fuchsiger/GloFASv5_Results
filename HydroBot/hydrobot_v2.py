import os
import io
import ast
import sys
import requests
import pandas as pd
import numpy as np
from io import StringIO
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
- Station info: ID, name, basin, river, provider, iso (country ISO code), lat, lon
- Grid coords: grid_x, grid_y (LISFLOOD grid coordinates)
- Drainage area: DrainageArea_prov (provider-given, km²), DrainageArea_LDD (from LDD raster, km²)
- GloFAS flags: SourceGlo (in GloFAS v4), GlofasV5 (calibration status in GloFAS v5: 'Calibrated' or other)
- Observation period: Obs_start, Obs_end, Split_date_CALstart (calibration period start)
- Region: world region classification

PERFORMANCE METRICS:
    KGEmod: modified Kling-Gupta Efficiency (calibration score).
            HIGHER is BETTER. Maximum possible value is 1.0 (perfect fit).
            Values close to 1.0 are excellent. Values below 0 are poor.
            "best" station = HIGHEST KGEmod. "worst" station = LOWEST KGEmod.
    JSD: Jensen-Shannon Divergence on flow duration curve.
         LOWER is BETTER. Minimum possible value is 0 (perfect match).
         "best" station = LOWEST JSD. "worst" station = HIGHEST JSD.
    Function: station function classification

CATCHMENT ATTRIBUTES:
    Elevation:   elv_mean, elv_median (m a.s.l.)
    Slope:       gradient_mean, gradient_median
    Land use:    fracforest_mean/median, fracirrigated_mean/median, fracother_mean/median (fractions 0-1)
                 lusemask_mean/median (dominant land use code)
    Leaf Area:   laii_mean/median (initial LAI), laif_mean/median (final LAI)
    Soil:        soildepth1_f_mean/median (frozen soil depth, mm), soildepth1_o_mean/median (other, mm)
                 ksat1_f_mean/median (hydraulic conductivity frozen), ksat1_o_mean/median (other)
    Glacier:     glacier_frac (glacier fraction of catchment, 0-1)

CLIMATE (catchment-averaged, ERA5-based):
    Precipitation:      tp_mean_annual (mm/yr), tp_std_interann (mm), tp_seasonality
    Evapotranspiration: eT0_mean_annual (mm/yr), eT0_std_interann (mm), eT0_seasonality
    Temperature:        ta_mean (degrees C), ta_std_interann (degrees C), ta_seasonality
    Aridity:            aridity_index (ET0/P ratio; >1 = arid, <1 = humid)

WATER BALANCE (mean annual, LISFLOOD simulated):
    q_mean_annual:      total discharge (mm/yr)
    eta_mean_annual:    actual evapotranspiration (mm/yr)
    et0_mean_annual:    reference ET0 from LISVAP output (mm/yr) [lowercase, distinct from eT0_mean_annual]
    et0_seasonality:    ET0 seasonality index (LISVAP output)
    ew0_mean_annual:    open water evaporation (mm/yr)
    ew0_seasonality:    open water evaporation seasonality
    swe_mean_annual:    snow water equivalent (mm)
    sf_mean_annual:     snowfall (mm/yr)
    sf_seasonality:     snowfall seasonality
    smlt_mean_annual:   snowmelt (mm/yr)
    smlt_seasonality:   snowmelt seasonality
    perc_mean_annual:   percolation to groundwater (mm/yr)
    perc_seasonality:   percolation seasonality
    qb_up_mean_annual:  upper groundwater baseflow (mm/yr)
    qb_up_seasonality:  upper groundwater baseflow seasonality
    qb_low_mean_annual: lower groundwater baseflow (mm/yr)
    qb_low_seasonality: lower groundwater baseflow seasonality
    gwloss_mean_annual: groundwater loss (mm/yr)
    gwloss_seasonality: groundwater loss seasonality
    lz_mean_annual:     lower groundwater zone storage (mm)
    uz_mean_annual:     upper groundwater zone storage (mm)
    theta_mean_annual:  soil moisture layer 1 (mm3/mm3)
    theta2_mean_annual: soil moisture layer 2 (mm3/mm3)
    theta3_mean_annual: soil moisture layer 3 (mm3/mm3)

CALIBRATION PARAMETERS (param_*) -- NaN = station not calibrated:
    param_CalChanMan1, param_CalChanMan3: channel Manning roughness
    param_GwLoss:                groundwater loss coefficient
    param_GwPercValue:           groundwater percolation rate
    param_LZThreshold:           lower zone threshold for baseflow
    param_LakeMultiplier:        lake outflow multiplier
    param_LowerZoneTimeConstant: lower zone recession constant
    param_PowerPrefFlow:         preferential flow exponent
    param_SnowMeltCoef:          snowmelt degree-day factor
    param_TransSub:              subsurface flow transmissivity
    param_UpperZoneTimeConstant: upper zone recession constant
    param_b_Xinanjiang:          Xinanjiang soil moisture exponent

RULES:
1. Use ONLY standard pandas/numpy methods (df.groupby(), .mean(), .max(), etc.)
2. For calibrated stations only, filter: df[df['param_GwLoss'].notna()]
3. Do NOT invent functions not defined in this script.
4. Return ONLY executable Python code, no explanations, no markdown.
5. CRITICAL -- metric directions:
   - KGEmod: HIGHER = BETTER -> use .idxmax() / .max() for "best", .idxmin() / .min() for "worst"
   - JSD:    LOWER  = BETTER -> use .idxmin() / .min() for "best", .idxmax() / .max() for "worst"
6. For "which station/basin is best/worst/highest/lowest" questions use this pattern:
   idx = df['KGEmod'].idxmax()
   print(f"Best station: {df.loc[idx, 'name']} (ID {df.loc[idx, 'ID']}), KGEmod = {df.loc[idx, 'KGEmod']:.3f}")
7. For ID lookups use:
   row = df[df['ID'] == 1960]
   if not row.empty:
       print(row[['name', 'basin', 'KGEmod', 'JSD']].round(3).to_string(index=False))
   else:
       print("Station ID not found.")
8. Always round numerical output to 3 decimal places.
   For DataFrames use: df.round(3) before printing.
   For single values use: f"{value:.3f}"
"""

# --- CODE EXECUTION ---
def execute_code(code: str, df: pd.DataFrame) -> str:
    """
    Safely execute LLM-generated pandas code.
    Uses AST compilation to handle multi-line code, if/else blocks, etc.
    Captures stdout as the result.
    """
    output_buffer = StringIO()
    old_stdout = sys.stdout
    sys.stdout = output_buffer

    try:
        tree = ast.parse(code)

        # If the last statement is a bare expression, wrap it in print()
        # so the result is captured — e.g. df.shape or a scalar value
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = tree.body[-1].value
            print_node = ast.Expr(
                value=ast.Call(
                    func=ast.Name(id="print", ctx=ast.Load()),
                    args=[last_expr],
                    keywords=[]
                )
            )
            tree.body[-1] = print_node
            ast.fix_missing_locations(tree)

        locs = {"df": df, "pd": pd, "np": np}
        exec(compile(tree, "<string>", "exec"), {}, locs)
        result = output_buffer.getvalue().strip()

    except Exception as e:
        result = f"Execution Error: {str(e)}"
    finally:
        sys.stdout = old_stdout

    return result


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

    question = (
        message.content
        .replace(f"<@{client.user.id}>", "")
        .replace(f"<@!{client.user.id}>", "")
        .strip()
    )

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

            code = (
                completion.choices[0].message.content
                .strip()
                .replace("```python", "")
                .replace("```", "")
                .strip()
            )

            if "df" in code:
                result = execute_code(code, df)
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