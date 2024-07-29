import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pprint import pprint as pp
import argparse
import schedule

##Debug
import code
import logging
import http.client

URL_OMBOKA_MIGRATIONSVERKET = "https://www.migrationsverket.se/ansokanbokning/omboka"

class InternalServerError(Exception):
    def __init__(self):
        super(InternalServerError, self).__init__()

    def __str__(self):
        return f"Internal error from Migrationsverket server!"


class MigrationsverketBooking():
    def __init__(self, booking_code, booking_email, debug=False):
        if debug:
            http.client.HTTPConnection.debuglevel=1
            logging.basicConfig()
            logging.getLogger().setLevel(logging.DEBUG)
            req_log = logging.getLogger('requests.packages.urllib3')
            req_log.setLevel(logging.DEBUG)
            req_log.propagate = True

        self.login_data = {'code': booking_code, 'email': booking_email}
        self.url = URL_OMBOKA_MIGRATIONSVERKET
        self.available_slots = {}
        
        self.session = requests.Session()
        self._get_cookies()
        self._login()
        self.get_available_slots()

    def _get_cookies(self):
        # Cookie will be store in the session obj
        r = self.session.get(self.url)
        # We get redirected to a new URL with a cookie
        self.url = r.url
    
    def _login(self):
        booking_data = {
            'bokningsnummer.border:bokningsnummer.border_body:bokningsnummer': self.login_data['code'],
            'epost.border:epost.border_body:epost': self.login_data['email'],
            'fortsatt': "Next"
        }

        r = self.session.post(f"{self.url}-1.-form=", data=booking_data)
        self.url = r.url
        soup = BeautifulSoup(r.content, 'html5lib')
        div = soup.find('div', class_='personInfoPanel')

        booking_date, booking_time, place, current_booking_code = [tag.text for tag in div.find_all("p", class_="tdData")]
        current_booking_date = datetime.fromisoformat(f"{booking_date}T{booking_time.split(' ')[0]}")
        self.current_booking = {"date": current_booking_date, "place": place, "code": current_booking_code, "email": self.login_data['email']}

    def get_current_booking_information(self):
        return self.current_booking

    def get_available_slots(self, start=datetime.now(), end=(datetime.now() + relativedelta(months=4))):
        data = {
            'start': start.isoformat(),
            'end': end.isoformat()
        }
        r = self.session.post(f"{self.url}-1.1-kalender-kalender", data=data)

        try:
            self.available_slots = r.json()
        except requests.exceptions.JSONDecodeError:
            if "A technical error has unfortunately occurred" in r.text:
                raise InternalServerError()
        return self.available_slots

    def get_earlier_slots(self):
        if len(self.available_slots) == 0: return []
        
        earlier_slots = [slot for slot in self.available_slots if slot['className'][0] == 'ledig' and (datetime.fromisoformat(slot['start']) < self.current_booking["date"])]
        
        return earlier_slots


def check_new_bookings(booking_code, booking_email, debug):
    mb =  MigrationsverketBooking(booking_code = booking_code, booking_email = booking_email, debug = debug)
    available_slots = mb.get_available_slots()
    earlier_slots = mb.get_earlier_slots()

    if debug:
        print("Available Slots:")
        pp(available_slots)

    print("Earlier Slots:")
    pp(earlier_slots)
    return earlier_slots

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("booking_code", type=str, help="Booking code from Migrationsverket")
    parser.add_argument("booking_email", type=str, help="E-mail used for original booking")
    parser.add_argument("-t", "--time", type=int, default=1, help="Time between checks (in hours)")
    parser.add_argument("-d", "--debug", action='store_true', help="Enable network debug")

    args = parser.parse_args()
    
    #Run once now
    check_new_bookings(args.booking_code, args.booking_email, args.debug)

    schedule.every(args.time).hour.do(check_new_bookings, args.booking_code, args.booking_email, args.debug)

    while True:
        schedule.run_pending()