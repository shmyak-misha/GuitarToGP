import requests, time

with open(r'C:\Users\shnai\Downloads\Mr Lonely.pdf', 'rb') as f:
    r = requests.post(
        'http://127.0.0.1:8000/api/convert-pdf',
        files={'file': ('Mr Lonely.pdf', f, 'application/pdf')}
    )
print(r.status_code, r.text[:200])
job_id = r.json()['job_id']
print('job_id:', job_id)
for _ in range(90):
    s = requests.get(f'http://127.0.0.1:8000/api/status/{job_id}').json()
    st = s.get('status')
    pr = s.get('progress', 0)
    msg = s.get('message', '')[:70]
    print(f'{st} {pr}% {msg}')
    if st in ('completed', 'failed'):
        break
    time.sleep(2)
