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
- **The promo-code form is easy to miss.** The "Fill out this form" link opens nebius.com/promo-code,
  where the first thing that renders is a newsletter sign-up; the real promo form loads later inside
  an embedded frame further down. On our first visit we gave up thinking the page was broken. Once
  found, it worked: "Form submitted. The promo code will be emailed to you." It would help if the
  console simply had a "Redeem a code" box next to the trial balance.
- **Two different "verify your email" flows** (Builders Program and Token Factory) arrive with the
  same subject line. Different subjects would help.
- The billing form clears street, city and postal code when you change the country, and only
  then shows the State field. Filling the country first avoids it, but nothing tells you that.

## Token Factory API

**What worked**
- `/v1/models` lists the Nemotron family with stable IDs (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`,
  `nvidia/nemotron-3-super-120b-a12b`, `nvidia/Nemotron-3-Ultra-550b-a55b`), so Kept discovers the
  models at start-up instead of hard-coding them. Note the inconsistent casing between the three IDs;
  we match case-insensitively.
- `response_format: json_object` is honoured by all three sizes.
- Latency was good: Nano answers in under a second with reasoning off, Super in 2-8 s, Ultra in
  roughly 5-15 s for a real decision.
- Super and Ultra return their reasoning in a separate `reasoning_content` field. We store Ultra's
  reasoning next to its decision so the owner can see *why* it proposed moving a deadline.

**What needs work**
- **Hidden reasoning can eat the whole answer.** Our first live run of Nano with `max_tokens=200`
  came back with `finish_reason: length`, empty `content` and empty `reasoning_content`, while
  usage showed all 200 tokens spent. Nothing in the response says the tokens went to reasoning.
  Passing `chat_template_kwargs: {"enable_thinking": false}` fixed it: 34 tokens, 0.8 s. A line
  in the quickstart ("Nemotron 3 reasons by default; budget for it or switch it off") would have
  saved us an hour. The `/no_think` system prompt and `reasoning_effort: low` did not help.

## NVIDIA Nemotron
_(to be filled in: where Nano was good enough, where Super was needed, what Ultra was worth)_

## Would we build with it again?
_(after the build)_
