# Trade Server - Hoe Het Werkt (How It Works)

Welkom bij de beknopte handleiding van de Agentic Trade Server. Dit document legt in duidelijke stappen uit hoe het "brein" van de applicatie werkt en wanneer het systeem besluit om actie te ondernemen in de cryptomarkt.

## 1. De Scanner (De Radar)
De Scanner (`data/scanner.py`) is de waakhond van de server. Hij controleert continu de markt en bepaalt of het veilig en winstgevend genoeg is om het Analyst Team wakker te maken.
- **Wanneer scant hij?** Elke 5 minuten (300 seconden).
- **Waar kijkt hij naar?** Hij vuurt 6 specifieke *Triggers* (signalen) af:
  1. **Volume Spike**: Is het volume plots 150%+ hoger dan het gemiddelde?
  2. **RSI Extremen**: Is de markt oversold (RSI < 35) of overbought (RSI > 65)?
  3. **CVD Shift**: Draait de koop/verkoop-druk plotseling om?
  4. **Key Levels**: Zit de prijs binnen 0.5% van een belangrijk steun- of weerstandsniveau (POC, VAH, VAL)?
  5. **Funding Rate Squeeze**: Ligt de funding rate (Bybit) ongewoon hoog of laag?
  6. **Absorption**: Ligt er "Magic Entry" bodemvorming of "absorptie" op de loer?
- **Wanneer geeft hij alarm?** Pas als **minimaal 2 van de 6 triggers** tegelijkertijd afgaan, klinkt de sirene en wekt hij de agents.

## 2. Het Analisten Team (De Deskundigen)
Zodra de Scanner alarm slaat, schieten 5 AI-Analisten in actie om de rauwe data te analyseren:
1. **Volume Analyst**: Bekijkt de kracht van de trend en het volume.
2. **Orderflow Analyst**: Kijkt naar de werkelijke bids/asks (kopers vs. verkopers).
3. **News Analyst**: Leest de laatste nieuwsberichten en evalueert marktsentiment.
4. **Volume Profile (VP) Analyst**: Berekent de 'High Value' en 'Low Value' gebieden (steun/weerstand).
5. **Game Theory Analyst (Grok)**: Analyseert het psychologische slagveld: wie probeert wie te slim af te zijn in de markt?

Elke analist brengt een eigen rapport uit (BULLISH, BEARISH, of NEUTRAL) met een cijfer voor zelfverzekerdheid (confidence).

## 3. Het Portfolio & Risk Management (De Poortwachter)
Voordat we klakkeloos de markt in duiken, moeten de adviezen van de Analisten langs de strenge Risk Manager:
- **Risk Assessment**: Voldoet de voorgestelde trade aan jouw limieten (maximaal % risico per trade, minimum confidence drempel)?
- **Portfolio Check**: Hebben we te veel posities open (max_positions threshold) of is onze USDT balans te laag?

### Veto: Het Non-Trade Journal
Zegt de Portfolio Manager **Nee** tegen de trade omdat het te riskant is of de confidence te laag is?
Dan verdwijnt deze "Afgewezen Setup" stilletjes in de database...
...om er 4 uur later door de **Non-Trade Evaluator** uit gehaald te worden! Deze achtergrond-service kijkt of we zojuist een pijnlijk verlies hebben voorkomen (🛡️ *Correct Reject*) of per ongeluk een 10x-klapper hebben laten schieten (💸 *Missed Opportunity*). Je ziet dit resultaat terug in je dashboard.

## 4. De Trade Monitor (De Lifeguard)
Als de trade **wordt geaccepteerd** en Live de markt op gaat, leunen we niet achterover.
De Trade Monitor (`services/monitor_service.py`) neemt het roer over.
- Hij draait op een razendsnelle loop in de achtergrond (elke paar seconden!).
- Zodra de prijs je **Stop Loss** raakt, triggert hij een NOODSTOP (panic button).
- Zodra de prijs je **Take Profit** nadert, zal hij razendsnel winnen pakken en de trade verzilveren, zonder dat een LLM (ai model) de tijd krijgt om te treuzelen.

## 5. De Meta Agent (De CEO & Zelfverbetering)
Aan het eind van elke week / of langere cyclus, ontwaakt de opperbaas: **De Meta Agent**.
Hij leest álle resultaten (zowel succesvolle trades als de gemiste/afgewezen kansen in het log) en bestudéért waarom we geld verloren of verdienden. Hij kan uit zichzelf de `confidence` threshholds op je dashboard veranderen als hij vindt dat we "steeds net te laat instappen" of "steeds net te veel risico nemen in ranging markets".

---
*Je trade server is geen simpele bot, maar een AI-gestuurd ecosysteem dat elke minuut bijleert en zichzelf heelt!*
