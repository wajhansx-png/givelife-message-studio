import threading, unittest
from donor_delivery import DonorDelivery

class StopReconnectTests(unittest.TestCase):
 def test_stop_during_connection_check_prevents_dispatch(self):
  delivery=object.__new__(DonorDelivery)
  delivery.stop=threading.Event()
  calls=[]
  def connected():
   delivery.stop.set()
   return True
  delivery.connected=connected
  delivery.send=lambda body:calls.append(body)
  self.assertIsNone(delivery._dispatch({}, {'message':'test'}, [],0,0))
  self.assertEqual(calls,[], 'Stop must be checked again after reconnecting')

if __name__=='__main__':unittest.main()
