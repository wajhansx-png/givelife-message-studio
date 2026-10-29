"""Poster and chat attachments can be an MP4 video for DMs and groups."""
import base64,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

MP4=b'\x00\x00\x00\x18ftypmp42'+b'\x00'*64
JPG=b'\xff\xd8\xff\xe0'+b'\x00'*64
def url(raw,mime):return f'data:{mime};base64,'+base64.b64encode(raw).decode()

class VideoPoster(unittest.TestCase):
 def setUp(self):
  self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup);d=Path(self.dir.name);(d/'attachments').mkdir()
  self.patches=[patch.object(server,'DATA',d),patch.object(server,'ATT',d/'attachments'),patch.object(server,'STORE',None),patch.object(server,'DONORS',None),patch.dict(server.CAMPAIGN,{'running':False})]
  for p in self.patches:p.start()
  self.addCleanup(lambda:[p.stop() for p in self.patches]);self.d=d
 def test_a_video_poster_is_used_for_sends_until_a_picture_replaces_it(self):
  (self.d/'poster.jpg').write_bytes(JPG)
  self.assertEqual(server.poster_media().name,'poster.jpg')
  self.assertEqual(server.save_upload(url(MP4,'video/mp4'),'poster'),'poster');self.assertEqual(server.poster_media().name,'poster.mp4')
  server.save_upload(url(JPG,'image/jpeg'),'poster');self.assertEqual(server.poster_media().name,'poster.jpg')
 def test_missing_video_file_falls_back_to_the_picture(self):
  (self.d/'poster.jpg').write_bytes(JPG);(self.d/'poster-kind.txt').write_text('video');self.assertEqual(server.poster_media().name,'poster.jpg')
 def test_only_real_mp4_under_the_whatsapp_limit(self):
  with self.assertRaisesRegex(ValueError,'MP4'):server.save_upload(url(b'not a video at all',"video/webm"),'poster')
  with self.assertRaisesRegex(ValueError,'too big'):server.save_upload(url(b'\x00\x00\x00\x18ftypmp42'+b'\x00'*15_000_001,'video/mp4'),'attachment')
 def test_video_attachments_are_found_for_chat_sends(self):
  aid=server.save_upload(url(MP4,'video/mp4'),'attachment');self.assertEqual(server.image_path(aid).suffix,'.mp4')
  pic=server.save_upload(url(JPG,'image/jpeg'),'attachment');self.assertEqual(server.image_path(pic).suffix,'.jpg')
 def test_the_gateway_video_endpoint_is_used_for_video_and_image_endpoint_for_pictures(self):
  seen=[]
  with patch.object(server.subprocess,'run',side_effect=lambda cmd,**k:seen.append(cmd) or type('R',(),{'stdout':b'{}'})()):
   server.post_media('1@s.whatsapp.net',self.d/'c.txt',self.d/'poster.mp4');server.post_media('1@s.whatsapp.net',self.d/'c.txt',self.d/'poster.jpg')
  self.assertTrue(any(str(x).endswith('/send/video') for x in seen[0]));self.assertTrue(any(str(x).startswith('video=@') for x in seen[0]))
  self.assertTrue(any(str(x).endswith('/send/image') for x in seen[1]))
if __name__=='__main__':unittest.main()

class GuardStaysOnTheSender(unittest.TestCase):
 def test_the_stop_and_supersede_guard_wraps_the_real_senders_not_the_helpers(self):
  self.assertTrue(hasattr(server.send_image,'__wrapped__'));self.assertTrue(hasattr(server.send_with_image,'__wrapped__'))
  self.assertFalse(hasattr(server.poster_media,'__wrapped__'));self.assertFalse(hasattr(server.post_media,'__wrapped__'))
