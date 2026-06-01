# Stock Email Agent

Scans your Gmail over IMAP, finds stock-related emails (results, dividends,
splits, bonuses, buybacks, corporate actions), fetches any linked filings
(PDF/HTML), and uses an LLM (Claude / OpenAI / Ollama) to produce a
summary + opinion. Then drops you into an interactive chat to ask
follow-up questions.

## Setup

1. **Create a Gmail App Password** (Google Account → Security → 2-Step Verification → App passwords).
2. Add these to your `.env` at the repo root:

   ```env
   # Gmail (IMAP)
   GMAIL_USER=you@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   GMAIL_MAILBOX=INBOX                # optional, default INBOX
   STOCK_EMAIL_SENDERS=               # optional, comma-separated allowlist
   STOCK_EMAIL_KEYWORDS=results,dividend,split,bonus,buyback,rights,agm,board meeting

   # LLM (pick one provider; provider switch via STOCK_LLM_PROVIDER)
   STOCK_LLM_PROVIDER=anthropic       # anthropic | openai | ollama
   ANTHROPIC_API_KEY=sk-ant-...
   ANTHROPIC_MODEL=claude-3-5-sonnet-latest
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o-mini
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.1
   ```

3. Install dependencies (added to `requirements.txt`):

   ```bash
   pip install -r requirements.txt
   ```

## Run

```bash
# Interactive scope picker + email selection
python -m stock_email_agent

# Non-interactive examples
python -m stock_email_agent --since-days 7
python -m stock_email_agent --last-n 50 --summarize-all
python -m stock_email_agent --unread --sender "no-reply@nseindia.com"
```

### Workflow

1. Pick a scan scope: last N, last X days, unread only, or a custom mix.
2. The agent connects via IMAP, fetches matching emails, classifies them
   (results / dividend / split / bonus / buyback / rights / merger / etc.),
   and renders an indexed list.
3. Pick an email → the agent fetches up to 3 linked filings (PDF/HTML),
   extracts text, and calls the configured LLM with a fixed analyst prompt
   that returns: TL;DR, key facts (with units), what changed, why it
   matters, an explicitly-labelled OPINION, and suggested follow-ups.
4. You then chat with the agent about that email. Commands:
   - `:next` — analyse the next email in the list
   - `:back` — return to the selection prompt
   - `:quit` — exit

## Notes & limits

- Uses IMAP (`imap.gmail.com:993`) with an **App Password** — never your
  main password. Credentials live only in `.env`.
- PDF extraction uses `pymupdf` (already a project dep), falling back to
  `pypdf` if needed.
- Linked URLs that look like tracker / unsubscribe links are skipped.
- The LLM is instructed to mark OPINION explicitly and never fabricate
  numbers; it will say "not disclosed" when a figure isn't in the source.
- All fetched docs are cached under `tmp/stock_email_agent/`.
