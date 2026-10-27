import os,json
try:
 import psycopg
 from psycopg.types.json import Jsonb
except ImportError:  # local preview without the cloud database
 psycopg=Jsonb=None

class CloudStore:
 def __init__(self,uri):self.uri=uri
 def connection(self):return psycopg.connect(self.uri,connect_timeout=15,autocommit=True)
 def initialize(self):
  with self.connection() as db:
   db.execute('CREATE TABLE IF NOT EXISTS givelife_studio_state (key TEXT PRIMARY KEY, value JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
 def get(self,key,default=None):
  with self.connection() as db:row=db.execute('SELECT value FROM givelife_studio_state WHERE key=%s',(key,)).fetchone()
  return row[0] if row else default
 def put(self,key,value):
  with self.connection() as db:db.execute('INSERT INTO givelife_studio_state (key,value) VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()',(key,Jsonb(value)))
 def seed(self,key,value):
  with self.connection() as db:db.execute('INSERT INTO givelife_studio_state (key,value) VALUES (%s,%s) ON CONFLICT(key) DO NOTHING',(key,Jsonb(value)))
 def claim(self,key,value):
  """Reserve one occurrence across overlapping deploy processes, without replacing its owner."""
  with self.connection() as db:
   row=db.execute('INSERT INTO givelife_studio_state (key,value) VALUES (%s,%s) ON CONFLICT(key) DO NOTHING RETURNING key',(key,Jsonb(value))).fetchone()
  return row is not None
 def restore(self,data,root):
  self.initialize()
  for file,key in [('drafts.json','drafts'),('state.md','campaign'),('variant-state.json','variants')]:
   seed=(root/file).read_text(encoding='utf-8') if (root/file).exists() else '{"index":0}'
   self.seed(key,seed);(data/file).write_text(self.get(key),encoding='utf-8')

def configured_store():
 uri=os.environ.get('DB_URI')
 return CloudStore(uri) if uri else None

