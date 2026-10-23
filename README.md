# Iraqi Consulate Frankfurt NID appointment monitor

This small personal monitor checks NeetoCal's public first-available-date endpoint, then inspects the corresponding month for explicit time slots. It sends a Telegram alert when it detects a changed set of actual times. It **does not book appointments**.

Official booking page: https://icass.mofa.gov.iq/#/booking

## Configure Telegram

1. Create a bot with Telegram's official **@BotFather** and copy the bot token.
2. Open a private chat with your bot and press **Start**.
3. Obtain your Telegram chat ID (for example, use Telegram's bot API getUpdates after sending the bot a message).
4. In this GitHub repository open **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Go to **Actions**, enable workflows if GitHub asks, then run **Check NID appointment availability** with **Run workflow** to test it.

Never put the token in source code, issues, commits, screenshots, or chat.

## How it behaves

- Scheduled checks run approximately every 30 minutes; GitHub Actions schedules can be delayed.
- Each run makes at most two GET requests to the public availability API.
- It only alerts when it finds explicit time-like values in the slot response; dates by themselves are not treated as available appointments.
- The first alert may need manual review because the endpoint's response schema can change. Always verify the slot on the official booking page and complete the process yourself.
- State is stored in `monitor-state.json` to avoid repeating the same notification.
- A failed API call is logged in the Actions run. It does not try to bypass a CAPTCHA, login, or other access control.

## Important limitation

The first-available-date endpoint and response format are controlled by the appointment provider. If it stops returning a date or changes its JSON format, the monitor may need updating. GitHub Actions is not a guaranteed real-time service.
