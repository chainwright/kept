# Feedback on Nebius Token Factory and NVIDIA Nemotron

Written as we built Kept, in the order things happened, so it reflects what a first-time
builder actually goes through. Times are from our notes on Oct 24, 2026.

## Onboarding: zero to "hello world"

**What worked**
- Signing in with Google was quick, and the contact-details step verified our email with a
  6-character code that arrived within a minute.
- The console's landing page shows a copy-paste OpenAI-SDK snippet with the base URL and the
  `NEBIUS_API_KEY` variable. For anyone who has used the OpenAI SDK, the mental model is instant.
- The "zero data retention" option is offered during profile setup, before you've sent a single
  prompt. For a personal assistant that reads someone's inbox, that is exactly when the question
  should be asked. We switched it on, and it became part of our privacy story.

**What needs work**
- **A card is required before hackathon credits can be used.** The FAQ says promo credits come
  through a form and the Builders Program, but the console shows a mandatory "Billing details"
  screen (address + card) before anything else. Builders who expect "free credits" are surprised
  here. A line on the Devpost resources page ("you'll need to add a card; it's a $0 authorization")
  would remove the surprise.
- **The promo-code page didn't render its form for us.** The "Fill out this form" link from the
  Devpost resources opened nebius.com/promo-code, which showed a newsletter sign-up but no promo
  field. We couldn't tell whether the code had been applied.
- **Two different "verify your email" flows** (Builders Program and Token Factory) arrive with the
  same subject line. Different subjects would help.
- The billing form clears street, city and postal code when you change the country, and only
  then shows the State field. Filling the country first avoids it, but nothing tells you that.

## Token Factory API
_(to be filled in once we have a key: latency per model, JSON mode behaviour, rate limits,
`/v1/models` listing, error messages)_

## NVIDIA Nemotron
_(to be filled in: where Nano was good enough, where Super was needed, what Ultra was worth)_

## Would we build with it again?
_(after the build)_
