"""Kept remembers who wrote before, and asks only what's missing."""
from datetime import date, timedelta

from kept import intake, tryit
from kept.store import write_json


def test_a_returning_client_is_remembered_from_alexs_records(fake):
    old = (date.today() - timedelta(days=6)).isoformat()
    write_json("inbox.json", [{"id": "m1", "from": "Jo Rivera <jo@riverahome.example>", "subject": "Our old kitchen",
                               "date": old, "ts": f"{old}T09:00:00+00:00", "body": "Hi Alex, what would a new kitchen cost?"}])
    from kept import estimate
    estimate.remember("jo@riverahome.example", {"low": 11500, "high": 14100, "mid": 12800, "lines": []}, "full_kitchen")
    from kept.reply import thread
    mem = tryit.remember("jo@riverahome.example", "Jo Rivera", thread("jo@riverahome.example"))
    assert mem["since"] == old and mem["topic"] == "Our old kitchen" and mem["days"] == 6
    assert mem["estimate"] == {"low": 11500, "high": 14100, "job": "full_kitchen"}


def test_someone_new_has_no_memory():
    assert tryit.remember("new@x.example", "New", []) is None


def test_same_name_from_another_address_is_flagged_never_merged():
    hit = tryit.same_name_elsewhere("maria.l@example.com", "Maria Lopez")
    assert hit["email"] == "maria@lopezhome.example"
    assert tryit.same_name_elsewhere("maria@lopezhome.example", "Maria Lopez") is None


def test_follow_up_questions_ask_only_whats_missing_and_at_most_two():
    asks = intake.follow_up_questions("full_kitchen", "We want a new kitchen.", photo=False, has_contract=False,
                                      est_from_their_numbers=False)
    assert len(asks) == 2 and "measurements" in asks[0] and "photos" in asks[1]
    asks = intake.follow_up_questions("full_kitchen", "New kitchen in Sellwood by March please.", photo=True,
                                      has_contract=False, est_from_their_numbers=True)
    assert asks == []
    assert "photo of the broken part" in intake.follow_up_questions("small_repair", "hinge broke, I'm on Alberta St", False, False, False)[0]


def test_off_topic_is_only_for_strangers_with_nothing_kitchen_in_it():
    assert intake.is_off_topic("other", "hi", "are you a bot? what's the weather like", photo=False)
    assert not intake.is_off_topic("other", "hi", "my cabinet door fell off", photo=False)
    assert not intake.is_off_topic("other", "", "what do you think?", photo=True)


def test_a_written_quote_by_a_set_day_before_the_visit_is_caught():
    from kept.reply import QUOTE_BY_DAY
    assert QUOTE_BY_DAY.search("Let me know which time works and I'll send a written quote by Friday, October 30.")
    assert QUOTE_BY_DAY.search("you'll have the estimate by tomorrow")
    assert not QUOTE_BY_DAY.search("The exact price comes after the free measuring visit on Monday.")
    assert not QUOTE_BY_DAY.search("I can come on Monday, Oct 26 at 5:30 pm.")


def test_quote_by_a_day_is_caught_in_either_order():
    from kept.reply import QUOTE_BY_DAY
    assert QUOTE_BY_DAY.search("Let me know which slot works, and by Friday, October 30 I'll send you a written quote.")


def test_spanish_weekdays_are_not_read_as_months():
    from datetime import date
    from kept.validators import dates_in
    assert dates_in("Puedo ir el martes 27 a las 16:30", date(2026, 10, 24)) == []
    assert dates_in("on March 27 or Oct 30", date(2026, 10, 24)) == [date(2026, 3, 27), date(2026, 10, 30)]


def test_the_words_name_the_job_when_the_model_doesnt():
    from kept.intake import WORD_JOBS
    pick = lambda t: next((j for rx, j in WORD_JOBS if rx.search(t)), None)
    assert pick("Could you put in a new tile backsplash behind the stove?") == "backsplash"
    assert pick("A cabinet hinge broke") == "small_repair"
    assert pick("replace our laminate counter with quartz") == "countertop"
    assert pick("How much for a new kitchen?") == "full_kitchen"


def test_a_typo_ridden_kitchen_question_is_not_off_topic():
    assert not intake.is_off_topic("question", "kichen", "hi i ned new kichen cabnets how mch?", photo=False)


def test_a_visit_time_the_calendar_didnt_offer_is_caught():
    from kept.validators import times_not_offered
    slots = [{"date": "2026-10-26", "time": "17:30"}, {"date": "2026-10-27", "time": "16:30"}]
    assert times_not_offered("Monday, Oct 26 at 5:30 pm or Tuesday at 4:30 pm", slots) == []
    assert times_not_offered("choose Wednesday, Oct 28 at 5:30 pm", slots) == ["Wednesday 5:30 pm"]


def test_the_reply_language_is_checked_against_theirs():
    from kept.validators import language_of
    assert language_of("Bonjour Alex, nous aimerions une nouvelle crédence dans la cuisine. Quel est le prix?") == "fr"
    assert language_of("Hola Alex, queremos cambiar las puertas de los gabinetes de la cocina.") == "es"
    assert language_of("Здравствуйте! Сколько стоит столешница?") == "ru"
    assert language_of("Hi Claire, a new backsplash starts from $1,200 and the visit is free.") == "en"


def test_a_visit_time_written_the_french_way_counts():
    from kept.reply import _names_a_slot
    slots = [{"date": "2026-10-26", "time": "17:30"}]
    assert _names_a_slot("Je peux passer le lundi 26 octobre à 17 h 30.", slots)
    assert _names_a_slot("le 26 octobre à 17h30", slots)


def test_other_trades_are_told_kindly_its_not_alexs_work():
    assert intake.not_our_trade("toilet", "Our upstairs toilet keeps running and the bathroom floor is wet.")
    assert intake.not_our_trade("roof leak", "We have a roof leak over the garage.")
    assert not intake.not_our_trade("vanity", "Do you also build bathroom vanities? Ours is falling apart.")
    assert not intake.not_our_trade("outlet", "The outlet behind the kitchen counter needs moving for the new cabinets")


def test_more_ways_of_promising_a_quote_on_a_day():
    from kept.reply import QUOTE_BY_DAY
    assert QUOTE_BY_DAY.search("and I'll follow up with a written quote on Friday, October 30.")
    assert not QUOTE_BY_DAY.search("The exact price comes after the free measuring visit on Monday.")


def test_a_typo_kitchen_is_still_a_kitchen_job():
    from kept.intake import WORD_JOBS
    assert next((j for rx, j in WORD_JOBS if rx.search("hi i ned new kichen cabnets how mch?")), None) == "full_kitchen"


def test_a_visitor_never_sees_another_visitors_contact():
    from kept import web
    from kept.store import write_json
    write_json("inbox.json", [{"id": "you:abc", "from": "Pat Real <pat.real@example.com>", "subject": "s", "date": "2026-10-24", "body": "hi"}])
    assert not any(p["email"] == "pat.real@example.com" for p in web.people(""))
    assert any(p["email"] == "pat.real@example.com" for p in web.people("pat.real@example.com"))


def test_dates_written_with_odd_spaces_are_still_checked():
    """Live, Oct 24: 'October 23' slipped a passed date into Maria's email: the check looked for a plain space."""
    from datetime import date
    from kept.validators import dates_in, honest_email
    body = "Hi Maria, the revised quote will be sent by October 23, 2026.\n\nAlex"
    assert dates_in(body, date(2026, 10, 24)) == [date(2026, 10, 23)]
    assert honest_email(body, recipient_first="Maria", owner_first="Alex", today=date(2026, 10, 24)).problems


def test_a_wrong_weekday_and_a_database_date_are_caught():
    """Live, Oct 24: 'I can't do Sundays, so not 2026-10-26' (a Monday)."""
    from datetime import date
    from kept.validators import iso_dates, wrong_weekdays
    today = date(2026, 10, 24)
    assert wrong_weekdays("Can we meet Sunday, Oct 26?", today) == ["Sunday, Oct 26 (it's a Monday)"]
    assert wrong_weekdays("Monday, Oct 26 at 5:30 pm", today) == []
    assert wrong_weekdays("on Sunday 2026-10-26", today)
    assert iso_dates("I'm unable to meet on 2026-10-26") == ["2026-10-26"]


def test_someone_alex_already_deals_with_is_never_off_topic():
    """Live, Oct 24: Alex's accountant asked for the Q3 receipts and the reply said 'I specialize in kitchens'."""
    from kept import ledger
    ledger.add("Send Sam Okafor the Q3 receipts", who="Sam Okafor", contact="sam@okaforcpa.example", due="2026-10-25")
    assert intake._known("sam@okaforcpa.example", "m-new")
    assert not intake._known("stranger@example.com", "m-new")


def test_a_strangers_own_email_doesnt_make_them_known():
    """Live, Oct 24: the promise read from a stranger's first email ('fix a running toilet') made them 'known'."""
    from kept import ledger
    ledger.add("Fix Rita's running toilet", who="Rita Moss", contact="rita.moss@example.com", source="you:abc123")
    assert not intake._known("rita.moss@example.com", "you:abc123")
    assert intake._known("rita.moss@example.com", "you:later")
