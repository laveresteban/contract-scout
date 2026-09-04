import json, httpx, sys, xml.etree.ElementTree as ET, re
sys.stdout.reconfigure(encoding='utf-8')

r = httpx.get('https://remoteok.com/api')
data = r.json()
tag_counter = {}
for item in data[1:]:
    for t in item.get('tags', []):
        tag_counter[t] = tag_counter.get(t, 0) + 1

print('--- RemoteOK employment-related tags ---')
for t, c in sorted(tag_counter.items()):
    if any(k in t.lower() for k in ['full time','part time','contract','freelance','temporary','intern','permanent','w2','1099','c2c']):
        print(t, c)

print('\n--- RemoteOK sample with non-zero salary ---')
for item in data[1:]:
    if item.get('salary_min') or item.get('salary_max'):
        print(item.get('position'), item.get('company'), 'salary_min:', item.get('salary_min'), 'salary_max:', item.get('salary_max'))
        break

r = httpx.get('https://weworkremotely.com/remote-jobs.rss')
root = ET.fromstring(r.content)
print('\n--- WWR category tags ---')
cats = set()
for item in root.findall('.//item')[:100]:
    cats.add(item.findtext('category'))
for c in sorted(cats)[:20]:
    print(c)
