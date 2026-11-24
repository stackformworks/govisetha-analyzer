import argparse, json, os, time
from pathlib import Path
from datetime import datetime, timezone
from collector.scraper import discover_latest_draw, parse_draw

PATH = Path('site/data/govisetha.json')
def save(rows, checked, cursor):
    payload = {'source':'NLB','checked_at':checked,'backfill_cursor':cursor,'draws':sorted(rows.values(),key=lambda r:r['draw_no'])}
    temp = PATH.with_suffix('.tmp')
    temp.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8')
    os.replace(temp,PATH)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--batch',type=int,default=30)
    p.add_argument('--earliest',type=int,default=1)
    a=p.parse_args()
    previous=json.loads(PATH.read_text())
    rows={r['draw_no']:r for r in previous['draws']}
    latest=discover_latest_draw()
    # Refresh recent draws first, then fill missing history in bounded batches.
    recent=list(range(latest,max(0,latest-3),-1))
    cursor=min(latest,previous.get('backfill_cursor') or latest)
    if cursor<a.earliest: cursor=latest
    missing=(n for n in range(cursor,max(0,a.earliest-1),-1) if n not in rows and n not in recent)
    from itertools import islice
    ids=recent+list(islice(missing,max(0,min(a.batch,100)-len(recent))))
    success=0; failed=[]; started=time.monotonic()
    for n in ids:
        if time.monotonic()-started>240: break
        if n not in recent: cursor=n-1
        try:
            r=parse_draw(n)
            rows[n]=r; success+=1
            print('Validated',n,flush=True)
        except Exception as e:
            failed.append(n); print('Rejected',n,str(e),flush=True)
            if len(failed)>=5 and not success: break
        time.sleep(1)
    if not success: raise SystemExit('No verified results retrieved; existing JSON preserved.')
    save(rows,datetime.now(timezone.utc).isoformat(),cursor)
    print(f'Collected {success}; rejected {failed}; total {len(rows)}')
if __name__=='__main__': main()
