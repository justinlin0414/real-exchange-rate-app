Real Exchange Rate Explorer
An interactive Streamlit app that builds monthly bilateral nominal and real exchange rates for any two IMF economies (including the Euro area) from official IMF data, starting in January 1976 where available.

What the app does
Country selection. Pick Country 1 (base currency) and Country 2 (quote currency) from the IMF economies, including the Euro area (IMF code G163).
Data retrieval. Downloads monthly series from the IMF SDMX 3.0 API (https://api.imf.org/external/sdmx/3.0):
Series	Dataflow	Key
Consumer price index (all items, index)	IMF.STA/CPI	{ISO3}.CPI._T.IX.M
Exchange rate, local currency per USD, period average	IMF.STA/ER	{ISO3}.XDC_USD.PA_RT.M
Exchange-rate calculations (see below), with the direction of the rate shown everywhere.
Sample period. A start/end month slider. The benchmark RER* and the real index are recalculated whenever the dates change.
Charts. Interactive Plotly charts: Real, Nominal, or Both (two stacked panels on a shared time axis, each with its own y-axis). Optional log scale for the nominal rate.
Download. A CSV of every month in the selected sample: both USD rates, S(t), both CPIs, RER(t), RER*, the real index and a validity flag.
Economics
Direction of the nominal rate.

S(t) = units of Country 2's currency per ONE unit of Country 1's currency
The IMF quotes every currency as local-currency units (LCU) per US dollar, so the bilateral rate is the cross rate through the dollar:

S(t) = (Country 2 LCU per USD) / (Country 1 LCU per USD)
Example: Country 1 = Euro area, Country 2 = Japan. If 1 USD = 0.90 EUR and 1 USD = 150 JPY, then S = 150 / 0.90 = 166.7 JPY per 1 EUR.

The US dollar. The United States' rate against itself is identically 1 (USD per USD). The app builds it directly instead of downloading it. If the US is Country 1, S(t) is simply Country 2's IMF rate. If the US is Country 2, S(t) is the inverse of Country 1's rate. Dollarized economies (e.g. Ecuador, El Salvador) also get a rate of 1 if the IMF has no series for them.

Real exchange rate.

RER(t) = S(t) × P1(t) / P2(t)
RER(t) is the number of Country 2 baskets of goods that one Country 1 basket buys. Each CPI has its own base year, so the level of RER(t) is arbitrary. The app therefore normalizes within the selected sample:

RER*          = average of RER(t) over the valid months in the selected sample
Real Index(t) = 100 × RER(t) / RER*
A month is valid when both exchange rates and both CPIs are available and positive. Months missing any input stay in the CSV (flagged valid_month = False), but they are left out of RER* and the index.

Interpretation.

A rise in S(t) is a nominal appreciation of Country 1's currency: it buys more of Country 2's currency.
A rise in the real index is a real appreciation of Country 1's currency: Country 1 goods become more expensive relative to Country 2 goods.
Index above 100: Country 1's currency is stronger in real terms than its average over the selected period. Index below 100: it is weaker.
If relative purchasing power parity held exactly, the index would stay at 100.
The nominal rate is plotted in actual currency units and is not normalized.
Data notes
The app asks the IMF availability service which economies have both monthly CPI and exchange-rate data, and lists only those. If that service is unavailable, it shows the full built-in IMF list and reports any missing series once a pair is chosen.
Series start in January 1976 or at the first month the IMF reports, whichever is later. The selectable range runs from the first to the last month where all four inputs are available.
The IMF generally expresses history in the economy's current currency unit (e.g. after redenominations). The app warns about any one-month nominal move larger than 30%. Such moves are usually devaluations or the end of a peg, but can also be series breaks.
Currency codes in the labels are the economies' current ISO 4217 codes.
IMF responses are cached for 24 hours to keep the app fast and to avoid repeated API calls.
Run locally
Requires Python 3.12.

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
Deploy on Streamlit Community Cloud
Push app.py, requirements.txt and README.md to the root of a GitHub repository.
Go to https://share.streamlit.io, click Create app, and choose the repository and branch.
Set Main file path to app.py.
Under Advanced settings, choose Python 3.12, then click Deploy.
No API key or secrets are needed. The IMF SDMX API is public.

Files
File	Purpose
app.py	The Streamlit application: IMF client, calculations, charts, CSV export
requirements.txt	Python dependencies
README.md	This document
Data source
International Monetary Fund, SDMX 3.0 API: Consumer Price Index (CPI) and Exchange Rates (ER) datasets.
