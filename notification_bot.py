from migrationsverket import MigrationsverketBooking, InternalServerError

import argparse
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

DEFAULT_TIMER = 1 #hour

#States
BOOKING_CODE, BOOKING_EMAIL, NOTIFY = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! I can look for earlier booking times at Migrationsverket, note that you must already have a booked time!\n")

    # Remove existing job if this is a restart
    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    
    # Clean user information after restart
    user_data = context.user_data
    if "booking_code" in user_data:
        del user_data['booking_code']
    if "booking_email" in user_data:
        del user_data['booking_email']

    await update.message.reply_text("Please input your current booking code:")
    return BOOKING_CODE

async def get_booking_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['booking_code'] = update.message.text

    await update.message.reply_text("Please input your booking email:")
    return BOOKING_EMAIL

async def get_booking_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['booking_email'] = update.message.text

    # Get booking info
    mb =  MigrationsverketBooking(context.user_data['booking_code'], context.user_data['booking_email'])
    current_booking = mb.get_current_booking_information()

    await update.message.reply_text(
        "This is your current booking information:\n"
        f"\tCode: {current_booking['code']}\n"
        f"\tEmail: {current_booking['email']}\n"
        f"\tPlace: {current_booking['place']}\n"
        f"\tDate: {current_booking['date']}\n"
        )

    await update.message.reply_text("How often should I notify you (in hours)?")

    return NOTIFY


async def get_timer_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I will let you know if any bookings earlier than that become available!")

    chat_id = update.message.chat_id
    
    try:
        timer_period = float(update.message.text)
        if timer_period < 0:
            raise ValueError()
        
        job = context.job_queue.run_repeating(check_earlier_booking, timer_period*3600, name=str(chat_id), user_id=update.message.from_user.id, chat_id=chat_id)    
        await job.run(context.application)
    except (IndexError, ValueError):
        await update.message.reply_text("Invalid value!")
        await update.message.reply_text("How often should I notify you (in hours)?")
        pass

    return NOTIFY

async def default_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I don't understand what you're saying!")

    return None

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove the job if the user changed their mind."""

    chat_id = update.message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)

    await update.message.reply_text("I will stop notifying now!")

    return BOOKING_CODE


async def check_earlier_booking(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the alarm message."""
    job = context.job

    mb =  MigrationsverketBooking(context.user_data['booking_code'], context.user_data['booking_email'])

    earlier_slots = mb.get_earlier_slots()

    if len(earlier_slots):
        await context.bot.send_message(job.chat_id, text=f"The following earlier booking times are available:\n")
        msg = ""
        for slot in earlier_slots:
            msg += f"Slot ID: {slot['id']}\nSlot date: {slot['start']}"

        await context.bot.send_message(job.chat_id, text=msg)
        await context.bot.send_message(job.chat_id, text=f"(I still don't know how to book it for you, sorry \U0001F623 \n Quick, change your booking at: https://www.migrationsverket.se/ansokanbokning/omboka")
    else:
        await context.bot.send_message(job.chat_id, text=f"No earlier times are available \U0001F61E")


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)

    if not current_jobs:
        return False

    for job in current_jobs:
        job.schedule_removal()

    return True

def main(token) -> None:
    """Run the bot."""

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(token).build()

    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            BOOKING_CODE: [MessageHandler(filters.Regex(r'^[A-Z]{4}-\d{4}$'), get_booking_code)],
            BOOKING_EMAIL: [MessageHandler(filters.Regex(r'^\S+@\S+\.\S+$'), get_booking_email)],
            NOTIFY: [MessageHandler(filters.Regex(r'\d+'), get_timer_period)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )

    application.add_handler(conv_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('token', help='File with Bot token from BotFather', type=argparse.FileType('r'))
    args = parser.parse_args()

    token = args.token.read().splitlines()[0]
    main(token)
