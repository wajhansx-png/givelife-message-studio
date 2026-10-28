"""Synthetic bridge: exercise actual Python business rules from Vitest/fast-check."""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from donor_book import DonorBook,normalize_phone

def run(case):
    if case['op']=='phone':return normalize_phone(case['value'])
    with tempfile.TemporaryDirectory() as folder:
        book=DonorBook(folder)
        if case['op']=='total':
            for i,cents in enumerate(case['cents']):
                d=book.add(f'Synthetic {i}',f'1555{1230000+i}')['donor']
                book.update(d['id'],donated=True,amount=cents/100)
            return book.list()['counts']['donated_amount']
        if case['op']=='duplicates':
            rows=[{'name':f'Synthetic {i}','phone':phone} for i,phone in enumerate(case['phones'])]
            result=book.add_contacts(rows,'923205069925')
            return {'count':book.list()['counts']['all'],'added':result['added'],'public':result}
raise_if_invalid=False
if __name__=='__main__':
    payload=json.load(sys.stdin)
    print(json.dumps(run(payload)))

