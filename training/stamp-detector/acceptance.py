from pathlib import Path
import argparse, json

def main():
    p=argparse.ArgumentParser();p.add_argument('--metrics',required=True,help='JSON with single_recall, sparse_recall, dense_recall, false_positive_rate');a=p.parse_args();m=json.loads(Path(a.metrics).read_text())
    gates={'single_recall':.98,'sparse_recall':.95,'dense_recall':.90}
    failures=[f'{k}={m.get(k)} < {v}' for k,v in gates.items() if float(m.get(k,0))<v]
    if float(m.get('false_positive_rate',1))>.03: failures.append(f"false_positive_rate={m.get('false_positive_rate')} > 0.03")
    if failures: raise SystemExit('FAIL\n'+'\n'.join(failures))
    print('PASS — stamp detector meets Browser Beta acceptance gates')
if __name__=='__main__':main()
