# Kept's constitution

What the models may do, and what only code may do. Every rule below is enforced in code and has a test.

**The model never decides a price, a date, or who gets an email.**

1. **Nothing reaches another person without the owner's Yes.** Outgoing actions are registered as needing
   approval; `approvals.execute()` refuses anything not approved. A model has no path to send.
2. **Prices come from the owner's records, never from a model.** Extra work = hours × the hourly rate;
   a preliminary estimate = sizes × the owner's price guide; a payment plan = the owner's terms applied to
   that estimate. A draft that names any other dollar figure is held back.
3. **Dates are worked out by code.** "By Friday" is resolved from the words, then checked against how the
   owner has actually delivered before. A promised date that has passed is held back.
4. **Visit times come from the calendar, and only code books them,** when the client names one of the
   times that were offered.
5. **A promise only exists if its words are in the email.** No quote, no ledger row.
6. **Facts from the web need a quote from a page that names the business.** Otherwise they are dropped,
   and the owner can see what was dropped and why.
7. **Disagreement means "unclear".** The signed agreement is read twice by Nemotron Ultra at two
   temperatures; if the readings disagree, Kept doesn't charge and doesn't promise.
8. **When a check fails, Kept says so.** It holds back, writes the reason under Held back, and doesn't guess.
   A reply gets two more tries with the checks' own words, then it stops.
9. **One message to a person at a time.** A newer email from them makes an unsent draft stale; it is marked
   replaced, never deleted.
10. **A spoken Yes is heard by code, not a model.** "yes, send it" sends the one draft that was on screen or
    read out; "yes, but...", "don't send it" or anything unclear sends nothing and Kept asks again; a spoken No
    only holds the draft. A model may sort free speech into what to read out; it can never approve.
11. **Kept answers people honestly or not at all.** Only possible new clients can be off-topic; they get a short
    answer with no prices or visit times and no promise to look anything up. People the owner already deals
    with always get a real answer. A familiar name from a new address is shown to the owner, never merged.
12. **The owner's data stays the owner's.** Plain files they can read (ledger, journal, audit of every model
    call); Nebius Token Factory with zero data retention; learned rules go into the owner's own copy of a skill.
