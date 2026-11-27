import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_manual_sends import app as server


def registry(state=None, current="", active=True):
    jobs = [{"state": state, "current": current}] if state else []
    return SimpleNamespace(active=active and bool(state), _cache={"jobs": jobs})


class SendingNow(unittest.TestCase):
    def busy(self, giki):
        idle = registry()
        hub = SimpleNamespace(
            jobs=idle,
            volunteers=SimpleNamespace(jobs=idle),
            giki=SimpleNamespace(jobs=giki),
            giki2=SimpleNamespace(jobs=idle),
        )
        with patch.object(server, "donors", return_value=hub):
            return server.sending_now()

    def test_nothing_running_is_not_busy(self):
        self.assertFalse(self.busy(registry()))

    def test_a_person_being_sent_to_is_busy(self):
        self.assertTrue(self.busy(registry("Sending", "Giki P1")))

    def test_the_wait_between_people_is_not_busy(self):
        self.assertFalse(self.busy(registry("Waiting", "Waiting between DMs")))
        self.assertFalse(self.busy(registry("Waiting", "Waiting for the next batch time")))

    def test_waiting_for_whatsapp_mid_person_is_busy(self):
        self.assertTrue(self.busy(registry("Waiting", "Waiting for WhatsApp to reconnect")))

    def test_a_send_going_out_is_busy(self):
        held = []
        import threading

        t = threading.Thread(
            target=lambda: (
                server.SEND_LOCK.acquire(),
                held.append(1),
                ev.wait(),
                server.SEND_LOCK.release(),
            )
        )
        ev = threading.Event()
        t.start()
        while not held:
            pass
        try:
            self.assertTrue(self.busy(registry()))
        finally:
            ev.set()
            t.join()


if __name__ == "__main__":
    unittest.main()
