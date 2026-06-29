# Dashboard Assistant — Setup Guide

A chatbot that answers questions about your channel + marketing data using
your **existing** RBAC-scoped queries — it never writes raw SQL, it only
calls the tool functions in `tools.py`.

## 1. Install the one new dependency

```bash
pip install google-generativeai
```

Add it to `requirements.txt` so Render picks it up on deploy:
```
google-generativeai>=0.8
```

## 2. Get a free Gemini API key

1. Go to https://aistudio.google.com/apikey
2. Sign in with a Google account → "Create API key" (no card needed)
3. Free tier (gemini-2.0-flash, as of writing): generous daily request
   quota, plenty for an internal dashboard's chat volume.

## 3. Set the environment variable

**Locally** (e.g. in your `.env` or shell before `runserver`):
```bash
export GEMINI_API_KEY="your-key-here"
```

**On Render:** Dashboard → your service → *Environment* tab → Add
Environment Variable → `GEMINI_API_KEY` = `your-key-here` → Save (triggers
a redeploy). That's the entire Render-specific setup — there's no extra
infra, no GPU, no background worker needed, since each chat turn is just
an outbound HTTPS call to Gemini that Render's free/standard web service
tier handles fine.

## 4. Drop the `chatbot` app into your project

Copy the `chatbot/` folder next to your other apps (`channel/`,
`marketing/`, etc.), then in your project's `settings.py`:

```python
INSTALLED_APPS = [
    ...
    'chatbot',
]
```

And in your project's main `urls.py`:

```python
urlpatterns = [
    ...
    path('chatbot/', include('chatbot.urls')),
]
```

No models, no migrations needed — conversation history is kept in the
Django session (cleared on logout / browser close), not the database.

## 5. Add the widget to your base template

In whichever template all your dashboard pages extend (the one with your
sidebar/header), right before `</body>`:

```django
{% include 'chatbot/widget.html' %}
```

That's it — a floating 💬 button appears bottom-right on every page that
extends that base template.

## 6. Verifying it RBAC-scopes correctly

Log in as a BU-locked or ARM-locked user and ask something broad like
"top 5 regions by revenue" — it should come back scoped to what
`get_scoped_qs(user)` already restricts them to, exactly like the rest of
the dashboard. The LLM never sees or controls `request.user` — it's
injected server-side in `llm._run_tool()`, so there's no prompt-injection
path to widen someone's own access.

## 7. Extending it later

To teach the bot a new kind of question:
1. Add a function to `tools.py` that wraps the relevant existing
   aggregation logic (reuse `get_scoped_qs`, don't reinvent it).
2. Add the function to `TOOL_FUNCTIONS`.
3. Add a matching entry to `TOOL_SCHEMAS` describing when to use it —
   this description is what the model reads to decide which tool fits a
   given question, so be specific about example phrasings and the exact
   metric names it accepts.

## 8. Performance notes

- Each answer takes roughly 1–4 seconds (Gemini's response time) plus a
  near-instant DB aggregation — your existing queries are already
  `Sum`/`Case`/`When` on indexed columns, so they're not the bottleneck.
- Tool results are cached per-user per-filter-combination for 2 minutes
  (`chatbot/tools.py::_cached`), so quick follow-up questions reusing the
  same filters skip the DB hit entirely.
- `MAX_TOOL_HOPS = 4` in `llm.py` caps how many tool calls one question
  can trigger, so a confused model can't loop indefinitely.
